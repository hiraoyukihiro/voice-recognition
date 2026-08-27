"""
PANNs（CNN14）による音イベント検知の実装。

■ 何をする係か
1秒ぶんの音を受け取り、AudioSetの527種類のうちどれに近いかを判定する。
その中から、labels.py に書いた「知りたい音19種」だけを取り出して返す。

■ なぜPANNsなのか
HoloSound論文は VGG を音用に転移学習して19種を判定した（論文2.2節）。
その特徴量の作り方は Hershey et al. [10] のログメルスペクトログラム。
PANNs も同じログメル入力の畳み込みモデルで、AudioSetで学習済みのため、
19種ぶんの音源を自前で集めなくても同じ役目を果たせる。
学習済みモデルの配布元は論文著者のZenodo（Kong et al. 2020）。

■ 注意（サンプリング周波数）
このアプリのマイクは16kHz、PANNsのCNN14は32kHz前提。
そのため判定の直前に2倍にアップサンプリングする（scipyのresample_poly）。
16kHzの音に無い高域が増えるわけではないが、モデルが期待する
時間×周波数の形に合わせないと精度が大きく落ちるため必須。
"""
import os
import sys
import contextlib
import io

import numpy as np
from scipy.signal import resample_poly

from .base import SoundEventDetectorBase, SoundEvent
from .labels import SOUND_CLASSES, SPEECH_LABELS, find_unknown_labels

PANNS_SAMPLE_RATE = 32000


class PANNsSoundEventDetector(SoundEventDetectorBase):
    """
    min_confidence : これ未満の自信度は無視する（論文2.2節: 50%）
    min_db         : これ未満の大きさは無視する（論文2.2節: 45dB）
    db_offset      : dBFS（録音レベル基準）を dB SPL（実際の音の大きさ）へ
                     変換するための補正値。マイクごとに違うため校正が必要。
                     None の場合は大きさによる足切りを行わない。
    exclude_speech : 人の声が主成分の時は音イベントを出さない（論文は非音声のみ表示）
    """

    def __init__(self, checkpoint_path=None, min_confidence=0.5, min_db=45.0,
                 db_offset=None, exclude_speech=True, device="cpu"):
        # panns_inference は import した瞬間にラベル表を読み込む（無ければwgetを試みる）
        from panns_inference import AudioTagging
        from panns_inference.config import labels as audioset_labels

        unknown = find_unknown_labels(audioset_labels)
        if unknown:
            raise RuntimeError(
                "labels.py のAudioSetラベル名に、実在しないものがあります:\n  "
                + "\n  ".join(unknown)
            )

        self.min_confidence = min_confidence
        self.min_db = min_db
        self.db_offset = db_offset
        self.exclude_speech = exclude_speech

        # ラベル名 → 通し番号 の辞書を先に作っておく（判定のたびに探すと遅いため）
        index_of = {name: i for i, name in enumerate(audioset_labels)}
        self._class_indices = [
            (cls, [index_of[n] for n in cls["audioset"]]) for cls in SOUND_CLASSES
        ]
        self._speech_indices = [index_of[n] for n in SPEECH_LABELS]

        # panns_inference は読み込み時に大量のログを出すので飲み込む
        with contextlib.redirect_stdout(io.StringIO()):
            self._tagger = AudioTagging(checkpoint_path=checkpoint_path, device=device)

    # --- 音の大きさ（dB） ---
    def measure_db(self, audio: np.ndarray) -> float:
        """
        音の大きさを返す。db_offset が設定されていれば dB SPL 相当、
        設定されていなければ dBFS（0が最大、マイナス方向に小さくなる）。
        """
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        dbfs = 20.0 * np.log10(max(rms, 1e-9))
        return dbfs + self.db_offset if self.db_offset is not None else dbfs

    def detect(self, audio: np.ndarray, sample_rate: int) -> list:
        if audio is None or len(audio) < sample_rate // 4:
            return []

        db = self.measure_db(audio)
        # 小さすぎる音は判定にかけない（論文2.2節の45dB足切り）。
        # db_offset 未設定時は校正できていないので、この足切りは行わない。
        if self.db_offset is not None and db < self.min_db:
            return []

        audio = audio.astype(np.float32)
        if sample_rate != PANNS_SAMPLE_RATE:
            # 16000 → 32000 のように整数比なら resample_poly が速くて正確
            from math import gcd
            g = gcd(sample_rate, PANNS_SAMPLE_RATE)
            audio = resample_poly(audio, PANNS_SAMPLE_RATE // g, sample_rate // g).astype(np.float32)

        with contextlib.redirect_stdout(io.StringIO()):
            clipwise, _ = self._tagger.inference(audio[None, :])
        scores = clipwise[0]

        # 人の声が主成分なら音イベントは出さない（字幕係の担当なので二重表示を防ぐ）
        if self.exclude_speech:
            speech_score = float(max(scores[i] for i in self._speech_indices))
            if speech_score >= 0.5:
                return []

        events = []
        for cls, indices in self._class_indices:
            score = float(max(scores[i] for i in indices))
            if score >= self.min_confidence:
                events.append(SoundEvent(
                    key=cls["key"], name=cls["ja"], icon=cls["icon"],
                    confidence=score, db=db,
                ))
        events.sort(key=lambda e: e.confidence, reverse=True)
        return events

    def debug_top(self, audio: np.ndarray, sample_rate: int, top_n: int = 10) -> list:
        """
        調整用: 19種に絞る前の、AudioSet 527種そのままの上位を返す。
        「鳴らしたのに反応しない」時に、AIが実際は何だと思ったのかを見るため。
        """
        from panns_inference.config import labels as audioset_labels
        audio = audio.astype(np.float32)
        if sample_rate != PANNS_SAMPLE_RATE:
            from math import gcd
            g = gcd(sample_rate, PANNS_SAMPLE_RATE)
            audio = resample_poly(audio, PANNS_SAMPLE_RATE // g, sample_rate // g).astype(np.float32)
        with contextlib.redirect_stdout(io.StringIO()):
            clipwise, _ = self._tagger.inference(audio[None, :])
        scores = clipwise[0]
        order = np.argsort(scores)[::-1][:top_n]
        return [(audioset_labels[i], float(scores[i])) for i in order]
