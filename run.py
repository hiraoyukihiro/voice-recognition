"""
全体統合パイプライン（軽量版）。これ1つを実行すれば全機能が動く。
機能は3つのみ: 音声認識（マイク→文字化）／字幕化（ブラウザ表示）／方向検知（DOA）。
実行: python run.py
ブラウザで output/web/index.html が自動で開く（配信サーバーは使わずファイルを直接開く）。
"""
import os

# ★ここは他のimportより先に置くこと（読み込んだ後では効かない）★
#
# このアプリは Vosk(Kaldi) / Whisper(CTranslate2) / PyTorch(VAD・音イベント検知) という
# 3つの独立したライブラリを1つのプログラムに同居させている。
# それぞれが独自の並列処理エンジン(OpenMP)を持ち込むため、そのまま動かすと
# 同じCPUを別々の管理者が奪い合う状態になり、**エラーメッセージを一切残さずに
# 突然終了する**ことがある（実測: 終了コード255・116で3回発生。2026-08-30）。
#
# KMP_DUPLICATE_LIB_OK … 並列処理エンジンが二重に読み込まれても止めずに続行させる
# OMP_NUM_THREADS       … 各ライブラリが勝手に全スレッドを取りに行くのを防ぐ
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import asyncio
import time
import webbrowser
import traceback
import sys
import numpy as np
import sounddevice as sd
import websockets
import json
import collections

import config

# --- 設定 ---
# 注記: 以前は「sd.InputStreamはこの環境で無音になる」としてsd.rec()による
# 毎回開き直し方式を使っていたが、tools/check_mic_gap.py で検証した結果、
# 無音になるのはDirectSoundホストAPI経由の場合のみで、WASAPI/MME経由なら
# 開きっぱなしのInputStreamで問題なく録音できることを確認した（2026-08-15）。

# --- 音量正規化設定 ---
# 固定倍率だと声の大小で認識精度が変わるため、ピーク音量基準で正規化する
TARGET_PEAK = 0.7

# --- マイクデバイス解決 ---
# USB機器の抜き差しでMMEの既定デバイスが無音になる不具合を確認したため、
# 名前+ホストAPIで実際に使えるデバイスを解決する（config.MIC_DEVICE_INDEXは手動指定用に残す）
from input.mic_input import find_input_device

if config.MIC_DEVICE_INDEX is not None:
    mic_device_index = config.MIC_DEVICE_INDEX
else:
    mic_device_index = find_input_device(config.MIC_DEVICE_NAME)
    if mic_device_index is None:
        print(f"  警告: '{config.MIC_DEVICE_NAME}' を含むマイクが見つからないため、システムデフォルトを使用します")
print(f"  → マイク入力デバイス: {mic_device_index if mic_device_index is not None else 'システムデフォルト'}")

# --- マイクストリーム（開きっぱなし） ---
# record_chunk()/record_frame() はこのストリームから読み取るだけにし、
# 呼び出すたびにマイクを開閉しない（開閉のたびに音が録れない時間が生じるため）。
#
# 重要: チャンネル数は必ずデバイスのネイティブ値で開くこと。
# reSpeaker XVF3800（2ch）に対して channels=1 で開くと、2ch分のデータが
# 1サンプルおきに交互に混ざったまま渡され、波形が壊れて認識が全く成立しない
# （実測: 隣接サンプル差より1つ飛ばし差の方が小さいという異常、6-8kHzに23%の偽エネルギー、
# 12秒録音しても実音声は6秒分だけ）。2026-08-27に判明・修正。
_dev_info = sd.query_devices(mic_device_index) if mic_device_index is not None else sd.query_devices(kind="input")
MIC_CHANNELS = max(1, int(_dev_info["max_input_channels"]))
print(f"  → マイクチャンネル数: {MIC_CHANNELS}（デバイスのネイティブ値で開く）")

mic_stream = sd.InputStream(
    samplerate=config.SAMPLE_RATE,
    channels=MIC_CHANNELS,
    dtype="float32",
    device=mic_device_index,
)
mic_stream.start()


def to_mono(audio: np.ndarray) -> np.ndarray:
    """複数チャンネルを平均して1本にまとめる（1chならそのまま）。"""
    return audio.mean(axis=1) if audio.ndim > 1 else audio

# --- マイクごとの自動設定 ---
# マイクの機種によって音量特性が違うため、実際に選ばれたデバイスの名前から機種を判定し、
# config.MIC_PROFILESに定義された音量しきい値・増幅上限を自動で適用する
# （マイクを差し替えても手動で設定し直さなくてよいように）。
if mic_device_index is not None:
    _mic_device_name = sd.query_devices(mic_device_index)["name"]
else:
    _mic_device_name = sd.query_devices(kind="input")["name"]

if config.FORCE_MIC_PROFILE is not None:
    _active_mic_profile = config.MIC_PROFILES.get(config.FORCE_MIC_PROFILE, config.DEFAULT_MIC_PROFILE)
    print(f"  → マイク設定: '{config.FORCE_MIC_PROFILE}' 用のプロファイルを手動指定で強制適用"
          f"（しきい値={_active_mic_profile['silence_threshold']}, 増幅上限={_active_mic_profile['max_gain']}倍）"
          f"　※config.FORCE_MIC_PROFILE=Noneで自動判定に戻せます")
