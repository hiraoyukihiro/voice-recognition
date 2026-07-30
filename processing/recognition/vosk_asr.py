"""
Vosk（オフライン・完全無料・軽量）を使った音声認識実装。
クラウドAPIの無料枠は月数時間程度で常時起動のアクセシビリティ用途には足りず、
WhisperはこのマシンのCPUには重すぎるため、その中間解として採用。
モデルは公式サイトから別途ダウンロードして配置する必要がある（pipには含まれない）。
"""
import json
import os

import numpy as np

from .base import TranscriberBase


class VoskASR(TranscriberBase):
    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self._model = None

    def load(self) -> None:
        if not os.path.isdir(self.model_path):
            raise FileNotFoundError(
                f"Voskモデルが見つかりません: {self.model_path}\n"
                "https://alphacephei.com/vosk/models からモデルをダウンロードし、展開して配置してください。"
            )
        from vosk import Model
        print(f"[VoskASR] モデルロード中: {self.model_path} ...")
        self._model = Model(self.model_path)
        print("[VoskASR] ロード完了")

    def create_recognizer(self, sample_rate: int = None):
        """
        ストリーミング認識用に、状態を持つ認識器を1つ作って返す。
        （transcribe()は1回ごとに使い捨てだが、ストリーミングでは同じ認識器に
        音声を流し込み続け、認識器自身に文の区切り（無音）を判定させる）
        """
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        from vosk import KaldiRecognizer
        return KaldiRecognizer(self._model, sample_rate or self.sample_rate)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        from vosk import KaldiRecognizer

        # Voskは16bit PCM(リトルエンディアン)のバイト列を受け取る
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

        recognizer = KaldiRecognizer(self._model, sample_rate)
        recognizer.AcceptWaveform(pcm)
        result = json.loads(recognizer.FinalResult())
        return result.get("text", "").strip()
