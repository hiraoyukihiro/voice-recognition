"""
音の大きさ(dB)の校正ツール。

■ なぜ必要か
HoloSound論文は「45dB未満の音は無視する」と決めている（論文2.2節）。
しかしマイクが返す数値は「録音レベル」（dBFS）であって、
空気の振動の大きさ（dB SPL＝騒音計が示す値）ではない。
2つの差はマイクの感度で決まるので、機種ごとに一度だけ測る必要がある。

■ やること
このツールで測った値を config.py の SOUND_EVENT_DB_OFFSET に書き込むと、
論文と同じ45dBの足切りが正しく効くようになる。

■ 使い方
1. スマホに騒音計アプリ（"騒音計" "sound meter" で検索、無料のものでよい）を入れる
2. スマホをマイクのすぐ横に置く
3. このツールを実行し、何か音を出し続ける（テレビ、話し声など）
4. 表示された値と、スマホの騒音計の値を見比べて入力する
"""
import os
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SECONDS = 10


def main():
    print(__doc__)
    print("=" * 60)
    input("準備ができたらEnterを押してください（10秒間、音を鳴らし続ける）...")

    audio = sd.rec(int(config.SAMPLE_RATE * SECONDS), samplerate=config.SAMPLE_RATE,
                   channels=1, dtype="float32")
    for remaining in range(SECONDS, 0, -1):
        print(f"  録音中... 残り{remaining}秒", end="\r")
        time.sleep(1)
    sd.wait()
    print(" " * 40, end="\r")

    audio = audio.reshape(-1)
    # 1秒ごとの音量を出し、その中央値を代表値にする（一瞬の物音に引きずられないため）
    step = config.SAMPLE_RATE
    dbfs_list = []
    for i in range(0, len(audio) - step + 1, step):
        rms = float(np.sqrt(np.mean(audio[i:i + step].astype(np.float64) ** 2)))
        dbfs_list.append(20.0 * np.log10(max(rms, 1e-9)))

    median_dbfs = float(np.median(dbfs_list))
    print(f"\n測定結果: このマイクの録音レベルは 中央値 {median_dbfs:.1f} dBFS でした")
    print(f"  （1秒ごとの値: {', '.join(f'{v:.0f}' for v in dbfs_list)}）\n")

    answer = input("同じ時に騒音計アプリが示していた値（例: 62）を入力してください: ").strip()
    try:
        spl = float(answer)
    except ValueError:
        print("数字ではないので終了します。")
        return

    offset = spl - median_dbfs
    print("\n" + "=" * 60)
    print(f"補正値 = {spl:.1f} - ({median_dbfs:.1f}) = {offset:.1f}")
    print("\nconfig.py の次の行を、こう書き換えてください:")
    print(f"    SOUND_EVENT_DB_OFFSET = {offset:.1f}")
    print("\nこれで「45dB未満は無視」が論文どおりに効くようになります。")
    print("マイクを変えたら測り直してください。")


if __name__ == "__main__":
    main()
