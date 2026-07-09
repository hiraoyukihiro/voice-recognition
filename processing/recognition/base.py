"""音声認識（ASR）の抽象基底クラス。"""
from abc import ABC, abstractmethod
import numpy as np


class TranscriberBase(ABC):
    @abstractmethod
    def load(self) -> None:
        """モデルのロード（起動時に一度だけ呼ぶ）"""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """
        音声データをテキストに変換して返す。
        audio: shape=(samples,), dtype=float32
        """