else:
    for _substr, _profile in config.MIC_PROFILES.items():
        if _substr in _mic_device_name:
            _active_mic_profile = _profile
            print(f"  → マイク設定: '{_substr}' 用のプロファイルを自動適用（しきい値={_profile['silence_threshold']}, 増幅上限={_profile['max_gain']}倍）")
            break
    else:
        _active_mic_profile = config.DEFAULT_MIC_PROFILE
        print(f"  → マイク設定: 未知のマイク（{_mic_device_name}）のため標準値を使用（しきい値={_active_mic_profile['silence_threshold']}, 増幅上限={_active_mic_profile['max_gain']}倍）")

SILENCE_THRESHOLD = _active_mic_profile["silence_threshold"]
MAX_GAIN = _active_mic_profile["max_gain"]

# --- メモリの空き確認 ---
# このアプリは複数のAIモデルを同時に積むため、実測で約2.8GB使う。
#   Vosk大型 1677MB / 音イベント検知 609MB / Whisper small 514MB / VAD 7MB
# 空きが足りないまま起動すると、途中で警告もなく落ちることがあるので先に知らせる。
def _print_memory_status():
    import ctypes

    class _MemStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("totalPage", ctypes.c_ulonglong), ("availPage", ctypes.c_ulonglong),
                    ("totalVirt", ctypes.c_ulonglong), ("availVirt", ctypes.c_ulonglong),
                    ("availExt", ctypes.c_ulonglong)]

    st = _MemStatus()
    st.length = ctypes.sizeof(_MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    free_gb = st.avail / 1e9

    need_gb = 1.7 + 0.6 + (0.6 if config.ENABLE_CORRECTION else 0.0)
    print(f"  → メモリの空き: {free_gb:.1f}GB（このアプリはおよそ{need_gb:.1f}GB使います）")
    if free_gb < need_gb + 0.5:
        print()
        print("  ⚠️ メモリの空きが足りません。途中で落ちる可能性があります。")
        print("     対処: 他のアプリ（ブラウザのタブなど）を閉じる")
        print("           または config.py で以下のどちらかを False にする")
        print("           ENABLE_SOUND_EVENT = False  … 音イベント検知を止める（約0.6GB節約）")
        print("           ENABLE_CORRECTION  = False  … 字幕の書き直しを止める（約0.6GB節約）")
        print()


_print_memory_status()

# --- モデルロード ---
print("=" * 50)
print("  音声認識システム 起動中...")
print("=" * 50)

print("\n[1/3] 音声認識モデルをロード中...")
if config.WHISPER_ENGINE == "faster_whisper":
    from processing.recognition.faster_whisper_asr import FasterWhisperASR
    asr = FasterWhisperASR(
        model_size=config.WHISPER_MODEL,
        language=config.WHISPER_LANGUAGE,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
        cpu_threads=config.WHISPER_CPU_THREADS,
    )
elif config.WHISPER_ENGINE == "vosk":
    from processing.recognition.vosk_asr import VoskASR
    asr = VoskASR(model_path=config.VOSK_MODEL_PATH, sample_rate=config.SAMPLE_RATE)
else:
    from processing.recognition.whisper_asr import WhisperASR
    asr = WhisperASR(model_size=config.WHISPER_MODEL, language=config.WHISPER_LANGUAGE)
asr.load()

print("[2/3] VAD（声かどうかの判定）モデルをロード中...")
vad = None
if config.ENABLE_VAD:
    from processing.vad.silero_vad import SileroVAD
    vad = SileroVAD(threshold=config.VAD_THRESHOLD, sample_rate=config.SAMPLE_RATE)
    vad.load()
else:
    print("  → VAD無効（config.ENABLE_VAD=Falseのためスキップ）")

print("[3/3] ウォームアップ中（初回のみ時間がかかります）...")
_dummy = np.zeros(config.SAMPLE_RATE * 3, dtype=np.float32)
asr.transcribe(_dummy, config.SAMPLE_RATE)

print("\n全モデルロード完了\n")

# --- 方向検知 ---
# reSpeaker実機のみ対応（ダミー実装は削除済み）。
# 見つからない場合は方向検知なし（常に0度=正面扱い）で起動し、字幕機能はそのまま使える。
from processing.direction.xvf3800_doa import XVF3800DOA

doa = None
for _attempt in range(5):
    try:
        doa = XVF3800DOA(
            angle_offset=config.XVF3800_ANGLE_OFFSET,
            invert=config.XVF3800_INVERT,
        )
        break
    except RuntimeError as e:
        print(f"  reSpeaker検出リトライ中... ({_attempt + 1}/5) {e}")
        time.sleep(1.5)

if doa is None:
    print("  → reSpeakerが見つからないため、方向検知なし（常に0度）で起動します")
else:
    # USBへの同期問い合わせを認識パイプラインのクリティカルパスから外すため、
    # バックグラウンドスレッドで0.1秒ごとに読み直してキャッシュする方式に切り替える
    doa.start()
    print("  → 方向検知: reSpeaker XVF3800（実機、バックグラウンドポーリング0.1秒間隔）")


def estimate_direction(audio: np.ndarray) -> float:
    return doa.estimate(audio) if doa is not None else 0.0

# --- 音イベント検知（HoloSound論文2.2節の再現） ---
# 「今どんな音が鳴ったか」（ノック・火災報知器・電話など19種）を字幕とは別に判定する係。
# 直近の生音をここに貯めておき、SOUND_EVENT_HOP秒ごとに末尾1秒ぶんを判定にかける
# （論文と同じスライディングウィンドウ方式）。
_frames_per_window = max(1, int(np.ceil(config.SOUND_EVENT_WINDOW / config.FRAME_DURATION)))
recent_frames: collections.deque = collections.deque(maxlen=_frames_per_window + 1)

sound_detector = None
if config.ENABLE_SOUND_EVENT:
    try:
        from processing.sound_event.panns_tagger import PANNsSoundEventDetector
        print("音イベント検知モデル(PANNs CNN14)を読み込み中... 初回は数十秒かかります")
        sound_detector = PANNsSoundEventDetector(
            checkpoint_path=config.PANNS_CHECKPOINT,
            min_confidence=config.SOUND_EVENT_MIN_CONFIDENCE,
            min_db=config.SOUND_EVENT_MIN_DB,
            db_offset=config.SOUND_EVENT_DB_OFFSET,
            exclude_speech=config.SOUND_EVENT_EXCLUDE_SPEECH,
        )
        if config.SOUND_EVENT_DB_OFFSET is None:
            print("  → 音イベント検知: 有効（音量による足切りは未校正のため無効。"
                  "python tools/calibrate_db.py で校正できます）")
        else:
            print(f"  → 音イベント検知: 有効（{config.SOUND_EVENT_MIN_DB}dB / "
                  f"自信度{config.SOUND_EVENT_MIN_CONFIDENCE:.0%} 未満は無視）")
    except Exception as e:
        print(f"  → 音イベント検知を読み込めませんでした（字幕と方向は通常どおり動きます）: {e}")
        sound_detector = None


def window_audio() -> np.ndarray:
    """直近の音から、判定にかける1秒ぶんを取り出す。足りなければ空を返す。"""
    if not recent_frames:
        return np.zeros(0, dtype=np.float32)
    need = int(config.SAMPLE_RATE * config.SOUND_EVENT_WINDOW)
    buf = np.concatenate(list(recent_frames))
    return buf[-need:] if len(buf) >= need else buf


# --- あとから書き直す係（Whisperによる訂正） ---
# Voskが即座に出した粗い字幕を、Whisperが聞き直して正しい文に置き換える。
# ここには直近CORRECT_WINDOW秒ぶんの生音を貯めておく。
# 発話ごとではなく一定間隔でまとめて処理するので、Whisperの「毎回約8秒」という
# 固定費を15秒ぶんで割ることになり、CPUに余裕を持って間に合う。
correction_buffer: collections.deque = collections.deque(
    maxlen=int(config.SAMPLE_RATE * config.CORRECT_WINDOW)
)

corrector = None
if config.ENABLE_CORRECTION:
    try:
        from processing.recognition.faster_whisper_asr import FasterWhisperASR
        print(f"書き直す係({config.CORRECT_MODEL})を読み込み中...")
        corrector = FasterWhisperASR(
            model_size=config.CORRECT_MODEL,
            language=config.WHISPER_LANGUAGE,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            # 全スレッドを使うとVosk（速報字幕）から奪ってしまう。
            # 実測では2スレッドでもほぼ同じ速度なので、あえて絞る。
            cpu_threads=config.CORRECT_CPU_THREADS,
        )
        corrector.load()
        print(f"  → 訂正: 有効（{config.CORRECT_INTERVAL:.0f}秒ごとに直近{config.CORRECT_WINDOW:.0f}秒を聞き直します"
              f" / {config.CORRECT_CPU_THREADS}スレッド）")
    except Exception as e:
        print(f"  → 訂正機能を読み込めませんでした（字幕はVoskのみで通常どおり動きます）: {e}")
        corrector = None


def remember_for_correction(frame: np.ndarray) -> None:
    """あとで聞き直すために、生の音を貯めておく。"""
    if corrector is not None:
        correction_buffer.extend(frame)


# --- WebSocketクライアント管理 ---
clients: set = set()


def transcribe(audio: np.ndarray) -> str:
    return asr.transcribe(audio, config.SAMPLE_RATE)


def garbage_reason(text: str):
    """
    雑音由来のゴミ字幕なら理由を、まともな言葉ならNoneを返す。

    Voskは渡された音に必ず何か文字を当てはめるため、物音を「中」「小」のような
    1文字に化けさせる。実測では「中」「小」「中 小」「小 小 小 小」が大量に出た。
    確定時だけでなく途中経過にも同じ判定をかけること。
    途中経過を素通しにすると、確定時に捨てたゴミが画面に出たまま残る。
    """
    text = text.strip()
    if not text:
        return "空"
    tokens = text.split()
    compact = text.replace(" ", "").replace("　", "")
    # 1) 実質2文字以下（スペースを除いて数える。「中 小」もここで落ちる）
    if len(compact) < 3:
        return "短文"
    # 2) 1文字の単語ばかりで、しかも種類が2つ以下（「小 小 小 小」「中 小 中」など）。
    #    本物の日本語は3語以上あれば必ず2文字以上の語が混ざるため、これで消えない。
    if len(tokens) >= 3 and all(len(t) == 1 for t in tokens) and len(set(tokens)) <= 2:
        return "同じ1文字の繰り返し"
    return None


def record_chunk() -> np.ndarray:
    frames = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    audio, overflowed = mic_stream.read(frames)
    if overflowed:
        print("  [警告] マイク入力バッファがオーバーフローしました（処理が録音に追いついていません）")
    return to_mono(audio)


def normalize_audio(audio: np.ndarray) -> tuple:
    """ピーク音量基準で正規化する。戻り値: (正規化後の音声, 適用した増幅率)"""
    peak = float(np.max(np.abs(audio))) or 1e-6
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return np.clip(audio * gain, -1.0, 1.0), gain


def amplify_frame(frame: np.ndarray) -> np.ndarray:
    """
    ストリーミング方式（pipeline_loop_streaming）用のフレーム単位増幅。
    RMSがSILENCE_THRESHOLD未満（＝無音）の場合は増幅しない。
    無音まで一律MAX_GAIN倍すると、静けさが持ち上がってノイズになり、
    Voskが「文が終わった」と判定できなくなるため（先生の資料の指摘）。

    増幅率は「ピークがTARGET_PEAKを超えない範囲で最大MAX_GAIN倍」。
    以前の一律MAX_GAIN倍は、大きめの声で波形が上限に張り付いて激しく音割れし、
    音は届いているのにVoskが全く認識できない原因になっていた。
    """
    rms = float(np.sqrt(np.mean(frame ** 2)))
    if rms < SILENCE_THRESHOLD:
        return frame
    peak = float(np.max(np.abs(frame))) or 1e-6
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return frame * gain


async def ws_handler(websocket, path=None):
    clients.add(websocket)
    print(f"[ブラウザ接続] 現在{len(clients)}台")
    # 表示の決まり事はPython側が正とし、接続時に画面へ配る
    # （JS側にも同じ数字を書くと、片方だけ直して食い違う事故が起きるため）
    try:
        await websocket.send(json.dumps({
            "type": "config",
            "sectors": config.DIRECTION_SECTORS,
            "max_sources": config.MAX_SOUND_SOURCES,
            "sound_history": config.SOUND_EVENT_HISTORY,
            "subtitle_lines": config.SUBTITLE_LINES,
            "arc_lifetime": config.SOURCE_ARC_LIFETIME,
            "subtitle_view": config.SUBTITLE_VIEW,
        }, ensure_ascii=False))
    except Exception:
        pass
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)
        print(f"[ブラウザ切断] 残{len(clients)}台")


