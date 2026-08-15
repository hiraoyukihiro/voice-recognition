"""
マイクの録音方式を検証する診断ツール(先生からの引き継ぎ資料 why-we-changed.pdf より作成)。

背景: run.py は「sd.InputStream はこの環境で無音になる」という理由で
sd.rec() による毎回開き直し方式を使っていたが、実際にはホストAPIが
DirectSound の場合にのみ発生するバグで、WASAPI/MME 経由なら開きっぱなし
方式が正常に動くことを本ツールで確認済み(2026-08-15)。

使い方: python tools/check_mic_gap.py
"""
import sys
import time
import numpy as np
import sounddevice as sd

sys.path.insert(0, ".")
import config

PREFERRED_STREAM_HOSTAPIS = ("Windows WASAPI", "MME")  # DirectSoundは意図的に除外(無音バグのため)


def find_streaming_capable_device(name_substr: str):
    hostapis = sd.query_hostapis()
    devices = sd.query_devices()
    for hostapi_name in PREFERRED_STREAM_HOSTAPIS:
        for idx, d in enumerate(devices):
            if d["max_input_channels"] <= 0:
                continue
            if name_substr not in d["name"]:
                continue
            if hostapis[d["hostapi"]]["name"] == hostapi_name:
                return idx, hostapi_name
    return None, None


def main():
    if config.MIC_DEVICE_INDEX is not None:
        dev = config.MIC_DEVICE_INDEX
        hostapi_name = sd.query_hostapis()[sd.query_devices(dev)["hostapi"]]["name"]
    else:
        dev, hostapi_name = find_streaming_capable_device(config.MIC_DEVICE_NAME)
    print(f"使用デバイス: {dev} ({hostapi_name}) {sd.query_devices(dev)['name'] if dev is not None else ''}")

    N, SR = 16000 * 9, 16000  # 9秒分

    print("\n[A] 毎回開き直す方法 (旧run.pyのrecord_chunk()相当)")
    t = time.perf_counter()
    chunks_a = []
    for _ in range(30):
        c = sd.rec(int(SR * 0.3), samplerate=SR, channels=1, dtype="float32", device=dev)
        sd.wait()
        chunks_a.append(c[:, 0])
    a = time.perf_counter() - t
    audio_a = np.concatenate(chunks_a)

    print("[B] 開きっぱなしの方法 (RawInputStream, WASAPI/MME限定)")
    t = time.perf_counter()
    s = sd.RawInputStream(samplerate=SR, blocksize=512, channels=1, dtype="int16", device=dev)
    s.start()
    raw_frames = []
    for _ in range(N // 512):
        data, _ = s.read(512)
        raw_frames.append(np.frombuffer(data, dtype=np.int16))
    s.stop()
    s.close()
    b = time.perf_counter() - t
    audio_b = np.concatenate(raw_frames).astype(np.float32) / 32768.0

    print(f"\n[A] 9.0秒分を録るのに {a:.2f}秒 → 消えた音 {max(0, a - 9):.2f}秒 ({max(0, a - 9) / 9 * 100:.0f}%)")
    print(f"    実際に録れた音: peak={np.max(np.abs(audio_a)):.4f} rms={np.sqrt(np.mean(audio_a**2)):.4f}")
    print(f"[B] 9.0秒分を録るのに {b:.2f}秒 → 消えた音 {max(0, b - 9):.2f}秒 ({max(0, b - 9) / 9 * 100:.0f}%)")
    print(f"    実際に録れた音: peak={np.max(np.abs(audio_b)):.4f} rms={np.sqrt(np.mean(audio_b**2)):.4f}")
    print("\n(peak/rmsが完全に0.0000ならホストAPI側の無音バグが再発している可能性あり)")


if __name__ == "__main__":
    main()
