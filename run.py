"""
全体統合パイプライン（軽量版）。これ1つを実行すれば全機能が動く。
機能は3つのみ: 音声認識（マイク→文字化）／字幕化（ブラウザ表示）／方向検知（DOA）。
実行: python run.py
ブラウザで output/web/index.html が自動で開く（配信サーバーは使わずファイルを直接開く）。
"""
import asyncio
import time
import webbrowser
import traceback
import os
import sys
import numpy as np
import sounddevice as sd
import websockets
import json

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

# --- モデルロード ---
print("=" * 50)
print("  音声認識システム 起動中...")
print("=" * 50)

print("\n[1/2] 音声認識モデルをロード中...")
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

print("[2/2] ウォームアップ中（初回のみ時間がかかります）...")
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

# --- WebSocketクライアント管理 ---
clients: set = set()


def transcribe(audio: np.ndarray) -> str:
    return asr.transcribe(audio, config.SAMPLE_RATE)


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

    async def finalize(text: str):
        nonlocal utterance_frames, last_partial_text, last_partial_change_time
        raw_audio = np.concatenate(utterance_frames) if utterance_frames else np.zeros(0, dtype=np.float32)
        utterance_frames = []
        last_partial_text = ""
        last_partial_change_time = time.time()
        # 方向検知は、Voskの認識に使ったのと同じ増幅後の音声で行う
        audio_amp = np.clip(raw_audio * MAX_GAIN, -1.0, 1.0) if len(raw_audio) else raw_audio

        text = text.strip()
        if not text:
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

            # --- 診断表示: 約3秒ごとに生RMSの最大値と認識途中経過を出す ---
            _diag_frame_count += 1
            _diag_max_rms = max(_diag_max_rms, float(np.sqrt(np.mean(frame ** 2))))
            if _diag_frame_count >= 10:
                print(f"  [診断] 直近3秒の最大RMS={_diag_max_rms:.4f} "
                      f"(しきい値={SILENCE_THRESHOLD}) 途中経過=「{last_partial_text}」")
                _diag_frame_count = 0
                _diag_max_rms = 0.0

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
                if partial:
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

    # 字幕ページをブラウザで直接開く（HTTP配信サーバーは廃止しWebSocketのみ使用）
    page = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "web", "index.html")
    webbrowser.open(f"file:///{page}")
    print(f"[ブラウザ] {page} を開きます\n")

    use_streaming = config.STREAMING_ASR and config.WHISPER_ENGINE == "vosk"
    if config.STREAMING_ASR and not use_streaming:
        print("  → STREAMING_ASR=Trueですが、WHISPER_ENGINEがVoskではないため従来方式で動作します")

    try:
        if use_streaming:
            await pipeline_loop_streaming()
        else:
            await pipeline_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n停止しました。")
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        mic_stream.stop()
        mic_stream.close()


if __name__ == "__main__":
    asyncio.run(main())