async def broadcast(payload: dict):
    if not clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)


async def recorder_loop(queue: asyncio.Queue):
    """
    録音だけを専門に繰り返す。認識処理（重い）とは切り離すことで、
    前の発話を処理している間もマイクを聞き続け、次の発話を取りこぼさないようにする。
    seq（録音回数の連番）は無音チャンクも含めて必ず+1されるため、
    2つのチャンクのseqが連続していれば、その間に無音（＝発話の切れ目）が
    無かったことを意味する（＝同じ文の続きの可能性が高い）。
    """
    loop = asyncio.get_event_loop()
    seq = 0
    while True:
        audio = await loop.run_in_executor(None, record_chunk)
        recent_frames.append(audio)
        remember_for_correction(audio)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        seq += 1
        if rms < SILENCE_THRESHOLD:
            print(".", end="", flush=True)
            continue
        if queue.full():
            # 処理が追いつかない時は、古い発話ではなく常に最新の発話を優先する
            try:
                queue.get_nowait()
                print("\n  [警告] 処理が追いつかないため、古い発話を破棄して最新の発話を優先します")
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait((audio, rms, seq))


# 秒: これだけ次の発話チャンクが来なければ、文が終わったとみなして表示を確定する。
# CHUNK_DURATIONより短いと、録音中の続きのチャンクを待たずに文を分割してしまうため、
# 最低でもCHUNK_DURATIONより長くする。
FLUSH_TIMEOUT = config.CHUNK_DURATION + 1.5

