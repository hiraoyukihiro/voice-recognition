"""VAD（音声区間検出）の抽象基底クラス。"""
from abc import ABC, abstractmethod
import numpy as np


class VADBase(ABC):
    @abstractmethod
    def load(self) -> None:
        """モデルのロード（起動時に一度だけ呼ぶ）"""

    @abstractmethod
    def is_speech(self, audio: np.ndarray, sample_rate: int) -> bool:
        """
        音声データに人の声が含まれるかを判定する。
        音量(RMS)だけでは車の音などの非音声ノイズと声を区別できないため、
        認識にかける前にここで弾く。
        """
