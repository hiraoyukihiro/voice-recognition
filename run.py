"""
全体統合パイプライン。これ1つを実行すれば全機能が動く。
実行: python run.py
ブラウザで http://localhost:8080 が自動で開く。
"""
import asyncio
import http.server
import threading
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
# 注記: sd.InputStream（連続録音）はこの環境ではどのバックエンドでも無音になる不具合を確認したため、
# sd.rec()による固定長チャンク方式を使用する。また0.3秒未満の短い録音はデバイスの
# ウォームアップ時間だけで終わり実音声を拾えないため、チャンクは短くしすぎない。
SILENCE_THRESHOLD = 0.0045  # 今の環境ノイズフロア(RMS約0.003〜0.008)より上に設定。下げすぎると無音を検知できず字幕が確定されなくなる
OVERLAP_RMS_RATIO = 2.0

# --- 音量正規化設定 ---
# 固定倍率だと声の大小でWhisperの精度が変わるため、ピーク音量基準で正規化する
TARGET_PEAK = 0.7
MAX_GAIN = 20.0  # reSpeaker接続により信号が強くなったため上限を下げる

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

print("[2/3] 話者識別モデルをロード中...")
if config.DIARIZER_MODE == "pyannote":
    import getpass
    hf_token = getpass.getpass(
        "HuggingFaceアクセストークンを入力してください（画面には表示されません。ファイルには保存されません）: "
    )
    from processing.diarization.pyannote_diarizer import PyannoteEmbedder
    embedder = PyannoteEmbedder(hf_token)
    embedder.load()
    hf_token = None  # メモリ上の参照を手放す（load()側でも既に破棄済み）

    def get_embedding(audio: np.ndarray) -> np.ndarray:
        return embedder.embed(audio, config.SAMPLE_RATE)
else:
    from resemblyzer import VoiceEncoder, preprocess_wav
    encoder = VoiceEncoder()

    def get_embedding(audio: np.ndarray) -> np.ndarray:
        wav = preprocess_wav(audio, source_sr=config.SAMPLE_RATE)
        return encoder.embed_utterance(wav)

print("[3/3] ウォームアップ中（初回のみ時間がかかります）...")
_dummy = np.zeros(config.SAMPLE_RATE * 3, dtype=np.float32)
asr.transcribe(_dummy, config.SAMPLE_RATE)

print("\n全モデルロード完了\n")

# --- 話者管理 ---
# しきい値はresemblyzerとpyannote.audioで埋め込みベクトルのスコア傾向が異なるため別々に設定する
speaker_embeddings: dict[str, np.ndarray] = {}
speaker_count = 0
if config.DIARIZER_MODE == "pyannote":
    SIMILARITY_THRESHOLD = 0.5    # これ以上なら確実に同一話者とみなす（pyannote用に調整中）
    NEW_SPEAKER_THRESHOLD = 0.15  # これ未満なら確実に新しい話者（pyannote用に調整中）
else:
    SIMILARITY_THRESHOLD = 0.75   # これ以上なら確実に同一話者とみなす
    NEW_SPEAKER_THRESHOLD = 0.35  # これ未満なら確実に新しい話者。マイク音質が悪く同一人物でも声の特徴がブレるため低めに設定
EMBEDDING_UPDATE_RATE = 0.3       # 高確信度で一致した際、話者の声の特徴を少しずつ更新する重み
NEW_SPEAKER_COOLDOWN = 8.0        # 秒: 新規話者登録の最短間隔。声のブレによる誤った新規話者登録の連発を防ぐ
last_speaker_id = "speaker_1"
last_rms = 0.0
last_new_speaker_time = 0.0

# --- 方向検知 ---
if config.DOA_MODE == "mic_array":
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
        print("  → reSpeakerが見つからないため、ダミー方向検知にフォールバックします")
        from processing.direction.dummy_doa import DummyDOA
        doa = DummyDOA(mode="sweep")
    else:
        print("  → 方向検知: reSpeaker XVF3800（実機）")
else:
    from processing.direction.dummy_doa import DummyDOA
    doa = DummyDOA(mode="sweep")
    print("  → 方向検知: ダミー（sweep）")

# --- WebSocketクライアント管理 ---
clients: set = set()


def identify_speaker(audio: np.ndarray, current_rms: float) -> str:
    global speaker_count, last_speaker_id, last_rms, last_new_speaker_time
    try:
        if last_rms > SILENCE_THRESHOLD and current_rms > last_rms * OVERLAP_RMS_RATIO:
            return last_speaker_id
        if len(audio) < config.SAMPLE_RATE * 0.5:
            return last_speaker_id
        embedding = get_embedding(audio)
        # resemblyzer/pyannoteどちらでも比較できるよう、正規化してコサイン類似度として扱う
        embedding = embedding / (np.linalg.norm(embedding) or 1.0)
        best_id, best_score = None, -1.0
        for spk_id, emb in speaker_embeddings.items():
            score = float(np.dot(embedding, emb))
            if score > best_score:
                best_score = score
                best_id = spk_id

        print(f"  [話者スコア] best_id={best_id} best_score={best_score:.3f}")
        now = time.time()
        if best_id is None or (
            best_score < NEW_SPEAKER_THRESHOLD
            and now - last_new_speaker_time > NEW_SPEAKER_COOLDOWN
        ):
            # 確実に新しい話者。ただし直近で新規登録したばかりの場合は
            # 同時発話で声が混ざったブレの可能性が高いため、登録を抑制してcooldown中は既存話者に割り当てる
            speaker_count += 1
            best_id = f"speaker_{speaker_count}"
            speaker_embeddings[best_id] = embedding
            last_new_speaker_time = now
            print(f"  → 新しい話者を検出: {best_id}")
        elif best_score >= SIMILARITY_THRESHOLD:
            # 高確信度の一致：声の特徴を少しずつ更新し、自然な声の変化に追従させる
            speaker_embeddings[best_id] = (
                (1 - EMBEDDING_UPDATE_RATE) * speaker_embeddings[best_id]
                + EMBEDDING_UPDATE_RATE * embedding
            )
        # NEW_SPEAKER_THRESHOLD以上SIMILARITY_THRESHOLD未満（不確実な一致）の場合は
        # 同時発話などで声が混ざった可能性が高いため、既存の推定話者に割り当てるだけで登録は更新しない

        last_speaker_id = best_id
        return best_id
    except Exception as e:
        return last_speaker_id


