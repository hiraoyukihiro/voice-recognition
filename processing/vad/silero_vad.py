"""Silero VAD（無料・オフライン・軽量）を使った音声区間検出の実装。"""
import numpy as np
from .base import VADBase


class SileroVAD(VADBase):
    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        # threshold: この値以上を「声」と判定する（0〜1、高いほど声と判定されにくくなる）
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._model = None
        self._get_speech_timestamps = None

    def load(self) -> None:
        from silero_vad import load_silero_vad, get_speech_timestamps
        print("[SileroVAD] モデルロード中...")
        self._model = load_silero_vad()
        self._get_speech_timestamps = get_speech_timestamps
        print("[SileroVAD] ロード完了")

    def is_speech(self, audio: np.ndarray, sample_rate: int = 16000) -> bool:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        timestamps = self._get_speech_timestamps(
            audio, self._model,
            sampling_rate=sample_rate,
            threshold=self.threshold,
        )
        return len(timestamps) > 0
