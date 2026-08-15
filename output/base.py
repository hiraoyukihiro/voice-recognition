"""出力レイヤーの抽象基底クラス。将来Even G2 SDKに差し替える際はこれを継承する。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SubtitleEvent:
    speaker_id: str    # "speaker_1" など
    text: str          # 認識テキスト
    direction: float   # 0〜359度


class DisplayBase(ABC):
    @abstractmethod
    async def start(self) -> None:
        """表示システムの起動"""

    @abstractmethod
    async def stop(self) -> None:
        """表示システムの停止"""

    @abstractmethod
    async def send(self, event: SubtitleEvent) -> None:
        """字幕イベントを表示に反映する"""
