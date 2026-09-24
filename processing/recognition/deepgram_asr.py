"""Deepgram Nova-3 API を使った音声認識実装（requests で直接 HTTP 通信）。"""
import io
import wave
import numpy as np
from .base import TranscriberBase


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


class DeepgramASR(TranscriberBase):
    def __init__(self, api_key: str, model: str = "nova-3", language: str = "ja"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self._session = None

    def load(self) -> None:
        import requests
        print(f"[DeepgramASR] クライアント初期化中 (model={self.model}) ...")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {self.api_key}",
        })
        print("[DeepgramASR] 初期化完了（モデルのダウンロード不要）")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._session is None:
            raise RuntimeError("load() を先に呼んでください")
        wav_bytes = _to_wav_bytes(audio, sample_rate)
        params = {
            "model": self.model,
            "language": self.language,
            "smart_format": "true",
        }
        resp = self._session.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers={"Content-Type": "audio/wav"},
            data=wav_bytes,
            timeout=15,
        )
        resp.raise_for_status()
        try:
            text = resp.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, IndexError):
            return ""
        return (text or "").strip()