# 秒: 無音判定に頼らず、これだけ経ったら強制的にそこまでの内容を字幕として確定する。
# 環境ノイズがしきい値を超え続けると無音が検知できない場合、
# 字幕が永遠に確定・表示されないままになるため、その安全策として設ける。
MAX_PENDING_DURATION = 8.0


async def pipeline_loop():
    loop = asyncio.get_event_loop()
    # 多少の詰まりは全部処理できるよう猶予を持たせつつ、無限に遅延が蓄積しないよう上限は設ける
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    asyncio.create_task(recorder_loop(queue))
    print("\nマイクに向かって話しかけてください（Ctrl+C で停止）\n")

    # 長い文がチャンクの境界で分割されても1つの字幕としてまとめて表示するためのバッファ
    pending_text = ""
    pending_direction = None
    pending_last_seq = None
    pending_started_at = 0.0

    async def flush():
        nonlocal pending_text, pending_direction, pending_last_seq, pending_started_at
        if pending_text:
            print(f"[{pending_direction:.0f}°] {pending_text}")
            await broadcast({
                "type": "subtitle",
                "text": pending_text,
                "direction": pending_direction,
            })
        pending_text = ""
        pending_direction = None
        pending_last_seq = None
        pending_started_at = 0.0

    while True:
        try:
            try:
                audio, rms, seq = await asyncio.wait_for(queue.get(), timeout=FLUSH_TIMEOUT)
            except asyncio.TimeoutError:
                await flush()
                continue

            audio_amp, gain = await loop.run_in_executor(None, normalize_audio, audio)
            t_asr0 = time.time()
            print(f"\n[音声検出 RMS={rms:.4f} gain={gain:.1f}倍] 認識中...")

            text = await loop.run_in_executor(None, transcribe, audio_amp)
            print(f"  [処理時間] 認識={time.time()-t_asr0:.2f}s")
            if not text:
                # 文字が得られなくても、発話が続いている可能性があるチャンクなら
                # 連番だけは更新し、次の本物のチャンクが「文の続き」と正しく判定されるようにする
                if pending_text and pending_last_seq is not None and seq == pending_last_seq + 1:
                    pending_last_seq = seq
                continue

            direction = await loop.run_in_executor(None, estimate_direction, audio_amp)

            now = time.time()
            is_continuation = (
                pending_text
                and pending_last_seq is not None
                and seq == pending_last_seq + 1
                and now - pending_started_at < MAX_PENDING_DURATION
            )
            if is_continuation:
                pending_text += text
            else:
                await flush()
                pending_text = text
                pending_started_at = now
            pending_direction = direction
            pending_last_seq = seq

        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            continue


