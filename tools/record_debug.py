"""
デバッグ用: run.pyと同じ方法でマイクから20秒録音してWAVに保存し、
その場でVosk(バッチ)にかけて「録れている音が本当に認識可能か」を検証する。
使い方: python tools/record_debug.py
実行したらすぐマイクに向かって話し続けること。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd
import soundfile as sf

import config
from input.mic_input import find_input_device

RECORD_SECONDS = 20
OUT_WAV = r"C:\Users\user\vosk-models\debug_capture.wav"  # 非ASCIIパス問題を避けるためモデルと同じ場所

# run.pyと同じデバイス解決
if config.MIC_DEVICE_INDEX is not None:
    device_index = config.MIC_DEVICE_INDEX
else:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
name = sd.query_devices(device_index)["name"] if device_index is not None else sd.query_devices(kind="input")["name"]
print(f"録音デバイス: {device_index} - {name}")

# run.pyと同じ開きっぱなしInputStream方式
stream = sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32", device=device_index)
stream.start()
print(f"\n=== 録音開始({RECORD_SECONDS}秒間)。マイクに向かって話し続けてください ===")
frames = []
for i in range(RECORD_SECONDS):
    audio, overflowed = stream.read(config.SAMPLE_RATE)
    frames.append(audio[:, 0])
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"  {i+1:2d}秒: RMS={rms:.4f}")
stream.stop()
stream.close()

audio = np.concatenate(frames)
sf.write(OUT_WAV, audio, config.SAMPLE_RATE)
print(f"\n保存: {OUT_WAV}")
print(f"全体RMS={float(np.sqrt(np.mean(audio**2))):.4f} ピーク={float(np.max(np.abs(audio))):.4f}")

print("\n=== Vosk(バッチ)で認識テスト ===")
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()

# 生のまま
text_raw = asr.transcribe(audio, config.SAMPLE_RATE)
print(f"認識結果(生のまま): 「{text_raw}」")

# ピーク正規化(音割れなし増幅)してから
peak = float(np.max(np.abs(audio))) or 1e-6
gain = min(0.7 / peak, 50.0)
text_amp = asr.transcribe(np.clip(audio * gain, -1.0, 1.0), config.SAMPLE_RATE)
print(f"認識結果(増幅{gain:.1f}倍): 「{text_amp}」")
