"""
resemblyzer を使った話者分離実装。
ステップ4でpyannote.audioに切り替える際はこのクラスを置き換える。
"""
import numpy as np
from .base import DiarizationBase


class ResemblyzerDiarizer(DiarizationBase):
    def __init__(self, similarity_threshold: float = 0.75):
        self.threshold = similarity_threshold
        self._encoder = None
        self._speaker_embeddings: dict[str, np.ndarray] = {}
        self._speaker_count = 0

    def load(self) -> None:
        from resemblyzer import VoiceEncoder
        print("[ResemblyzerDiarizer] モデルロード中 ...")
        self._encoder = VoiceEncoder()
        print("[ResemblyzerDiarizer] ロード完了")

    def identify(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self._encoder is None:
            raise RuntimeError("load() を先に呼んでください")

        from resemblyzer import preprocess_wav
        # resemblyzerは16kHz想定
        wav = preprocess_wav(audio, source_sr=sample_rate)
        embedding = self._encoder.embed_utterance(wav)

        # 既知の話者と照合
        best_id, best_score = None, -1.0
        for spk_id, emb in self._speaker_embeddings.items():
            score = float(np.dot(embedding, emb))
            if score > best_score:
                best_score = score
                best_id = spk_id

        if best_id is None or best_score < self.threshold:
            # 新しい話者として登録
            self._speaker_count += 1
            best_id = f"speaker_{self._speaker_count}"
            self._speaker_embeddings[best_id] = embedding
            print(f"[Diarizer] 新しい話者を検出: {best_id}")

        return best_id