def record_frame() -> np.ndarray:
    frames = int(config.SAMPLE_RATE * config.FRAME_DURATION)
    audio, overflowed = mic_stream.read(frames)
    if overflowed:
        print("  [警告] マイク入力バッファがオーバーフローしました（処理が録音に追いついていません）")
    return to_mono(audio)


async def recorder_loop_streaming(queue: asyncio.Queue):
    """
    ストリーミング方式用の録音ループ。区切り判定はVosk自身の無音検知に任せるため、
    従来方式と違い無音チャンクもすべて捨てずにキューへ積み、音声を途切れさせない。
    """
    loop = asyncio.get_event_loop()
    while True:
        frame = await loop.run_in_executor(None, record_frame)
        # 音イベント検知は増幅前の生の音を使う（音量の判定を狂わせないため）
        recent_frames.append(frame)
        remember_for_correction(frame)
        if queue.full():
            try:
                queue.get_nowait()
                print("\n  [警告] 処理が追いつかないため、古いフレームを破棄します")
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(frame)


# 秒: Vosk自身の無音判定（AcceptWaveformがTrueを返すタイミング）は数秒間の完全な沈黙が
# 必要で、会話の普通の間には遅すぎることを確認した。そのため、部分認識結果(PartialResult)が
# これだけ変化しなければ「話が一段落した」とみなして先に確定させる、という二段構えにする。
# モデルの探索範囲を狭めて認識が2.7倍速くなった（実時間の74%→27%）ため、
# 以前の1.5秒から短縮して字幕の確定を早めた（2026-08-27）。
# 必ず FRAME_DURATION より長くすること。短いと、次のフレームが届いた瞬間に
# 「変化がない」と判定されて文の途中で毎回切れてしまう。
PARTIAL_STALL_TIMEOUT = 1.5


