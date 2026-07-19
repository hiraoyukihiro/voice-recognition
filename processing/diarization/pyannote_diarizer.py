"""
pyannote.audio (pyannote/embedding) を使った話者埋め込み抽出。
resemblyzerより高精度な声の特徴量を得るための差し替え用実装。

HuggingFaceのアクセストークンはメモリ上でのみ保持し、ファイル・環境変数には一切保存しない
（貸与PCでの利用を想定し、呼び出し側でgetpass.getpass()等により都度入力させること）。
"""
import numpy as np


class PyannoteEmbedder:
    def __init__(self, hf_token: str):
        self._hf_token = hf_token
        self._inference = None

    def load(self) -> None:
        from pyannote.audio import Model, Inference
        print("[PyannoteEmbedder] モデルロード中: pyannote/embedding ...")
        model = Model.from_pretrained("pyannote/embedding", use_auth_token=self._hf_token)
        self._inference = Inference(model, window="whole")
        print("[PyannoteEmbedder] ロード完了")
        # トークンは読み込みが済んだらインスタンスからも手放す
        self._hf_token = None

    def embed(self, audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        if self._inference is None:
            raise RuntimeError("load() を先に呼んでください")
        import torch
        waveform = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)  # (1, samples)
        embedding = self._inference({"waveform": waveform, "sample_rate": sample_rate})
        return np.asarray(embedding).reshape(-1)
