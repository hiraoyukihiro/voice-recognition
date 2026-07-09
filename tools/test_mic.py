"""
マイク録音 → WAV保存 → 即再生 の動作確認スクリプト。
使い方: python tools/test_mic.py [秒数] [デバイス番号]
例:    python tools/test_mic.py 5
       python tools/test_mic.py 5 2
"""
import sys
import os
import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 5
DEVICE = int(sys.argv[2]) if len(sys.argv) > 2 else None
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "test_audio", "mic_test.wav")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

print(f"録音開始（{DURATION}秒）... 話しかけてください")
audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
    device=DEVICE,
)
sd.wait()
print("録音完了")

# RMSで音量確認
rms = float(np.sqrt(np.mean(audio ** 2)))
print(f"音量（RMS）: {rms:.4f}  ", end="")
if rms < 0.001:
    print("← ほぼ無音。マイクが認識されていない可能性があります。")
elif rms < 0.01:
    print("← やや小さい。マイクの音量設定を上げてみてください。")
else:
    print("← OK")

# WAV保存
sf.write(OUT_PATH, audio, SAMPLE_RATE)
print(f"WAV保存: {OUT_PATH}")

# 即再生
print("再生中...")
sd.play(audio, samplerate=SAMPLE_RATE)
sd.wait()
print("完了。録音した音声が聞こえましたか？")
print()
print("次のステップ: python tools/test_mic.py で問題なければステップ3へ進めます。")