def transcribe(audio: np.ndarray) -> str:
    return asr.transcribe(audio, config.SAMPLE_RATE)


def record_chunk() -> np.ndarray:
    frames = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    audio = sd.rec(frames, samplerate=config.SAMPLE_RATE, channels=1,
                   dtype="float32", device=mic_device_index)
    sd.wait()
    return audio[:, 0]


ENABLE_NOISE_REDUCTION = False  # 1〜2秒の処理時間増がキュー詰まり・警告連発を悪化させるため無効化


def normalize_audio(audio: np.ndarray) -> tuple:
    """
    （必要なら）ノイズ除去してからピーク音量基準で正規化する。
    マイクの物理的な感度が低く強い増幅が必要なため、増幅前にノイズ除去を挟むと
    ノイズも一緒に増幅されてしまうのを軽減できるが、処理時間が1〜2秒増える。
    戻り値: (正規化後の音声, 適用した増幅率)
    """
    if ENABLE_NOISE_REDUCTION:
        import noisereduce as nr
        audio = nr.reduce_noise(y=audio, sr=config.SAMPLE_RATE)
    peak = float(np.max(np.abs(audio))) or 1e-6
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return np.clip(audio * gain, -1.0, 1.0), gain


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


def start_http_server():
    """output/web/ を HTTP で配信するサーバーをスレッドで起動"""
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "web")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
        def log_message(self, *args):
            pass  # アクセスログを非表示
        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            super().end_headers()

    server = http.server.ThreadingHTTPServer(("", config.WEB_PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[HTTP] http://localhost:{config.WEB_PORT}")


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
# 環境ノイズがしきい値を超え続けると無音が検知できず、話者も変わらない場合
# 字幕が永遠に確定・表示されないままになるため、その安全策として設ける。
MAX_PENDING_DURATION = 8.0


async def pipeline_loop():
    global last_rms
    loop = asyncio.get_event_loop()
    # 多少の詰まりは全部処理できるよう猶予を持たせつつ、無限に遅延が蓄積しないよう上限は設ける
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    asyncio.create_task(recorder_loop(queue))
    print("\nマイクに向かって話しかけてください（Ctrl+C で停止）\n")

    # 長い文がチャンクの境界で分割されても1つの字幕としてまとめて表示するためのバッファ
    pending_text = ""
    pending_speaker_id = None
    pending_direction = None
    pending_last_seq = None
    pending_started_at = 0.0

    async def flush():
        nonlocal pending_text, pending_speaker_id, pending_direction, pending_last_seq, pending_started_at
        if pending_text:
            print(f"[{pending_speaker_id} | {pending_direction:.0f}°] {pending_text}")
            await broadcast({
                "type": "subtitle",
                "speaker_id": pending_speaker_id,
                "text": pending_text,
                "direction": pending_direction,
            })
        pending_text = ""
        pending_speaker_id = None
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

            t0 = time.time()
            audio_amp, gain = await loop.run_in_executor(None, normalize_audio, audio)
            t_norm1 = time.time()
            print(f"\n[音声検出 RMS={rms:.4f} gain={gain:.1f}倍] 認識中...")

            text = await loop.run_in_executor(None, transcribe, audio_amp)
            t_asr1 = time.time()
            print(f"  [処理時間] ノイズ除去={t_norm1-t0:.2f}s 認識={t_asr1-t_norm1:.2f}s")
            if not text:
                last_rms = rms
                # 文字が得られなくても、直前と同じ話者が続いている可能性があるチャンクなら
                # 連番だけは更新し、次の本物のチャンクが「文の続き」と正しく判定されるようにする
                if pending_text and pending_last_seq is not None and seq == pending_last_seq + 1:
                    pending_last_seq = seq
                continue

            direction = await loop.run_in_executor(None, doa.estimate, audio_amp)
            t_spk0 = time.time()
            speaker_id = await loop.run_in_executor(
                None, identify_speaker, audio_amp, rms
            )
            print(f"  [処理時間] 話者判定={time.time()-t_spk0:.2f}s")
            last_rms = rms

            now = time.time()
            is_continuation = (
                pending_text
                and pending_speaker_id == speaker_id
                and pending_last_seq is not None
                and seq == pending_last_seq + 1
                and now - pending_started_at < MAX_PENDING_DURATION
            )
            if is_continuation:
                pending_text += text
            else:
                await flush()
                pending_text = text
                pending_speaker_id = speaker_id
                pending_started_at = now
            pending_direction = direction
            pending_last_seq = seq

        except KeyboardInterrupt:
            raise
        except Exception:
            traceback.print_exc()
            continue


async def main():
    # HTTPサーバー起動
    start_http_server()

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

    # ブラウザを自動で開く
    url = f"http://localhost:{config.WEB_PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"[ブラウザ] {url} を自動で開きます\n")

    try:
        await pipeline_loop()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n停止しました。")
    finally:
        ws_server.close()
        await ws_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
