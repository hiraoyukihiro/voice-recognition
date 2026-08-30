"""
デバッグ用: 決まった言葉を自分のタイミングで録音し、その場でVoskにかけて比べる。

背景: 「テスト、テストです」と言うと必ず「ベスト、ベストです」になる現象を追うために作った。
合成音声（＝Voskが完璧に認識できる音）と同じ言葉を、実際のマイクで録って比較する。

使い方: python tools/record_phrase.py
        Enterを押してから話し始める。録音は保存されるので後から何度でも解析できる。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd
import soundfile as sf

import config
from input.mic_input import find_input_device

PHRASE = "テスト、テストです"
RECORD_SECONDS = 6
SR = 16000
OUT_WAV = r"C:\Users\user\vosk-models\phrase_capture.wav"


def native_channels(device_index):
    """2chデバイスを1chで開くと波形が壊れるため、必ずネイティブ値で開く（2026-08-27の教訓）。"""
    info = sd.query_devices(device_index) if device_index is not None else sd.query_devices(kind="input")
    return max(1, int(info["max_input_channels"]))


device_index = config.MIC_DEVICE_INDEX
if device_index is None:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
name = sd.query_devices(device_index)["name"] if device_index is not None else sd.query_devices(kind="input")["name"]

print(f"録音デバイス: {device_index} - {name}")
print()
print("=" * 55)
print(f"  これから {RECORD_SECONDS}秒 録音します。")
print(f"  Enterを押したら、いつもの距離・いつもの話し方で")
print(f"  「{PHRASE}」 を2〜3回くり返してください。")
print("=" * 55)
input("\n準備ができたらEnterを押してください > ")

stream = sd.InputStream(samplerate=SR, channels=native_channels(device_index),
                        dtype="float32", device=device_index)
stream.start()
print("\n▶ 録音中... 話してください！")
frames = []
for i in range(RECORD_SECONDS):
    audio, _ = stream.read(SR)
    frames.append(audio.mean(axis=1))
    rms = float(np.sqrt(np.mean(audio ** 2)))
    bar = "#" * min(int(rms * 200), 40)
    print(f"  残り{RECORD_SECONDS - i - 1}秒  音量={rms:.4f} {bar}")
stream.stop()
stream.close()

mic = np.concatenate(frames).astype(np.float32)
sf.write(OUT_WAV, mic, SR)
print(f"\n■ 録音終了。保存: {OUT_WAV}")

rms = float(np.sqrt(np.mean(mic ** 2)))
print(f"  全体の音量(RMS): {rms:.4f}  ピーク: {float(np.max(np.abs(mic))):.3f}")
if rms < 0.01:
    print("  ⚠️ 音量が小さすぎます。声が入っていない可能性があります。もう一度お試しください。")

print("\n" + "=" * 55)
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()

peak = float(np.max(np.abs(mic))) or 1e-6
amp = np.clip(mic * min(0.7 / peak, 50.0), -1.0, 1.0).astype(np.float32)

print(f"\n言った言葉 : 「{PHRASE}」")
print(f"認識結果   : 「{asr.transcribe(amp, SR)}」")
