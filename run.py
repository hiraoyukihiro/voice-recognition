"""
全体統合パイプライン。これ1つを実行すれば全機能が動く。
実行: python run.py
ブラウザで http://localhost:8080 が自動で開く。
"""
import asyncio
import http.server
import threading
import webbrowser
import traceback
import os
import sys
import numpy as np
import sounddevice as sd
import websockets
import json

import config

# --- 設定 ---
SILENCE_THRESHOLD = 0.003
AUDIO_GAIN = 10.0
OVERLAP_RMS_RATIO = 2.0

# --- モデルロード ---
print("=" * 50)
print("  音声認識システム 起動中...")
print("=" * 50)

print("\n[1/3] Whisperモデルをロード中...")
import whisper
asr_model = whisper.load_model(config.WHISPER_MODEL)

print("[2/3] 話者識別モデルをロード中...")
from resemblyzer import VoiceEncoder, preprocess_wav
encoder = VoiceEncoder()

print("[3/3] ウォームアップ中（初回のみ時間がかかります）...")
_dummy = np.zeros(config.SAMPLE_RATE * 3, dtype=np.float32)
asr_model.transcribe(_dummy, language=config.WHISPER_LANGUAGE, fp16=False, verbose=False)

print("\n全モデルロード完了\n")

# --- 話者管理 ---
speaker_embeddings: dict[str, np.ndarray] = {}
speaker_count = 0
SIMILARITY_THRESHOLD = 0.75
last_speaker_id = "speaker_1"
last_rms = 0.0

# --- 方向検知 ---
if config.DOA_MODE == "mic_array":
    from processing.direction.xvf3800_doa import XVF3800DOA
    import time as _time

    doa = None
    for _attempt in range(5):
        try:
            doa = XVF3800DOA(
                angle_offset=config.XVF3800_ANGLE_OFFSET,
                invert=config.XVF3800_INVERT,
            )
            break
        except RuntimeError as e:
            print(f"  reSpeaker検出リトライ中... ({_attempt + 1}/5) {e}")
            _time.sleep(1.5)

    if doa is None:
        print("  → reSpeakerが見つからないため、ダミー方向検知にフォールバックします")
        from processing.direction.dummy_doa import DummyDOA
        doa = DummyDOA(mode="sweep")
    else:
        print("  → 方向検知: reSpeaker XVF3800（実機）")
else:
    from processing.direction.dummy_doa import DummyDOA
    doa = DummyDOA(mode="sweep")
    print("  → 方向検知: ダミー（sweep）")

# --- WebSocketクライアント管理 ---
clients: set = set()


def identify_speaker(audio: np.ndarray, current_rms: float) -> str:
    global speaker_count, last_speaker_id, last_rms
    try:
        if last_rms > SILENCE_THRESHOLD and current_rms > last_rms * OVERLAP_RMS_RATIO:
            return last_speaker_id
        wav = preprocess_wav(audio, source_sr=config.SAMPLE_RATE)
        if len(wav) < config.SAMPLE_RATE * 0.5:
            return last_speaker_id
        embedding = encoder.embed_utterance(wav)
        best_id, best_score = None, -1.0
        for spk_id, emb in speaker_embeddings.items():
            score = float(np.dot(embedding, emb))
            if score > best_score:
                best_score = score
                best_id = spk_id
        if best_id is None or best_score < SIMILARITY_THRESHOLD:
            speaker_count += 1
            best_id = f"speaker_{speaker_count}"
            speaker_embeddings[best_id] = embedding
            print(f"  → 新しい話者を検出: {best_id}")
        last_speaker_id = best_id
        return best_id
    except Exception as e:
        return last_speaker_id


def transcribe(audio: np.ndarray) -> str:
    result = asr_model.transcribe(
        audio,
        language=config.WHISPER_LANGUAGE,
        fp16=False,
        verbose=False,
        condition_on_previous_text=False,
    )
    return result["text"].strip()


def record_chunk() -> np.ndarray:
    frames = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    audio = sd.rec(frames, samplerate=config.SAMPLE_RATE, channels=1,
                   dtype="float32", device=config.MIC_DEVICE_INDEX)
    sd.wait()
    return audio[:, 0]


async def ws_handler(websocket, path=None):
    clients.add(websocket)
    print(f"[ブラウザ接続] 現在{len(clients)}台")
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)
        print(f"[ブラウザ切断] 残{len(clients)}台")


async def broadcast(payload: dict):
    if not clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)


def start_http_server():
    """output/web/ を HTTP で配信するサーバーをスレッドで起動"""
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "web")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
        def log_message(self, *args):
            pass  # アクセスログを非表示
        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            super().end_headers()

    server = http.server.ThreadingHTTPServer(("", config.WEB_PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[HTTP] http://localhost:{config.WEB_PORT}")


async def pipeline_loop():
    global last_rms
    loop = asyncio.get_event_loop()
    print("\nマイクに向かって話しかけてください（Ctrl+C で停止）\n")

    while True:
        try:
            audio = await loop.run_in_executor(None, record_chunk)
            rms = float(np.sqrt(np.mean(audio ** 2)))

            if rms < SILENCE_THRESHOLD:
                print(".", end="", flush=True)
                last_rms = 0.0
                continue

            audio_amp = np.clip(audio * AUDIO_GAIN, -1.0, 1.0)
            print(f"\n[音声検出 RMS={rms:.4f}] 認識中...")

            text = await loop.run_in_executor(None, transcribe, audio_amp)
            if not text:
                last_rms = rms
                continue

            direction = doa.estimate(audio_amp)
            speaker_id = await loop.run_in_executor(
                None, identify_speaker, audio_amp, rms
            )
            last_rms = rms

            print(f"[{speaker_id} | {direction:.0f}°] {text}")
            await broadcast({
                "type": "subtitle",
                "speaker_id": speaker_id,
                "text": text,
                "direction": direction,
            })

        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            continue


async def main():
    # HTTPサーバー起動
    start_http_server()

    # WebSocketサーバー起動
    for attempt in range(10):
        try:
            ws_server = await websockets.serve(
                ws_handler, config.WEBSOCKET_HOST, config.WEBSOCKET_PORT
            )
            break
        except OSError:
            print(f"ポート {config.WEBSOCKET_PORT} 使用中... 待機 ({attempt+1}秒)")
            await asyncio.sleep(1)
    else:
        print("エラー: WebSocketポートを開放できませんでした")
        sys.exit(1)

    print(f"[WebSocket] ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")

    # ブラウザを自動で開く
    url = f"http://localhost:{config.WEB_PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"[ブラウザ] {url} を自動で開きます\n")

    try:
        await pipeline_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n停止しました。")
    finally:
        ws_server.close()
        await ws_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
