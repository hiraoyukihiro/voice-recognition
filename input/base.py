"""入力レイヤーの抽象基底クラス。新しいハードウェアはこれを継承して実装する。"""
from abc import ABC, abstractmethod
import numpy as np


class AudioInputBase(ABC):
    def __init__(self, sample_rate: int, channels: int):
        self.sample_rate = sample_rate
        self.channels = channels

    @abstractmethod
    def start(self) -> None:
        """入力デバイスの初期化・開始"""

    @abstractmethod
    def stop(self) -> None:
        """入力デバイスの停止・リソース解放"""

    @abstractmethod
    def read_chunk(self, duration: float) -> np.ndarray:
        """
        指定した秒数分の音声データを返す。
        戻り値: shape=(samples,), dtype=float32, 範囲 -1.0〜1.0
        """
