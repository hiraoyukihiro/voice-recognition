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
# 注記: sd.InputStream（連続録音）はこの環境ではどのバックエンドでも無音になる不具合を確認したため、
# sd.rec()による固定長チャンク方式を使用する。また0.3秒未満の短い録音はデバイスの
# ウォームアップ時間だけで終わり実音声を拾えないため、チャンクは短くしすぎない。
SILENCE_THRESHOLD = 0.003
OVERLAP_RMS_RATIO = 2.0

# --- 音量正規化設定 ---
# 固定倍率だと声の大小でWhisperの精度が変わるため、ピーク音量基準で正規化する
# このマイクは物理的な感度が低いため、上限を高めに設定している
TARGET_PEAK = 0.7
MAX_GAIN = 100.0

# --- マイクデバイス解決 ---
# USB機器の抜き差しでMMEの既定デバイスが無音になる不具合を確認したため、
# 名前+ホストAPIで実際に使えるデバイスを解決する（config.MIC_DEVICE_INDEXは手動指定用に残す）
from input.mic_input import find_input_device

if config.MIC_DEVICE_INDEX is not None:
    mic_device_index = config.MIC_DEVICE_INDEX
else:
    mic_device_index = find_input_device(config.MIC_DEVICE_NAME)
    if mic_device_index is None:
        print(f"  警告: '{config.MIC_DEVICE_NAME}' を含むマイクが見つからないため、システムデフォルトを使用します")
print(f"  → マイク入力デバイス: {mic_device_index if mic_device_index is not None else 'システムデフォルト'}")

# --- モデルロード ---
print("=" * 50)
print("  音声認識システム 起動中...")
print("=" * 50)

print("\n[1/3] Whisperモデルをロード中...")
if config.WHISPER_ENGINE == "faster_whisper":
    from processing.recognition.faster_whisper_asr import FasterWhisperASR
    asr = FasterWhisperASR(
        model_size=config.WHISPER_MODEL,
        language=config.WHISPER_LANGUAGE,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )
else:
    from processing.recognition.whisper_asr import WhisperASR
    asr = WhisperASR(model_size=config.WHISPER_MODEL, language=config.WHISPER_LANGUAGE)
asr.load()

print("[2/3] 話者識別モデルをロード中...")
from resemblyzer import VoiceEncoder, preprocess_wav
encoder = VoiceEncoder()

print("[3/3] ウォームアップ中（初回のみ時間がかかります）...")
_dummy = np.zeros(config.SAMPLE_RATE * 3, dtype=np.float32)
asr.transcribe(_dummy, config.SAMPLE_RATE)

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
    return asr.transcribe(audio, config.SAMPLE_RATE)


def record_chunk() -> np.ndarray:
    frames = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    audio = sd.rec(frames, samplerate=config.SAMPLE_RATE, channels=1,
                   dtype="float32", device=mic_device_index)
    sd.wait()
    return audio[:, 0]


def normalize_audio(audio: np.ndarray) -> tuple:
    """
    ノイズ除去してからピーク音量基準で正規化する。
    マイクの物理的な感度が低く強い増幅が必要なため、増幅前にノイズ除去を挟むことで
    ノイズも一緒に増幅されてしまうのを軽減する。
    戻り値: (正規化後の音声, 適用した増幅率)
    """
    import noisereduce as nr
    denoised = nr.reduce_noise(y=audio, sr=config.SAMPLE_RATE)
    peak = float(np.max(np.abs(denoised))) or 1e-6
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return np.clip(denoised * gain, -1.0, 1.0), gain


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

            audio_amp, gain = await loop.run_in_executor(None, normalize_audio, audio)
            print(f"\n[音声検出 RMS={rms:.4f} gain={gain:.1f}倍] 認識中...")

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
