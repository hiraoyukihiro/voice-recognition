"""Whisper (OpenAI) を使った音声認識実装。"""
import numpy as np
import whisper
from .base import TranscriberBase


class WhisperASR(TranscriberBase):
    def __init__(self, model_size: str = "base", language: str = "ja"):
        self.model_size = model_size
        self.language = language
        self._model = None

    def load(self) -> None:
        print(f"[WhisperASR] モデルロード中: {self.model_size} ...")
        self._model = whisper.load_model(self.model_size)
        print(f"[WhisperASR] ロード完了")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        # Whisperは16kHz float32を期待する
        result = self._model.transcribe(
            audio,
            language=self.language,
            fp16=False,        # CPUでも動くようにfp16はオフ
            verbose=False,
        )
        return result["text"].strip()
