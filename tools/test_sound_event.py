"""
音イベント検知（PANNs）の単体テスト・調整ツール。

使い方:
  python tools/test_sound_event.py              … マイクから5秒録って判定する
  python tools/test_sound_event.py <WAVファイル> … WAVを1秒ずつ判定する
  python tools/test_sound_event.py --bench      … 判定1回にかかる時間を測る

「鳴らしたのに反応しない」時は、19種に絞る前のAudioSet 527種の上位も出るので、
AIが実際に何だと思ったのかを確認できる。
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from processing.sound_event.panns_tagger import PANNsSoundEventDetector

WINDOW = config.SOUND_EVENT_WINDOW


def load_detector():
    print("モデル読み込み中...")
    t0 = time.time()
    det = PANNsSoundEventDetector(
        checkpoint_path=config.PANNS_CHECKPOINT,
        min_confidence=config.SOUND_EVENT_MIN_CONFIDENCE,
        min_db=config.SOUND_EVENT_MIN_DB,
        db_offset=config.SOUND_EVENT_DB_OFFSET,
        exclude_speech=config.SOUND_EVENT_EXCLUDE_SPEECH,
    )
    print(f"  読み込み完了 ({time.time() - t0:.1f}秒)\n")
    return det


def report(det, chunk, sr, header):
    print(header)
    print(f"  音量: {det.measure_db(chunk):.1f} dB"
          f"{'' if config.SOUND_EVENT_DB_OFFSET is not None else '（dBFS・未校正）'}")
    events = det.detect(chunk, sr)
    if events:
        for e in events:
            print(f"  → {e.icon} {e.name}  自信度 {e.confidence:.0%}")
    else:
        print("  → 該当なし（19種のどれにも当てはまらないか、足切りされた）")
    print("  参考（AudioSet 527種の上位5件）:")
    for name, score in det.debug_top(chunk, sr, 5):
        print(f"      {score:6.1%}  {name}")
    print()


def from_wav(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd

    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != config.SAMPLE_RATE:
        g = gcd(sr, config.SAMPLE_RATE)
        audio = resample_poly(audio, config.SAMPLE_RATE // g, sr // g).astype(np.float32)
        sr = config.SAMPLE_RATE

    det = load_detector()
    step = int(sr * WINDOW)
    print(f"{os.path.basename(path)}: {len(audio)/sr:.1f}秒 を{WINDOW}秒ずつ判定します\n")
    for i in range(0, len(audio) - step + 1, step):
        report(det, audio[i:i + step], sr, f"--- {i/sr:.1f}秒 〜 {(i+step)/sr:.1f}秒 ---")


def from_mic(seconds=5.0):
    import sounddevice as sd

    det = load_detector()
    print(f"{seconds:.0f}秒間録音します。音を鳴らしてください...")
    audio = sd.rec(int(config.SAMPLE_RATE * seconds), samplerate=config.SAMPLE_RATE,
                   channels=1, dtype="float32")
    sd.wait()
    audio = audio.reshape(-1)
    print("録音終了\n")

    step = int(config.SAMPLE_RATE * WINDOW)
    for i in range(0, len(audio) - step + 1, step):
        report(det, audio[i:i + step], config.SAMPLE_RATE,
               f"--- {i/config.SAMPLE_RATE:.1f}秒 〜 {(i+step)/config.SAMPLE_RATE:.1f}秒 ---")


def bench(times=10):
    det = load_detector()
    chunk = np.random.randn(int(config.SAMPLE_RATE * WINDOW)).astype(np.float32) * 0.05
    det.detect(chunk, config.SAMPLE_RATE)  # 1回目は準備が入るので測らない
    t0 = time.time()
    for _ in range(times):
        det.detect(chunk, config.SAMPLE_RATE)
    per = (time.time() - t0) / times
    print(f"1回の判定にかかる時間: {per*1000:.0f} ミリ秒")
    print(f"判定の間隔(SOUND_EVENT_HOP): {config.SOUND_EVENT_HOP}秒 = {config.SOUND_EVENT_HOP*1000:.0f} ミリ秒")
    if per > config.SOUND_EVENT_HOP:
        print("  [警告] 判定が間隔より遅いので、config.py の SOUND_EVENT_HOP を大きくしてください")
    else:
        print(f"  → CPUの使用率はおよそ {per/config.SOUND_EVENT_HOP:.0%}（1コアぶん）")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if "--bench" in args:
        bench()
    elif args:
        from_wav(args[0])
    else:
        from_mic()
