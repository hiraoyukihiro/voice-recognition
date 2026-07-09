"""
メインパイプライン。
入力 → 処理（方向検知 + 音声認識 + 話者分離） → 出力 を繋ぐ。
"""
import asyncio
import numpy as np

import config
from input import MicInput, FileInput, DummyInput
from processing.direction.dummy_doa import DummyDOA
from processing.recognition.whisper_asr import WhisperASR
from processing.diarization.resemblyzer_diarizer import ResemblyzerDiarizer
from output.browser_display import BrowserDisplay
from output.base import SubtitleEvent


def build_input(mode: str = "mic"):
    if mode == "mic":
        return MicInput(
            sample_rate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            device_index=config.MIC_DEVICE_INDEX,
        )
    elif mode == "dummy":
        return DummyInput(sample_rate=config.SAMPLE_RATE, mode="sine")
    elif mode == "file":
        import sys
        path = sys.argv[2] if len(sys.argv) > 2 else "test_audio/sample.wav"
        return FileInput(file_path=path, sample_rate=config.SAMPLE_RATE)
    raise ValueError(f"未知の入力モード: {mode}")


async def pipeline(audio_input, doa, asr, diarizer, display):
    """音声チャンクを処理して表示に送るメインループ。"""
    print("[Pipeline] 開始。Ctrl+C で停止。")
    while True:
        # 1. 音声取得
        audio: np.ndarray = audio_input.read_chunk(config.CHUNK_DURATION)

        # 無音スキップ（RMSが閾値未満）
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.01:
            await asyncio.sleep(0.05)
            continue

        # 2. 方向推定
        direction = doa.estimate(audio)

        # 3. 音声認識
        text = asr.transcribe(audio, config.SAMPLE_RATE)
        if not text:
            continue

        # 4. 話者分離
        speaker_id = diarizer.identify(audio, config.SAMPLE_RATE)

        print(f"[{speaker_id}] 方向:{direction:.0f}° | {text}")

        # 5. 表示に送信
        event = SubtitleEvent(speaker_id=speaker_id, text=text, direction=direction)
        await display.send(event)

        await asyncio.sleep(0)


async def main(input_mode: str = "mic"):
    # --- コンポーネント初期化 ---
    audio_input = build_input(input_mode)
    doa = DummyDOA(mode="sweep")
    asr = WhisperASR(model_size=config.WHISPER_MODEL, language=config.WHISPER_LANGUAGE)
    diarizer = ResemblyzerDiarizer()
    display = BrowserDisplay(host=config.WEBSOCKET_HOST, port=config.WEBSOCKET_PORT)

    asr.load()
    diarizer.load()
    await display.start()
    audio_input.start()

    try:
        await pipeline(audio_input, doa, asr, diarizer, display)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[Server] 停止中...")
    finally:
        audio_input.stop()
        await display.stop()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "mic"
    asyncio.run(main(mode))
