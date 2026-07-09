"""
ダミー方向検知。指向性マイクアレイ実機が届くまでの代替実装。
本物のDOA実装（例: SRP-PHAT）に差し替える際はこのクラスを置き換える。
"""
import random
import numpy as np
from .base import DirectionEstimatorBase


class DummyDOA(DirectionEstimatorBase):
    def __init__(self, mode: str = "random"):
        """
        mode:
          "random"  - 呼び出しごとにランダムな角度を返す
          "fixed"   - 常に fixed_angle を返す（特定方向のテスト用）
          "sweep"   - 少しずつ角度が変わる（アニメーション確認用）
        """
        self.mode = mode
        self.fixed_angle = 0.0
        self._sweep_angle = 0.0

    def estimate(self, audio: np.ndarray) -> float:
        if self.mode == "random":
            return float(random.randint(0, 359))
        elif self.mode == "fixed":
            return self.fixed_angle
        elif self.mode == "sweep":
            self._sweep_angle = (self._sweep_angle + 15) % 360
            return self._sweep_angle
        return 0.0
