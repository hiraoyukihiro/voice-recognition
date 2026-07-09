"""話者分離の抽象基底クラス。"""
from abc import ABC, abstractmethod
import numpy as np


class DiarizationBase(ABC):
    @abstractmethod
    def load(self) -> None:
        """モデルのロード"""

    @abstractmethod
    def identify(self, audio: np.ndarray, sample_rate: int) -> str:
        """
        音声データから話者IDを返す。
        戻り値: "speaker_0", "speaker_1" などの文字列
        同一話者には同じIDが返り続けるよう実装する。
        """
