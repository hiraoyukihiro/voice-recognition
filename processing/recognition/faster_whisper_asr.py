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
    {"お疲れ様"},
    {"ご覧", "ありがとう"},
]

# Whisperが無音・低SNR区間に対して「発話らしさが低い」と自己申告するスコア。
# キーワード一致では拾いきれない未知のハルシネーション文言を、この確信度で弾く。
_NO_SPEECH_PROB_THRESHOLD = 0.6


def _is_hallucination(text: str) -> bool:
    return any(all(kw in text for kw in kws) for kws in _HALLUCINATION_KEYWORD_SETS)


class FasterWhisperASR(TranscriberBase):
    def __init__(self, model_size: str = "small", language: str = "ja",
                 device: str = "cpu", compute_type: str = "int8", cpu_threads: int = 0):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads  # 0 = faster-whisperのデフォルト
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel
        print(f"[FasterWhisperASR] モデルロード中: {self.model_size} ({self.device}/{self.compute_type}, threads={self.cpu_threads}) ...")
        self._model = WhisperModel(
            self.model_size, device=self.device, compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        print("[FasterWhisperASR] ロード完了")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            condition_on_previous_text=False,
            beam_size=1,
            # vad_filterは使わない。音声を細切れに分割してから1つずつ処理するため、
            # Whisperの「必ず30秒に引き伸ばす」計算が分割数だけ繰り返されて遅くなる
            # （実測: 5ファイル合計 27.9秒 → 17.4秒。2026-08-30）。
            # 発話の区切りは run.py 側でVADを使って済ませてあるので、ここでは不要。
            vad_filter=False,
            no_speech_threshold=0.6,
            # 同じ言葉を延々と作り続ける暴走（幻覚ループ）を抑える。
            # 実測: 6回中1回、3秒の音声に15.8秒かかる暴走が起きた（2026-08-30）。
            repetition_penalty=1.15,
            # 暴走時の最悪ケースを短くするための上限。
            # 音声1秒あたり日本語で20文字も出れば十分（普通の会話は5〜8文字/秒）。
            max_new_tokens=min(448, max(48, int(len(audio) / sample_rate * 20))),
        )
        text = "".join(
            seg.text for seg in segments if seg.no_speech_prob < _NO_SPEECH_PROB_THRESHOLD
        ).strip()
        if _is_hallucination(text):
            return ""
        return text
