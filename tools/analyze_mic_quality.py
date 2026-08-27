"""
デバッグ用: マイク録音を1回だけ行って保存し、
「合成音声(Voskが完璧に認識できる基準音)」と特性を比較する。

背景: Voskは合成音声(TTS)をほぼ完璧に認識できるのに、
同じ設定でマイク録音だと全く認識できない。音量もスペクトル重心も正常範囲なので、
別の要因(残響・雑音・マイクのDSP加工・声の距離)を数値で切り分ける。

使い方: python tools/analyze_mic_quality.py  （実行後すぐ話し続ける）
保存先: C:\\Users\\user\\vosk-models\\mic_capture.wav （以後は録音なしで再解析できる）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sounddevice as sd
import soundfile as sf

import config
from input.mic_input import find_input_device

RECORD_SECONDS = 12
SR = 16000
OUT_WAV = r"C:\Users\user\vosk-models\mic_capture.wav"
TTS_WAV = r"C:\Users\user\vosk-models\tts_test.wav"


def analyze(sig, label):
    """音声の品質指標を出す。TTS(認識できる音)との比較用。"""
    rms = float(np.sqrt(np.mean(sig ** 2)))
    peak = float(np.max(np.abs(sig)))

    # フレームごとのRMSから、発話区間と無音区間を分けてSNRを推定する
    win = 400  # 25ms
    n = len(sig) // win
    frame_rms = np.array([np.sqrt(np.mean(sig[i * win:(i + 1) * win] ** 2)) for i in range(n)])
    speech_level = float(np.percentile(frame_rms, 90))   # 発話中とみなす
    noise_level = float(np.percentile(frame_rms, 10))    # 無音中とみなす
    snr_db = 20 * np.log10((speech_level + 1e-9) / (noise_level + 1e-9))

    # ダイナミクス（AGC/圧縮がかかっていると小さくなる）
    dynamic_db = 20 * np.log10((float(np.percentile(frame_rms, 95)) + 1e-9)
                               / (float(np.percentile(frame_rms, 50)) + 1e-9))

    spec = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(len(sig), 1 / SR)
    total = spec.sum() or 1e-9
    centroid = float((freqs * spec).sum() / total)
    # スペクトル平坦度: 1に近いほどノイズ的、0に近いほど倍音構造のある声
    p = spec / total
    flatness = float(np.exp(np.mean(np.log(p + 1e-12))) / (np.mean(p) + 1e-12))

    print(f"\n--- {label} ---")
    print(f"  RMS              : {rms:.4f}   ピーク: {peak:.3f}")
    print(f"  推定SNR          : {snr_db:5.1f} dB   (声と雑音の差。20dB以上が望ましい)")
    print(f"  声の抑揚(ダイナミクス): {dynamic_db:5.1f} dB   (小さすぎるとAGCで潰れている)")
    print(f"  スペクトル重心     : {centroid:5.0f} Hz")
    print(f"  スペクトル平坦度   : {flatness:.4f} (0に近い=声らしい / 1に近い=ノイズ的)")
    return dict(rms=rms, snr=snr_db, centroid=centroid, flatness=flatness)


# --- 録音 ---
if config.MIC_DEVICE_INDEX is not None:
    device_index = config.MIC_DEVICE_INDEX
else:
    device_index = find_input_device(config.MIC_DEVICE_NAME)
name = sd.query_devices(device_index)["name"] if device_index is not None else sd.query_devices(kind="input")["name"]
print(f"録音デバイス: {device_index} - {name}")

stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", device=device_index)
stream.start()
print(f"\n=== 録音開始({RECORD_SECONDS}秒)。マイクに向かって普通の声で話し続けてください ===")
frames = []
for i in range(RECORD_SECONDS):
    audio, _ = stream.read(SR)
    frames.append(audio[:, 0])
    print(f"  {i+1:2d}秒: RMS={float(np.sqrt(np.mean(audio ** 2))):.4f}")
stream.stop()
stream.close()

mic = np.concatenate(frames).astype(np.float32)
sf.write(OUT_WAV, mic, SR)
print(f"\n保存: {OUT_WAV}")

# --- 比較解析 ---
print("\n" + "=" * 60)
print("Voskが完璧に認識できた合成音声(基準)と比較します")
print("=" * 60)
analyze(mic, "マイク録音")
if os.path.exists(TTS_WAV):
    tts, _ = sf.read(TTS_WAV)
    analyze(tts.astype(np.float32), "合成音声(認識成功した基準)")

# --- 認識テスト ---
print("\n" + "=" * 60)
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
asr.load()
peak = float(np.max(np.abs(mic))) or 1e-6
amp = np.clip(mic * min(0.7 / peak, 50.0), -1.0, 1.0).astype(np.float32)
print(f"\n認識結果: 「{asr.transcribe(amp, SR)}」")
