"""
ステップ4: マイク → Whisper文字起こし + 話者分離 → ブラウザ字幕表示
実行: python run_step4.py
ブラウザで http://localhost:8080 を開いておくこと。
"""
import asyncio
import sys
import traceback
import numpy as np
import sounddevice as sd
import websockets
import json
import config

SILENCE_THRESHOLD = 0.003
OVERLAP_RMS_RATIO = 2.0
AUDIO_GAIN = 10.0  # マイク音量が小さい場合の増幅倍率

print(f"Whisperモデル [{config.WHISPER_MODEL}] をロード中...")
import whisper
from resemblyzer import VoiceEncoder, preprocess_wav

asr_model = whisper.load_model(config.WHISPER_MODEL)
encoder = VoiceEncoder()

# Numba JITコンパイルを起動時に済ませる（初回処理の詰まりを防ぐ）
print("ウォームアップ中...")
_dummy = np.zeros(config.SAMPLE_RATE * 3, dtype=np.float32)
asr_model.transcribe(_dummy, language=config.WHISPER_LANGUAGE, fp16=False, verbose=False)
print("ロード完了\n")

# 話者管理
speaker_embeddings: dict[str, np.ndarray] = {}
speaker_count = 0
SIMILARITY_THRESHOLD = 0.75
last_speaker_id: str = "speaker_1"
last_rms: float = 0.0

clients: set = set()

_direction = 0.0
def get_dummy_direction() -> float:
    global _direction
    _direction = (_direction + 30) % 360
    return _direction


def identify_speaker(audio: np.ndarray, current_rms: float) -> str:
    global speaker_count, last_speaker_id, last_rms
    try:
        if last_rms > SILENCE_THRESHOLD and current_rms > last_rms * OVERLAP_RMS_RATIO:
            print(f"  → 同時発話の可能性: {last_speaker_id} を維持")
            return last_speaker_id

        wav = preprocess_wav(audio, source_sr=config.SAMPLE_RATE)
        if len(wav) < config.SAMPLE_RATE * 0.5:  # 0.5秒未満はスキップ
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
            print(f"  → 新しい話者: {best_id}")

        last_speaker_id = best_id
        return best_id

    except Exception as e:
        print(f"  → 話者識別エラー（スキップ）: {e}")
        return last_speaker_id


async def ws_server(websocket, path=None):
    clients.add(websocket)
    print(f"ブラウザ接続 (計{len(clients)}台)")
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)


async def broadcast(payload: dict):
    if not clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)


def record_chunk(duration: float) -> np.ndarray:
    frames = int(config.SAMPLE_RATE * duration)
    audio = sd.rec(frames, samplerate=config.SAMPLE_RATE, channels=1,
                   dtype="float32", device=config.MIC_DEVICE_INDEX)
    sd.wait()
    return audio[:, 0]


def transcribe(audio: np.ndarray) -> str:
    result = asr_model.transcribe(
        audio,
        language=config.WHISPER_LANGUAGE,
        fp16=False,
        verbose=False,
        condition_on_previous_text=False,  # 前の文脈に引きずられないようにする
    )
    return result["text"].strip()


async def pipeline_loop():
    global last_rms
    print(f"録音開始 (チャンク={config.CHUNK_DURATION}秒, モデル={config.WHISPER_MODEL})")
    print("話しかけてください（Ctrl+C で停止）\n")
    loop = asyncio.get_event_loop()

    while True:
        try:
            audio = await loop.run_in_executor(None, record_chunk, config.CHUNK_DURATION)
            rms = float(np.sqrt(np.mean(audio ** 2)))

            if rms < SILENCE_THRESHOLD:
                print(".", end="", flush=True)
                last_rms = 0.0
                continue

            audio_amplified = np.clip(audio * AUDIO_GAIN, -1.0, 1.0)
            amp_rms = float(np.sqrt(np.mean(audio_amplified ** 2)))
            print(f"\n[RMS={rms:.4f}→{amp_rms:.4f}] 認識中...")
            text = await loop.run_in_executor(None, transcribe, audio_amplified)
            if not text:
                last_rms = rms
                continue

            speaker_id = await loop.run_in_executor(None, identify_speaker, audio_amplified, rms)
            last_rms = rms
            direction = get_dummy_direction()

            print(f"[{speaker_id} | {direction:.0f}°] {text}")
            await broadcast({
                "type": "subtitle",
                "speaker_id": speaker_id,
                "text": text,
                "direction": direction,
            })

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"\n[エラー・次のチャンクへ] {e}")
            traceback.print_exc()
            continue


async def main():
    for attempt in range(10):
        try:
            server = await websockets.serve(ws_server, config.WEBSOCKET_HOST, config.WEBSOCKET_PORT)
            break
        except OSError:
            print(f"ポート {config.WEBSOCKET_PORT} 使用中... 待機中 ({attempt+1}秒)")
            await asyncio.sleep(1)
    else:
        print(f"エラー: ポート {config.WEBSOCKET_PORT} を開放できませんでした。")
        sys.exit(1)

    print(f"WebSocket起動: ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    print(f"ブラウザ: http://localhost:{config.WEB_PORT}\n")

    try:
        await pipeline_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n停止しました。")
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
