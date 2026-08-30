"""
マイクの音量（Windowsの入力レベル）を実測で最適化する。

いくつかのレベルを順に試し、それぞれで録音して
「音量・音割れの有無・実際の認識結果」を並べて比べる。
一番よかったレベルをそのまま設定できる。

使い方: python tools/tune_mic_level.py
        1回だけ、通しで話し続ければ全レベル分をまとめて測れる。
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd
import soundfile as sf
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

import config
from input.mic_input import find_input_device

PHRASE = "テスト、テストです"
LEVELS = [60, 70, 80, 90, 100]   # 試すWindowsの入力レベル(%)
SECONDS = 4                       # 1レベルあたりの録音秒数
SR = 16000
SAVE_DIR = r"C:\Users\user\vosk-models"

# 理想の範囲。RMSは声の平均的な大きさ、ピークは一番大きい瞬間。
RMS_LOW, RMS_HIGH = 0.05, 0.15
PEAK_LIMIT = 0.95   # これを超えると音割れ（波形の頭が潰れる）


def get_volume_ctl():
    mic = AudioUtilities.GetMicrophone()
    iface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def native_channels(device_index):
    """2chデバイスを1chで開くと波形が壊れるため、必ずネイティブ値で開く。"""
    info = sd.query_devices(device_index) if device_index is not None else sd.query_devices(kind="input")
    return max(1, int(info["max_input_channels"]))


device_index = config.MIC_DEVICE_INDEX
if device_index is None:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
name = sd.query_devices(device_index)["name"] if device_index is not None else sd.query_devices(kind="input")["name"]

vol = get_volume_ctl()
original_level = vol.GetMasterVolumeLevelScalar()

print(f"録音デバイス: {device_index} - {name}")
print(f"現在の入力レベル: {original_level*100:.0f}%")
print()
print("=" * 60)
print(f"  {len(LEVELS)}種類の音量を順に試します（1つ{SECONDS}秒 × {len(LEVELS)}回）。")
print(f"  始まったら、最後まで止めずに")
print(f"  「{PHRASE}」 をくり返し言い続けてください。")
print("=" * 60)
input("\n準備ができたらEnterを押してください > ")

channels = native_channels(device_index)
results = []

try:
    for lv in LEVELS:
        vol.SetMasterVolumeLevelScalar(lv / 100.0, None)
        time.sleep(0.4)  # 設定が反映されるのを待つ

        stream = sd.InputStream(samplerate=SR, channels=channels, dtype="float32", device=device_index)
        stream.start()
        print(f"\n▶ 入力レベル {lv}% で録音中... 話し続けてください")
        frames = []
        for _ in range(SECONDS):
            audio, _ = stream.read(SR)
            frames.append(audio.mean(axis=1))
        stream.stop()
        stream.close()

        sig = np.concatenate(frames).astype(np.float32)
        path = os.path.join(SAVE_DIR, f"level_{lv}.wav")
        sf.write(path, sig, SR)

        rms = float(np.sqrt(np.mean(sig ** 2)))
        peak = float(np.max(np.abs(sig)))
        clipped = float(np.mean(np.abs(sig) > 0.99) * 100)
        results.append(dict(level=lv, rms=rms, peak=peak, clipped=clipped, path=path))
        print(f"   音量RMS={rms:.4f}  ピーク={peak:.3f}  音割れ={clipped:.2f}%")
finally:
    vol.SetMasterVolumeLevelScalar(original_level, None)
    print(f"\n（入力レベルをいったん元の {original_level*100:.0f}% に戻しました）")

# --- 認識してみる ---
print("\n" + "=" * 60)
print("それぞれの録音をVoskにかけます...")
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()

for r in results:
    sig, _ = sf.read(r["path"])
    sig = sig.astype(np.float32)
    p = float(np.max(np.abs(sig))) or 1e-6
    amp = np.clip(sig * min(0.7 / p, 20.0), -1.0, 1.0).astype(np.float32)
    r["text"] = asr.transcribe(amp, SR)

# --- まとめ ---
print("\n" + "=" * 60)
print(f"言った言葉: 「{PHRASE}」")
print("=" * 60)
print(f"{'レベル':>6} {'音量RMS':>8} {'ピーク':>7} {'音割れ':>7}  判定   認識結果")
print("-" * 60)

for r in results:
    if r["clipped"] > 0.1 or r["peak"] >= PEAK_LIMIT:
        verdict = "×割れ"
    elif r["rms"] < RMS_LOW:
        verdict = "△小さい"
    elif r["rms"] > RMS_HIGH:
        verdict = "△大きい"
    else:
        verdict = "○良好"
    r["verdict"] = verdict
    print(f"{r['level']:5d}% {r['rms']:8.4f} {r['peak']:7.3f} {r['clipped']:6.2f}%  {verdict:6s} 「{r['text']}」")

good = [r for r in results if r["verdict"] == "○良好"]
best = max(good, key=lambda r: r["rms"]) if good else \
       min((r for r in results if r["clipped"] <= 0.1), key=lambda r: abs(r["rms"] - 0.09), default=None)

print()
if best:
    print(f"おすすめ: {best['level']}%  （音量が理想の範囲で、音割れなし）")
    ans = input(f"\nこのレベル({best['level']}%)に設定しますか？ [y/N] > ").strip().lower()
    if ans == "y":
        vol.SetMasterVolumeLevelScalar(best["level"] / 100.0, None)
        print(f"設定しました: {vol.GetMasterVolumeLevelScalar()*100:.0f}%")
    else:
        print(f"変更しませんでした（{vol.GetMasterVolumeLevelScalar()*100:.0f}% のまま）")
else:
    print("どのレベルも理想の範囲に入りませんでした。マイクとの距離を見直してください。")
