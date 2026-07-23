"""
Voskの動作確認スクリプト。
モデルのロード確認と、実際にマイクから数秒録音して文字起こしできるかを確認する。
使い方: python tools/check_vosk.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd

import config
from input.mic_input import find_input_device
from processing.recognition.vosk_asr import VoskASR

RECORD_SECONDS = 4

print("=== 1. Voskモデルのロード確認 ===")
print(f"モデルパス: {config.VOSK_MODEL_PATH}")
if not os.path.isdir(config.VOSK_MODEL_PATH):
    print("NG: モデルフォルダが見つかりません。config.VOSK_MODEL_PATH を確認してください。")
    sys.exit(1)

asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
try:
    asr.load()
    print("OK: モデルをロードできました")
except Exception as e:
    print(f"NG: モデルのロードに失敗しました: {e}")
    sys.exit(1)

print("\n=== 2. マイクデバイスの解決 ===")
if config.MIC_DEVICE_INDEX is not None:
    device_index = config.MIC_DEVICE_INDEX
else:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
print(f"使用デバイス: {device_index if device_index is not None else 'システムデフォルト'}")

print(f"\n=== 3. {RECORD_SECONDS}秒間の録音＋文字起こし ===")
input(f"Enterを押したら録音開始。{RECORD_SECONDS}秒間、マイクに向かって話してください...")

frames = int(config.SAMPLE_RATE * RECORD_SECONDS)
audio = sd.rec(frames, samplerate=config.SAMPLE_RATE, channels=1, dtype="float32", device=device_index)
sd.wait()
audio = audio[:, 0]

rms = float(np.sqrt(np.mean(audio ** 2)))
print(f"録音完了（RMS={rms:.4f}）")
if rms < 0.001:
    print("警告: 音量がほぼ無音です。マイクが正しく選択されているか確認してください。")

text = asr.transcribe(audio, config.SAMPLE_RATE)
print(f"\n認識結果: 「{text}」")
print("\n完了。結果が空欄や明らかにおかしい場合は、マイクの選択・音量・雑音を見直してください。")
