"""
2チャンネルのマイクで「1本目だけ」「2本目だけ」「平均」のどれが一番よく認識できるかを比べる。

背景: reSpeakerのような機器は2本のチャンネルに別々の役割を持たせている場合がある。
      両方同じ音なら平均した方が雑音が減るが、片方が加工前の生音だった場合、
      平均するとせっかくの加工済み音を汚すことになる。実測で決める。

使い方: python tools/compare_channels.py
        Enterを押してから、決まった言葉をくり返し言う。
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
SECONDS = 6
SR = 16000
OUT = r"C:\Users\user\vosk-models\channels_capture.wav"

device_index = config.MIC_DEVICE_INDEX
if device_index is None:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
info = sd.query_devices(device_index) if device_index is not None else sd.query_devices(kind="input")
channels = max(1, int(info["max_input_channels"]))

print(f"録音デバイス: {info['name']}")
print(f"チャンネル数: {channels}")
if channels < 2:
    print("\nこのマイクは1チャンネルなので、比べる意味がありません。終了します。")
    sys.exit(0)

print()
print("=" * 55)
print(f"  {SECONDS}秒 録音します。Enterを押したら")
print(f"  「{PHRASE}」 をくり返し言ってください。")
print("=" * 55)
input("\n準備ができたらEnterを押してください > ")

stream = sd.InputStream(samplerate=SR, channels=channels, dtype="float32", device=device_index)
stream.start()
print("\n▶ 録音中... 話してください！")
frames = []
for i in range(SECONDS):
    audio, _ = stream.read(SR)
    frames.append(audio)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"  残り{SECONDS - i - 1}秒  音量={rms:.4f} {'#' * min(int(rms * 200), 40)}")
stream.stop()
stream.close()

data = np.concatenate(frames).astype(np.float32)
sf.write(OUT, data, SR)   # 2ch のまま保存（後から何度でも比べられる）
print(f"\n■ 録音終了。保存: {OUT}")

# --- 比べる ---
cands = {
    "1本目だけ": data[:, 0],
    "2本目だけ": data[:, 1],
    "2本の平均（今のアプリ）": data.mean(axis=1),
    "2本の差分": data[:, 0] - data[:, 1],   # 参考: 完全に同じなら無音になる
}

print("\n" + "=" * 55)
print("それぞれの特徴")
print("=" * 55)
for name, sig in cands.items():
    rms = float(np.sqrt(np.mean(sig ** 2)))
    print(f"  {name:24s} 音量RMS={rms:.4f}")

corr = float(np.corrcoef(data[:, 0], data[:, 1])[0, 1])
print(f"\n  1本目と2本目の似ている度: {corr:.4f}")
print("   （1.0に近い＝ほぼ同じ音 / 低い＝別の役割を持っている）")

print("\n" + "=" * 55)
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()

print(f"\n言った言葉: 「{PHRASE}」")
print("-" * 55)
for name, sig in cands.items():
    if name == "2本の差分":
        continue  # 参考値なので認識はしない
    p = float(np.max(np.abs(sig))) or 1e-6
    amp = np.clip(sig * min(0.7 / p, 20.0), -1.0, 1.0).astype(np.float32)
    print(f"  {name:24s}「{asr.transcribe(amp, SR)}」")
