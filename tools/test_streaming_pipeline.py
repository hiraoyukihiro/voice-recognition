"""
マイク・スピーカーを使わず、run.py の pipeline_loop_streaming() と同じロジック
（無音ゲート増幅 → Vosk逐次認識 → 方向ベース話者分離）を
既存の音声ファイル(test_audio/mic_test.wav)で検証するテスト。

実際に人が喋れない状況で、録音方式やハードウェアの変更ではなく
「ストリーミング認識まわりのロジックが壊れていないか」だけを確認したいときに使う。

使い方: python tools/test_streaming_pipeline.py [wavファイルパス]
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import soundfile as sf

import config
from processing.recognition.vosk_asr import VoskASR
from processing.diarization.direction_diarizer import DirectionDiarizer

WAV_PATH = sys.argv[1] if len(sys.argv) > 1 else "test_audio/mic_test.wav"

SILENCE_THRESHOLD = 0.0045  # config.MIC_PROFILES["reSpeaker"] と同じ値
MAX_GAIN = 20.0
FRAME_SAMPLES = int(config.SAMPLE_RATE * config.FRAME_DURATION)
PARTIAL_STALL_TIMEOUT = 1.5


def amplify_frame(frame: np.ndarray) -> np.ndarray:
    """run.py の amplify_frame() と同一ロジック。"""
    rms = float(np.sqrt(np.mean(frame ** 2)))
    if rms < SILENCE_THRESHOLD:
        return frame
    return np.clip(frame * MAX_GAIN, -1.0, 1.0)


def main():
    print(f"音声ファイル: {WAV_PATH}")
    audio, sr = sf.read(WAV_PATH, dtype="float32")
    if sr != config.SAMPLE_RATE:
        print(f"警告: サンプルレートが{sr}Hzです（期待値{config.SAMPLE_RATE}Hz）。結果が不正確になる可能性があります。")

    # 前後に無音を足す（実際のマイク入力のように、発話の前後に間があることを再現する）
    pad = np.zeros(int(config.SAMPLE_RATE * 1.0), dtype=np.float32)
    audio = np.concatenate([pad, audio, pad])

    print("Voskモデルをロード中...")
    asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
    asr.load()
    recognizer = asr.create_recognizer(config.SAMPLE_RATE)

    diarizer = DirectionDiarizer(angle_tolerance=config.DIRECTION_ANGLE_TOLERANCE)
    DUMMY_DIRECTION = 123.0  # 実機なしのため固定値。方向ベース分離ロジックの動作確認用

    print(f"\n=== ストリーミング処理開始（フレーム={config.FRAME_DURATION}秒） ===\n")

    last_partial_text = ""
    last_partial_change_time = time.time()
    finalized_texts = []

    n_frames = len(audio) // FRAME_SAMPLES
    for i in range(n_frames):
        frame = audio[i * FRAME_SAMPLES: (i + 1) * FRAME_SAMPLES]
        amplified = amplify_frame(frame)
        pcm = (amplified * 32767).astype(np.int16).tobytes()
        is_final = recognizer.AcceptWaveform(pcm)

        if is_final:
            result = json.loads(recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                speaker_id = diarizer.identify(DUMMY_DIRECTION)
                print(f"[確定/Vosk無音検知] [{speaker_id} | {DUMMY_DIRECTION:.0f}度] {text}")
                finalized_texts.append(text)
            last_partial_text = ""
            last_partial_change_time = time.time()
            continue

        partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
        now = time.time()
        if partial != last_partial_text:
            last_partial_text = partial
            last_partial_change_time = now
            if partial:
                speaker_id = diarizer.identify(DUMMY_DIRECTION)
                print(f"  [途中経過] [{speaker_id}] {partial}")
        elif partial and (now - last_partial_change_time > PARTIAL_STALL_TIMEOUT):
            recognizer.Reset()
            speaker_id = diarizer.identify(DUMMY_DIRECTION)
            print(f"[確定/停滞タイムアウト] [{speaker_id} | {DUMMY_DIRECTION:.0f}度] {partial}")
            finalized_texts.append(partial)
            last_partial_text = ""
            last_partial_change_time = now

    # ファイル末尾で確定していない分を回収
    result = json.loads(recognizer.FinalResult())
    text = result.get("text", "").strip()
    if text:
        speaker_id = diarizer.identify(DUMMY_DIRECTION)
        print(f"[確定/末尾] [{speaker_id} | {DUMMY_DIRECTION:.0f}度] {text}")
        finalized_texts.append(text)

    print("\n=== 結果まとめ ===")
    if finalized_texts:
        for t in finalized_texts:
            print(f"  ・{t}")
    else:
        print("  （確定した文字起こしはありませんでした）")


if __name__ == "__main__":
    main()
