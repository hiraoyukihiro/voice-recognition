"""テスト用音声ファイルからの入力（WAVファイルをループ再生）。"""
import numpy as np
import soundfile as sf
from .base import AudioInputBase


class FileInput(AudioInputBase):
    def __init__(self, file_path: str, sample_rate: int = 16000):
        super().__init__(sample_rate, channels=1)
        self.file_path = file_path
        self._data = None
        self._pos = 0

    def start(self) -> None:
        data, sr = sf.read(self.file_path, dtype="float32", always_2d=False)
        if data.ndim == 2:
            data = data[:, 0]  # ステレオならモノラルに
        # サンプルレートが違う場合は単純リサンプル（精度より手軽さ優先）
        if sr != self.sample_rate:
            import scipy.signal as sps
            num = int(len(data) * self.sample_rate / sr)
            data = sps.resample(data, num)
        self._data = data
        self._pos = 0
        print(f"[FileInput] ロード完了: {self.file_path} ({len(data)/self.sample_rate:.1f}秒)")

    def stop(self) -> None:
        self._data = None
        self._pos = 0

    def read_chunk(self, duration: float) -> np.ndarray:
        frames = int(self.sample_rate * duration)
        end = self._pos + frames
        if end <= len(self._data):
            chunk = self._data[self._pos:end]
            self._pos = end
        else:
            # ファイル末尾でループ
            chunk = np.concatenate([
                self._data[self._pos:],
                self._data[:end - len(self._data)]
            ])
            self._pos = end - len(self._data)
        return chunk
