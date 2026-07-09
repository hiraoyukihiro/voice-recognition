"""
ステップ3: マイク → Whisper文字起こし → ブラウザ字幕表示
実行: python run_step3.py
ブラウザで output/web/index.html を開いておくこと。
"""
import asyncio
import numpy as np
import sounddevice as sd
import websockets
import json
import config

SILENCE_THRESHOLD = 0.008   # これ以下のRMSは無音とみなしてスキップ

print("Whisper モデルをロード中... (初回はモデルDLが入ります)")
import whisper
model = whisper.load_model(config.WHISPER_MODEL)
print(f"ロード完了 [{config.WHISPER_MODEL}]\n")

# 接続中のブラウザクライアント
clients: set = set()


async def ws_server(websocket, path=None):
    clients.add(websocket)
    print(f"ブラウザ接続 (計{len(clients)}台)")
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)
        print(f"ブラウザ切断 (残{len(clients)}台)")


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


# 方向はダミー（ステップ5で本物に差し替え）
_direction = 0.0
def get_dummy_direction() -> float:
    global _direction
    _direction = (_direction + 30) % 360
    return _direction


async def recognition_loop():
    print(f"録音開始。話しかけてください（Ctrl+C で停止）\n")
    loop = asyncio.get_event_loop()

    while True:
        # 録音はブロッキングなので別スレッドで実行
        audio = await loop.run_in_executor(None, record_chunk, config.CHUNK_DURATION)

        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < SILENCE_THRESHOLD:
            print(".", end="", flush=True)  # 無音は点で表示
            continue

        print(f"\n[録音中 RMS={rms:.4f}] 認識中...")

        # Whisper文字起こし（CPUなのでブロッキング→別スレッドで）
        result = await loop.run_in_executor(
            None,
            lambda: model.transcribe(audio, language=config.WHISPER_LANGUAGE, fp16=False, verbose=False)
        )
        text = result["text"].strip()
        if not text:
            continue

        direction = get_dummy_direction()
        print(f"[speaker_1 | {direction:.0f}°] {text}")

        await broadcast({
            "type": "subtitle",
            "speaker_id": "speaker_1",
            "text": text,
            "direction": direction,
        })


async def main():
    server = await websockets.serve(ws_server, config.WEBSOCKET_HOST, config.WEBSOCKET_PORT)
    print(f"WebSocket起動: ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    print(f"ブラウザで output/web/index.html を開いてください\n")

    try:
        await recognition_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n停止しました。")
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
