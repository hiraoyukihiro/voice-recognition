"""PC内蔵マイク（またはUSBマイク）からの音声入力。"""
import numpy as np
import sounddevice as sd
from .base import AudioInputBase


def find_input_device(name_substr: str, prefer_hostapis: tuple = ("Windows WASAPI", "MME", "Windows DirectSound")) -> int | None:
    """
    名前の一部とホストAPIの優先順位からマイクのデバイス番号を解決する。
    USBデバイスの抜き差しで sounddevice のデバイス番号やMMEの既定デバイスが
    無音になる不具合が確認されたため、番号固定ではなく名前+ホストAPIで検索する。
    見つからない場合は None を返す（呼び出し側は config.MIC_DEVICE_INDEX にフォールバック）。

    優先順位はWASAPI/MMEを先にしている。DirectSound経由のreSpeakerは
    sd.rec()等の単発録音では問題ないが、InputStreamで開きっぱなしにして
    read()し続けると即座に無音データを返し続ける不具合を確認したため
    （tools/check_mic_gap.py で検証済み、2026-08-15）、開きっぱなし方式の
    既定候補からは外している。
    """
    hostapis = sd.query_hostapis()
    devices = sd.query_devices()
    for hostapi_name in prefer_hostapis:
        for idx, d in enumerate(devices):
            if d["max_input_channels"] <= 0:
                continue
            if name_substr not in d["name"]:
                continue
            if hostapis[d["hostapi"]]["name"] == hostapi_name:
                return idx
    return None


class MicInput(AudioInputBase):
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index=None):
        super().__init__(sample_rate, channels)
        self.device_index = device_index
        self._stream = None

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            device=self.device_index,
        )
        self._stream.start()
        print(f"[MicInput] 開始 (device={self.device_index}, {self.sample_rate}Hz)")

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        print("[MicInput] 停止")

    def read_chunk(self, duration: float) -> np.ndarray:
        frames = int(self.sample_rate * duration)
        data, _ = self._stream.read(frames)
        return data[:, 0]  # モノラルに変換
