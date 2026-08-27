"""
デバッグ用: reSpeakerの複数の入り口(ホストAPI × チャンネル)から同時に録音し、
どれが本当に認識可能な音声を出しているかをVoskで比較する。

背景: WASAPI経由ch0の録音は音量は正常なのに7.7kHz付近に声と連動した強いピークがあり、
Voskが全く認識できなかった。Windowsの「エコーキャンセルスピーカーフォン」加工や
チャンネル選択が原因の可能性があるため、他の経路と比較する。

使い方: python tools/compare_endpoints.py  （実行後すぐ話し続ける）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd

import config

RECORD_SECONDS = 10
SR = 16000

# (ラベル, デバイス番号) — 同じreSpeakerの別ホストAPI経由の入り口
CANDIDATES = [
    ("WASAPI", 15),
    ("WDM-KS", 19),
]


def record(device, seconds, channels=2):
    """指定デバイスから指定チャンネル数で録音して返す。失敗したらNone。"""
    try:
        stream = sd.InputStream(samplerate=SR, channels=channels, dtype="float32", device=device)
        stream.start()
        frames = []
        for _ in range(seconds):
            audio, _ = stream.read(SR)
            frames.append(audio)
        stream.stop()
        stream.close()
        return np.concatenate(frames)
    except Exception as e:
        print(f"    録音失敗: {type(e).__name__}: {e}")
        return None


def describe(sig):
    """音量と、声の帯域らしさ（スペクトル重心）を返す。"""
    rms = float(np.sqrt(np.mean(sig ** 2)))
    spec = np.abs(np.fft.rfft(sig[:SR * 5]))
    freqs = np.fft.rfftfreq(len(sig[:SR * 5]), 1 / SR)
    total = spec.sum() or 1e-9
    centroid = float((freqs * spec).sum() / total)
    high_ratio = float(spec[freqs >= 6000].sum() / total)
    return rms, centroid, high_ratio


def normalize(sig):
    peak = float(np.max(np.abs(sig))) or 1e-6
    return np.clip(sig * min(0.7 / peak, 50.0), -1.0, 1.0).astype(np.float32)


recordings = {}
for label, dev in CANDIDATES:
    print(f"\n=== {label} (device {dev}) から{RECORD_SECONDS}秒録音します。話し続けてください ===")
    data = record(dev, RECORD_SECONDS)
    if data is None:
        continue
    for ch in range(data.shape[1]):
        recordings[f"{label}-ch{ch}"] = data[:, ch].copy()
    # 2chの差分（ビームフォーミングの副産物が片方に入っている場合の切り分け用）
    if data.shape[1] == 2:
        recordings[f"{label}-ch0+ch1"] = (data[:, 0] + data[:, 1]) / 2

print("\n" + "=" * 60)
print("Voskモデルをロードして各経路を認識してみます...")
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()

print("\n" + "=" * 60)
print(f"{'経路':<16} {'RMS':>7} {'重心Hz':>7} {'6k以上%':>8}  認識結果")
print("-" * 60)
for name, sig in recordings.items():
    rms, centroid, high = describe(sig)
    text = asr.transcribe(normalize(sig), SR)
    print(f"{name:<16} {rms:7.4f} {centroid:7.0f} {high*100:7.1f}%  「{text}」")

print("\n重心が300-1500Hz・6k以上が数%程度の経路が「正常な声」です。")
