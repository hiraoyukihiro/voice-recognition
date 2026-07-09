"""方向検知（DOA）の抽象基底クラス。"""
from abc import ABC, abstractmethod
import numpy as np


class DirectionEstimatorBase(ABC):
    @abstractmethod
    def estimate(self, audio: np.ndarray) -> float:
        """
        音声データから声の方向角度を推定して返す。
        戻り値: 0〜359 度（0=正面、時計回り）
        実機なしの場合はダミー値を返す実装で代替する。
        """
