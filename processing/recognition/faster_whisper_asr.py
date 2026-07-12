"""faster-whisper (CTranslate2) を使った音声認識実装。低遅延・高精度化のためopenai-whisperから切り替え。"""
import numpy as np
from .base import TranscriberBase

# Whisper系モデルが無音・低SNR音声に対して出しがちな定型ハルシネーション。
# マイク感度が低く強い増幅が必要な環境では音量では判別できないため文面で弾く。
_HALLUCINATION_PHRASES = {
    "ご視聴ありがとうございました",
    "ご視聴いただきありがとうございました",
    "最後までご視聴いただきありがとうございました",
    "チャンネル登録お願いします",
    "チャンネル登録よろしくお願いします",
    "字幕視聴ありがとうございました",
    "この動画が良かったら高評価",
    "終わり",
    "おわり",
}


class FasterWhisperASR(TranscriberBase):
    def __init__(self, model_size: str = "small", language: str = "ja",
                 device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel
        print(f"[FasterWhisperASR] モデルロード中: {self.model_size} ({self.device}/{self.compute_type}) ...")
        self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        print("[FasterWhisperASR] ロード完了")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "threshold": 0.3},
            no_speech_threshold=0.7,
        )
        text = "".join(seg.text for seg in segments).strip()
        if text.rstrip("。、!?！？") in _HALLUCINATION_PHRASES:
            return ""
        return text
