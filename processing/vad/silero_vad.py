"""
Silero VAD（無料・オフライン・軽量）で「人の声かどうか」を判定する。

音量だけでは、エアコンの音や物音と人の声を区別できない。
Voskは渡された音に必ず何か文字を当てはめようとするため、
雑音を渡すと意味不明な字幕が出る。それを防ぐのがこの役目。

2026-08-27の実測（threshold=0.15）:
  本物の声（近い/中/遠い/すごく遠い）→ すべて「声」と正しく判定
  ホワイトノイズ・低音ノイズ・環境音   → すべて「雑音」と正しく判定
  処理時間 0.12秒 / 音声6秒（十分軽い）
※以前は threshold=0.35〜0.5 を使い「本物の声まで雑音扱い」して無効化したが、
  それはマイクの2ch混線バグで音声自体が壊れていた時の判断だった。
"""
import numpy as np


class SileroVAD:
    def __init__(self, threshold: float = 0.15, sample_rate: int = 16000):
        # threshold: 高いほど「声」と判定されにくい（0〜1）
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._model = None
        self._get_speech_timestamps = None

    def load(self) -> None:
        from silero_vad import load_silero_vad, get_speech_timestamps
        print("[SileroVAD] モデルロード中...")
        self._model = load_silero_vad()
        self._get_speech_timestamps = get_speech_timestamps
        print(f"[SileroVAD] ロード完了（判定基準={self.threshold}）")

    def is_speech(self, audio: np.ndarray, sample_rate: int = 16000) -> bool:
        if self._model is None:
            raise RuntimeError("load() を先に呼んでください")
        if len(audio) == 0:
            return False
        timestamps = self._get_speech_timestamps(
            audio, self._model,
            sampling_rate=sample_rate,
            threshold=self.threshold,
        )
        return len(timestamps) > 0
