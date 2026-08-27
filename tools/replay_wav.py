# -*- coding: utf-8 -*-
"""
録音済みWAVを「マイクの代わり」に流し込み、run.pyの字幕パイプラインと
同じ手順（0.3秒フレーム → 増幅 → VAD → Voskストリーミング → 0.8秒無変化で確定）で
字幕が出るかを確認する。マイクを使わないのでrun.py実行中でも安全。

使い方:
    python tools/replay_wav.py <WAVファイル> [--small] [--no-vad]
        --small : 軽量Voskモデルを使う（メモリ不足時の確認用。精度は落ちる）
        --no-vad: 声かどうかの判定を切って、Voskの生の認識結果だけを見る
"""
import sys, os, io, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import soundfile as sf

import config

TARGET_PEAK = 0.7                # run.py と同じ
PARTIAL_STALL_TIMEOUT = 0.8      # run.py:363 と同じ

parser = argparse.ArgumentParser()
parser.add_argument("wav")
parser.add_argument("--small", action="store_true")
parser.add_argument("--no-vad", action="store_true")
args = parser.parse_args()

profile = config.MIC_PROFILES.get("reSpeaker", config.DEFAULT_MIC_PROFILE)
SILENCE_THRESHOLD = profile["silence_threshold"]
MAX_GAIN = profile["max_gain"]


def amplify_frame(frame):
    rms = float(np.sqrt(np.mean(frame ** 2)))
    if rms < SILENCE_THRESHOLD:
        return frame
    peak = float(np.max(np.abs(frame))) or 1e-6
    return frame * min(TARGET_PEAK / peak, MAX_GAIN)


audio, sr = sf.read(args.wav, dtype="float32", always_2d=True)
audio = audio.mean(axis=1)
if sr != config.SAMPLE_RATE:
    raise SystemExit(f"サンプリング周波数が {sr}Hz です。{config.SAMPLE_RATE}Hz のWAVを渡してください。")
print(f"入力: {args.wav}  長さ={len(audio)/sr:.1f}秒")

model_path = config.VOSK_MODEL_PATH
if args.small:
    model_path = os.path.join(os.path.dirname(model_path), "vosk-model-small-ja-0.22")
from processing.recognition.vosk_asr import VoskASR
asr = VoskASR(model_path=model_path, sample_rate=config.SAMPLE_RATE)
asr.load()

vad = None
if config.ENABLE_VAD and not args.no_vad:
    from processing.vad.silero_vad import SileroVAD
    vad = SileroVAD(threshold=config.VAD_THRESHOLD, sample_rate=config.SAMPLE_RATE)
    vad.load()

recognizer = asr.create_recognizer(config.SAMPLE_RATE)
frame_len = int(config.SAMPLE_RATE * config.FRAME_DURATION)

utterance_frames, subtitles = [], []
last_partial_text, last_change_at = "", 0.0
vad_is_speech, vad_counter = True, 0
t_start = time.time()


def finalize(text, vclock):
    """run.py の finalize() と同じ判定（VADで最終確認してから確定字幕にする）"""
    global utterance_frames, last_partial_text, last_change_at
    raw = np.concatenate(utterance_frames) if utterance_frames else np.zeros(0, dtype=np.float32)
    utterance_frames, last_partial_text, last_change_at = [], "", vclock
    text = text.strip()
    if not text:
        return
    if vad is not None and len(raw) and not vad.is_speech(raw, config.SAMPLE_RATE):
        print(f"  [VAD] 人の声ではないため字幕にしません: 「{text}」")
        return
    print(f"[確定 {vclock:5.1f}秒] {text}")
    subtitles.append((vclock, text))


for i in range(0, len(audio) - frame_len + 1, frame_len):
    frame = audio[i:i + frame_len]
    vclock = (i + frame_len) / sr          # 音声側の経過時間（＝マイクなら実時間）
    utterance_frames.append(frame)

    if vad is not None:
        vad_counter += 1
        if vad_counter >= config.VAD_CHECK_INTERVAL:
            vad_counter = 0
            tail_len = int(config.SAMPLE_RATE * config.VAD_CHECK_SECONDS)
            vad_is_speech = vad.is_speech(np.concatenate(utterance_frames)[-tail_len:], config.SAMPLE_RATE)

    pcm = (np.clip(amplify_frame(frame), -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    if recognizer.AcceptWaveform(pcm):
        finalize(json.loads(recognizer.Result()).get("text", ""), vclock)
        continue

    partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
    if partial != last_partial_text:
        last_partial_text, last_change_at = partial, vclock
        if partial and vad_is_speech:
            print(f"  [途中 {vclock:5.1f}秒] {partial}")
    elif partial and (vclock - last_change_at > PARTIAL_STALL_TIMEOUT):
        recognizer.Reset()
        finalize(partial, vclock)

finalize(json.loads(recognizer.FinalResult()).get("text", ""), len(audio) / sr)

elapsed = time.time() - t_start
dur = len(audio) / sr
print("\n" + "=" * 50)
print(f"確定した字幕: {len(subtitles)}行")
for t, s in subtitles:
    print(f"  {t:5.1f}秒  {s}")
print(f"処理時間 {elapsed:.1f}秒 / 音声 {dur:.1f}秒  → RTF={elapsed/dur:.2f}（1.00未満なら間に合っている）")
