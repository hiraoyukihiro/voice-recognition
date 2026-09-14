"""Groq Cloud の Whisper API を使った音声認識実装。"""
import io
import wave
import numpy as np
from .base import TranscriberBase

_HALLUCINATION_KEYWORD_SETS = [
    {"視聴", "ありがとう"},
    {"チャンネル登録"},
    {"高評価"},
    {"字幕", "ありがとう"},
    {"お疲れ様"},
    {"ご覧", "ありがとう"},
]


def _is_hallucination(text: str) -> bool:
    return any(all(kw in text for kw in kws) for kws in _HALLUCINATION_KEYWORD_SETS)


def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """float32 の音声データを WAV バイト列に変換する（API 送信用）"""
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class GroqWhisperASR(TranscriberBase):
    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo", language: str = "ja"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self._client = None

    def load(self) -> None:
        from groq import Groq
        print(f"[GroqWhisperASR] クライアント初期化中 (model={self.model}) ...")
        self._client = Groq(api_key=self.api_key)
        print("[GroqWhisperASR] 初期化完了（モデルのダウンロード不要）")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._client is None:
            raise RuntimeError("load() を先に呼んでください")
        wav_bytes = _to_wav_bytes(audio, sample_rate)
        result = self._client.audio.transcriptions.create(
            file=("audio.wav", wav_bytes, "audio/wav"),
            model=self.model,
            language=self.language,
            response_format="text",
        )
        text = (result if isinstance(result, str) else result.text).strip()
        if _is_hallucination(text):
            return ""
        return text
