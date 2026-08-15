"""テスト用ダミー入力（サイン波やホワイトノイズを生成）。"""
import numpy as np
from .base import AudioInputBase


class DummyInput(AudioInputBase):
    def __init__(self, sample_rate: int = 16000, mode: str = "sine"):
        """
        mode: "sine" = 440Hzサイン波, "noise" = ホワイトノイズ, "silence" = 無音
        """
        super().__init__(sample_rate, channels=1)
        self.mode = mode
        self._t = 0

    def start(self) -> None:
        print(f"[DummyInput] 開始 (mode={self.mode})")

    def stop(self) -> None:
        print("[DummyInput] 停止")

    def read_chunk(self, duration: float) -> np.ndarray:
        frames = int(self.sample_rate * duration)
        t = np.linspace(self._t, self._t + duration, frames, endpoint=False)
        self._t += duration
        if self.mode == "sine":
            return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        elif self.mode == "noise":
            return (0.1 * np.random.randn(frames)).astype(np.float32)
        else:
            return np.zeros(frames, dtype=np.float32)
