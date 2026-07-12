"""faster-whisper (CTranslate2) を使った音声認識実装。低遅延・高精度化のためopenai-whisperから切り替え。"""
import numpy as np
from .base import TranscriberBase

# Whisper系モデルが無音・低SNR音声に対して出しがちな定型ハルシネーション。
# マイク感度が低く強い増幅が必要な環境では音量では判別できないため文面で弾く。
# 言い回しに揺れがあるため、完全一致ではなくキーワードの組み合わせで判定する。
_HALLUCINATION_KEYWORD_SETS = [
    {"視聴", "ありがとう"},
    {"チャンネル登録"},
    {"高評価"},
    {"字幕", "ありがとう"},
]


def _is_hallucination(text: str) -> bool:
    return any(all(kw in text for kw in kws) for kws in _HALLUCINATION_KEYWORD_SETS)


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
        if _is_hallucination(text):
            return ""
        return text
