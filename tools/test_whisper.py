"""
マイクで録音 → Whisper で文字起こし の動作確認スクリプト。
使い方: python tools/test_whisper.py [録音秒数]
例:    python tools/test_whisper.py 5
"""
import sys
import os
import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from processing.recognition.whisper_asr import WhisperASR
import config

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 5

print("Whisper モデルをロード中... (初回は少し時間がかかります)")
asr = WhisperASR(model_size=config.WHISPER_MODEL, language=config.WHISPER_LANGUAGE)
asr.load()

print(f"\n録音開始（{DURATION}秒）... 話しかけてください")
audio = sd.rec(
    int(DURATION * config.SAMPLE_RATE),
    samplerate=config.SAMPLE_RATE,
    channels=1,
    dtype="float32",
    device=config.MIC_DEVICE_INDEX,
)
sd.wait()
print("録音完了。文字起こし中...")

audio_flat = audio[:, 0]
text = asr.transcribe(audio_flat, config.SAMPLE_RATE)

print()
print("=" * 40)
print(f"認識結果: {text if text else '（無音または認識できませんでした）'}")
print("=" * 40)