async def pipeline_loop_streaming():
    """
    Vosk本来のストリーミングAPIを使う方式。CHUNK_DURATIONで機械的に区切らず、
    音声を流し込み続けて認識器自身に文脈を持たせたまま認識する。
    そのため単語の途中で区切られにくい。区切りの確定は次の二段構え:
      1. Voskが自分で無音を検知した場合はその結果(Result)を使う（一番正確）
      2. それより前に、部分認識結果(PartialResult)がPARTIAL_STALL_TIMEOUT秒
         変化しなくなったら、そこで先に区切って確定する（体感速度のため）
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=20)
    asyncio.create_task(recorder_loop_streaming(queue))
    print("\nマイクに向かって話しかけてください（Ctrl+C で停止、ストリーミング方式）\n")

    recognizer = asr.create_recognizer(config.SAMPLE_RATE)
    utterance_frames: list = []
    last_partial_text = ""
    last_partial_change_time = time.time()
    # 診断用: 数秒ごとに生の音量と認識途中経過を表示する（音が届いているかの切り分け用）
    _diag_frame_count = 0
    _diag_max_rms = 0.0
    # VAD判定のキャッシュ（毎フレーム判定すると重いのでVAD_CHECK_INTERVALごとに更新）
    _vad_is_speech = True
    _vad_counter = 0

    async def finalize(text: str):
        nonlocal utterance_frames, last_partial_text, last_partial_change_time
        raw_audio = np.concatenate(utterance_frames) if utterance_frames else np.zeros(0, dtype=np.float32)
        utterance_frames = []
        last_partial_text = ""
        last_partial_change_time = time.time()
        # 方向検知は、Voskの認識に使ったのと同じ増幅後の音声で行う
        audio_amp = np.clip(raw_audio * MAX_GAIN, -1.0, 1.0) if len(raw_audio) else raw_audio

        text = text.strip()

        # 途中経過をすでに画面に出している場合、ここで捨てると画面に出っぱなしになる。
        # 捨てる時は必ずブラウザにも「今の途中経過を消して」と伝えること。
        async def reject(reason: str):
            print(f"  [{reason}] 「{text}」")
            await broadcast({"type": "subtitle_cancel"})

        if not text:
            await broadcast({"type": "subtitle_cancel"})
            return

        reason = garbage_reason(text)
        if reason:
            await reject(reason + "除外")
            return

        # 確定前の最終チェック: 発話全体を見て人の声でなければ字幕にしない
        if vad is not None and len(raw_audio):
            if not await loop.run_in_executor(None, vad.is_speech, raw_audio, config.SAMPLE_RATE):
                await reject("VAD 人の声ではないため除外")
                return

        direction = await loop.run_in_executor(None, estimate_direction, audio_amp)

        print(f"[{direction:.0f}°] {text}")
        await broadcast({
            "type": "subtitle",
            "text": text,
            "direction": direction,
            "is_final": True,
        })

    while True:
        try:
            frame = await queue.get()
            utterance_frames.append(frame)

            # --- 診断表示: 約30秒ごとに音量の目安を出す（声が届いているかの確認用）---
            _diag_frame_count += 1
            _diag_max_rms = max(_diag_max_rms, float(np.sqrt(np.mean(frame ** 2))))
            if _diag_frame_count >= 100:
                print(f"  [音量] 直近30秒の最大={_diag_max_rms:.4f} "
                      f"(0.02以上あれば声は十分届いています)")
                _diag_frame_count = 0
                _diag_max_rms = 0.0

            # --- 直近の音が人の声かどうかを判定（雑音を字幕にしないため）---
            # 毎フレーム判定すると重いので、VAD_CHECK_INTERVALフレームごとに更新する。
            if vad is not None:
                _vad_counter += 1
                if _vad_counter >= config.VAD_CHECK_INTERVAL:
                    _vad_counter = 0
                    tail_len = int(config.SAMPLE_RATE * config.VAD_CHECK_SECONDS)
                    tail = np.concatenate(utterance_frames)[-tail_len:]
                    _vad_is_speech = await loop.run_in_executor(
                        None, vad.is_speech, tail, config.SAMPLE_RATE
                    )

            amplified = amplify_frame(frame)
            pcm = (amplified * 32767).astype(np.int16).tobytes()
            is_final = await loop.run_in_executor(None, recognizer.AcceptWaveform, pcm)

            if is_final:
                result = json.loads(recognizer.Result())
                await finalize(result.get("text", ""))
                continue

            partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            now = time.time()
            if partial != last_partial_text:
                last_partial_text = partial
                last_partial_change_time = now
                # 画面に出すのは「人の声だと判定できていて、かつゴミではない」時だけ。
                # 確定時と同じ基準をここにもかけないと、確定時に捨てるはずのゴミが
                # 途中経過として画面に出てしまい、そのまま残る（＝ターミナルは正しいのに画面だけ変になる）。
                if partial and _vad_is_speech and garbage_reason(partial) is None:
                    # 全文が読める段階（確定前）でも先に画面へ送る。確定を待つと
                    # 実際には損をしていない時間（0.87秒 vs 1.50秒、先生の資料より）を待つことになるため。
                    direction = estimate_direction(amplified)
                    await broadcast({
                        "type": "subtitle",
                        "text": partial,
                        "direction": direction,
                        "is_final": False,
                    })
            elif partial and (now - last_partial_change_time > PARTIAL_STALL_TIMEOUT):
                # Voskの無音判定を待たず、ここで先に区切って確定する
                recognizer.Reset()
                await finalize(partial)

        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            utterance_frames = []
            continue


async def correction_loop():
    """
    一定間隔で「直近CORRECT_WINDOW秒」をWhisperに聞き直させ、
    Voskが出した粗い字幕を正しい文に書き換える係。

    発話ごとではなく一定間隔でまとめて動かすのが要点。
    Whisperは音声の長さに関係なく毎回約8秒かかるため、
    「4秒の発話ごとに8秒」では追いつかないが、「15秒ぶんに8秒」なら十分間に合う。
    """
    loop = asyncio.get_event_loop()
    need = int(config.SAMPLE_RATE * config.CORRECT_MIN_SPEECH)

    while True:
        await asyncio.sleep(config.CORRECT_INTERVAL)
        try:
            if len(correction_buffer) < need:
                continue
            audio = np.array(correction_buffer, dtype=np.float32)

            # 声がほとんど含まれていない区間は、聞き直すだけ無駄なので飛ばす
            if vad is not None:
                if not await loop.run_in_executor(None, vad.is_speech, audio, config.SAMPLE_RATE):
                    continue

            peak = float(np.max(np.abs(audio))) or 1e-6
            amp = np.clip(audio * min(TARGET_PEAK / peak, MAX_GAIN), -1.0, 1.0).astype(np.float32)

            t0 = time.time()
            try:
                text = await asyncio.wait_for(
                    loop.run_in_executor(None, corrector.transcribe, amp, config.SAMPLE_RATE),
                    timeout=config.CORRECT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                print(f"  [訂正] {config.CORRECT_TIMEOUT:.0f}秒以内に終わらなかったため今回は見送ります")
                continue
            elapsed = time.time() - t0

            text = (text or "").strip()
            if not text or garbage_reason(text):
                continue

            direction = await loop.run_in_executor(None, estimate_direction, amp)
            print(f"  [訂正] ({elapsed:.1f}秒) 「{text}」")
            await broadcast({
                "type": "correction",
                "text": text,
                "direction": direction,
                "seconds": len(audio) / config.SAMPLE_RATE,
            })
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
            continue


async def sound_event_loop():
    """
    論文2.2節の再現。SOUND_EVENT_HOP秒ごとに直近1秒の音を判定し、
    19種のどれかに当てはまれば画面へ送る。
    重い処理なので必ず別スレッド(executor)で回し、字幕の流れを止めない。
    同じ種類の音は SOUND_EVENT_COOLDOWN 秒のあいだ再表示しない（連発防止）。
    """
    loop = asyncio.get_event_loop()
    last_sent: dict = {}
    while True:
        await asyncio.sleep(config.SOUND_EVENT_HOP)
        audio = window_audio()
        if len(audio) < config.SAMPLE_RATE * config.SOUND_EVENT_WINDOW * 0.5:
            continue
        try:
            events = await loop.run_in_executor(
                None, sound_detector.detect, audio, config.SAMPLE_RATE
            )
        except Exception:
            traceback.print_exc()
            continue
        if not events:
            continue

        now = time.time()
        top = events[0]
        if now - last_sent.get(top.key, 0.0) < config.SOUND_EVENT_COOLDOWN:
            continue
        last_sent[top.key] = now

        direction = estimate_direction(audio)
        payload = top.to_dict()
        payload.update({"type": "sound_event", "direction": direction})
        print(f"  [音] {top.icon} {top.name} ({top.confidence:.0%}) {direction:.0f}°")
        await broadcast(payload)


async def direction_loop():
    """
    方向を一定間隔で送り続ける係。字幕が出た瞬間だけでなく常に送ることで、
    画面の円弧（論文Figure 1の中央部）をなめらかに動かせる。
    音が鳴っているかどうか(active)も一緒に送り、無音の時は円弧を出さない。
    """
    while True:
        await asyncio.sleep(config.DIRECTION_BROADCAST_INTERVAL)
        if not clients:
            continue
        audio = window_audio()
        if len(audio) == 0:
            continue
        rms = float(np.sqrt(np.mean(audio ** 2)))
        active = rms >= SILENCE_THRESHOLD
        if not active:
            continue
        await broadcast({
            "type": "direction",
            "direction": estimate_direction(audio),
            "level": rms,
        })


async def pipeline_loop_utterance():
    """
    Whisper系エンジン用のパイプライン。
    Voskと違い「1音ずつ流し込んで途中結果をもらう」ことができないため、
    **話し終わるまで音を貯めて、1回でまとめて渡す**方式にする。

    なぜ貯めるのか:
      Whisperは渡された音を必ず内部で30秒に引き伸ばして計算する。
      そのため2秒渡しても20秒渡しても処理時間はほぼ変わらない（実測 約2〜3秒）。
      短く刻んで何度も渡すと、計算力の大半を捨てることになる。

    どこで区切るのか:
      音量ではなくVAD（人の声かどうかの判定）を使い、
      UTTERANCE_SILENCE_HOLD秒だけ静かになったら「話し終わった」とみなす。
      単語の途中で切れないので、Voskで起きた「テスト→ベスト」のような破綻がない。
    """
    loop = asyncio.get_event_loop()
    frame_len = int(config.SAMPLE_RATE * config.UTTERANCE_FRAME)
    min_len = int(config.SAMPLE_RATE * config.UTTERANCE_MIN_SECONDS)
    max_len = int(config.SAMPLE_RATE * config.UTTERANCE_MAX_SECONDS)
    silence_frames_needed = max(1, int(config.UTTERANCE_SILENCE_HOLD / config.UTTERANCE_FRAME))

    def read_frame():
        audio, overflowed = mic_stream.read(frame_len)
        if overflowed:
            print("  [警告] マイク入力バッファがオーバーフローしました")
        return to_mono(audio)

    print("\nマイクに向かって話しかけてください（Ctrl+C で停止、発話まとめ方式）\n")

    speech_frames: list = []      # 発話中の音をここに貯める
    silence_run = 0               # 静かなフレームが何回続いたか
    diag_count, diag_max = 0, 0.0

    async def flush(reason: str):
        nonlocal speech_frames, silence_run
        audio = np.concatenate(speech_frames) if speech_frames else np.zeros(0, dtype=np.float32)
        speech_frames = []
        silence_run = 0
        if len(audio) < min_len:
            return

        peak = float(np.max(np.abs(audio))) or 1e-6
        amp = np.clip(audio * min(TARGET_PEAK / peak, MAX_GAIN), -1.0, 1.0).astype(np.float32)

        t0 = time.time()
        try:
            text = await asyncio.wait_for(
                loop.run_in_executor(None, transcribe, amp),
                timeout=config.WHISPER_TIMEOUT,
            )
        except asyncio.TimeoutError:
            # まれに同じ言葉を作り続ける暴走が起きる。待ち続けると字幕が固まるので諦める。
            print(f"  [打ち切り] {config.WHISPER_TIMEOUT}秒以内に終わらなかったため破棄しました")
            return
        elapsed = time.time() - t0

        text = (text or "").strip()
        if not text:
            await broadcast({"type": "subtitle_cancel"})
            return

        garbage = garbage_reason(text)
        if garbage:
            print(f"  [{garbage}除外] 「{text}」")
            await broadcast({"type": "subtitle_cancel"})
            return

        direction = await loop.run_in_executor(None, estimate_direction, amp)
        print(f"[{direction:.0f}°] {text}   （発話{len(audio)/config.SAMPLE_RATE:.1f}秒 / 認識{elapsed:.1f}秒 / {reason}）")
        await broadcast({
            "type": "subtitle",
            "text": text,
            "direction": direction,
            "is_final": True,
        })

    while True:
        try:
            frame = await loop.run_in_executor(None, read_frame)

            diag_count += 1
            diag_max = max(diag_max, float(np.sqrt(np.mean(frame ** 2))))
            if diag_count >= int(30 / config.UTTERANCE_FRAME):
                print(f"  [音量] 直近30秒の最大={diag_max:.4f} (0.02以上あれば声は十分届いています)")
                diag_count, diag_max = 0, 0.0

            # 人の声かどうかで区切る（音量だけでは物音と区別できないため）
            if vad is not None:
                is_speech = await loop.run_in_executor(
                    None, vad.is_speech, frame, config.SAMPLE_RATE
                )
            else:
                is_speech = float(np.sqrt(np.mean(frame ** 2))) >= SILENCE_THRESHOLD

            if is_speech:
                speech_frames.append(frame)
                silence_run = 0
                # 長く話し続けている場合も、どこかで区切って字幕を出す
                if sum(len(f) for f in speech_frames) >= max_len:
                    await flush("長さ上限")
            elif speech_frames:
                # 発話の直後の静けさも少しだけ含める（語尾が切れるのを防ぐ）
                speech_frames.append(frame)
                silence_run += 1
                if silence_run >= silence_frames_needed:
                    await flush("話し終わり")

        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            speech_frames = []
            silence_run = 0
            continue


async def main():
    # WebSocketサーバー起動
    for attempt in range(10):
        try:
            ws_server = await websockets.serve(
                ws_handler, config.WEBSOCKET_HOST, config.WEBSOCKET_PORT
            )
            break
        except OSError:
            print(f"ポート {config.WEBSOCKET_PORT} 使用中... 待機 ({attempt+1}秒)")
            await asyncio.sleep(1)
    else:
        print("エラー: WebSocketポートを開放できませんでした")
        sys.exit(1)

    print(f"[WebSocket] ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")

    # G2シミュレーター（localhost:5173）を使うため、古いブラウザ表示は自動起動しない

    # エンジンごとに最適な渡し方が違うので、ここで振り分ける。
    #   vosk    … 1音ずつ流し込んで途中結果ももらえる（ストリーミング方式）
    #   whisper … 話し終わるまで貯めて1回で渡す（発話まとめ方式）
    if config.WHISPER_ENGINE == "vosk":
        pipeline = pipeline_loop_streaming if config.STREAMING_ASR else pipeline_loop
        print(f"  → 認識方式: {'ストリーミング' if config.STREAMING_ASR else '固定長チャンク'}（Vosk）")
    else:
        pipeline = pipeline_loop_utterance
        print(f"  → 認識方式: 発話まとめ（{config.WHISPER_ENGINE} / {config.WHISPER_MODEL}）"
              f" 静かになって{config.UTTERANCE_SILENCE_HOLD}秒で区切ります")

    background = []
    if sound_detector is not None:
        background.append(asyncio.create_task(sound_event_loop()))
    background.append(asyncio.create_task(direction_loop()))
    if corrector is not None:
        background.append(asyncio.create_task(correction_loop()))

    try:
        await pipeline()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n停止しました。")
    finally:
        for task in background:
            task.cancel()
        ws_server.close()
        await ws_server.wait_closed()
        mic_stream.stop()
        mic_stream.close()


if __name__ == "__main__":
    asyncio.run(main())
