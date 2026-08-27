"""
音イベント検知（＝「今どんな音が鳴ったか」を当てる係）の抽象基底クラス。

方向検知（processing/direction/base.py）と同じ考え方で、
中身のAIを差し替えても run.py 側を書き換えなくて済むようにする。
将来PANNs以外（YAMNet、自前学習モデル等）に替える時は、
このクラスを継承したファイルを1つ足して config.py の設定を変えるだけでよい。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class SoundEvent:
    """検知した音1件ぶんの情報。そのままWebSocketでブラウザへ送れる形にする。"""
    key: str          # 内部用の識別子（例: "doorbell"）
    name: str         # 画面に出す日本語名（例: "インターホン"）
    icon: str         # 画面に出す絵文字
    confidence: float # 0.0〜1.0 どれくらい自信があるか
    db: float         # その音の大きさ（dB換算値。未校正の場合は目安）

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "icon": self.icon,
            "confidence": round(self.confidence, 3),
            "db": round(self.db, 1),
        }


class SoundEventDetectorBase(ABC):
    @abstractmethod
    def detect(self, audio: np.ndarray, sample_rate: int) -> list:
        """
        音声データ（1秒程度）から、鳴っている音の種類を推定して返す。
        戻り値: SoundEvent のリスト（自信度の高い順。該当なしなら空リスト）
        """

    def close(self) -> None:
        """必要なら後片付けをする。何もしない実装でよい。"""
