# 全体設定
# 機能は3つのみ: 音声認識 / 字幕化 / 方向検知（話者分離・VAD等は2026-08-27に軽量化のため削除）

# --- 入力設定 ---
MIC_DEVICE_INDEX = None   # None = 自動検出（MIC_DEVICE_NAMEで検索、失敗時のみシステムデフォルト）
MIC_DEVICE_NAME = "reSpeaker"  # 自動検出時にデバイス名でマッチさせる部分文字列（reSpeakerが無ければシステムデフォルトにフォールバック）

# マイクの機種ごとに音量特性が違うため、実際に選ばれたデバイス名にこの部分文字列が
# 含まれていれば対応する設定を自動適用する（run.py起動時に判定、上から順に最初に一致したものを使う）。
# 新しいマイクを追加した場合はここにプロファイルを足すだけでよい。
MIC_PROFILES = {
    "reSpeaker": {"silence_threshold": 0.0015, "max_gain": 20.0},       # reSpeakerは生の話し声RMSが0.002〜0.02程度と小さく、0.0045だと声まで無音扱いになり増幅されず認識がほぼ成立しなかったため下げた
    "USB Microphone": {"silence_threshold": 0.0045, "max_gain": 50.0},  # 音量が小さいマイク
}
DEFAULT_MIC_PROFILE = {"silence_threshold": 0.003, "max_gain": 20.0}  # 未知のマイク用の標準値

# 実機を差し替えなくても、上のMIC_PROFILESのキー名（例:"USB Microphone"）を指定すれば
# 自動判定を無視してそのプロファイルを強制的に使う。「元に戻して」と言われたらNoneに戻せばよい。
FORCE_MIC_PROFILE = None  # None = 実際に接続されているマイクから自動判定
SAMPLE_RATE = 16000       # Hz (16kHz推奨)
CHUNK_DURATION = 4.0      # 秒: STREAMING_ASR=False（従来方式）の時のみ使用。一度に処理する音声の長さ
CHANNELS = 1              # モノラル

# --- ストリーミング認識設定（WHISPER_ENGINE="vosk"の時のみ有効） ---
# True: 音声を流し込み続け、Vosk自身に「文の区切り（無音）」を判定させる新方式。
#       CHUNK_DURATIONで機械的に区切らないため単語が途中で切れにくく、区切りが
#       確定した瞬間に字幕を出せるので体感速度も上がる。
# False: 従来方式（CHUNK_DURATION秒ごとに強制的に区切ってから認識にかける）。
#        何か問題があれば、ここをFalseにすればいつでも前の方式に戻せる。
STREAMING_ASR = True
FRAME_DURATION = 0.3      # 秒: ストリーミング方式でマイクから読み込む単位

# --- 音声認識設定 ---
WHISPER_ENGINE = "vosk"  # faster_whisper / whisper / vosk
WHISPER_MODEL = "small"   # tiny / base / small / medium / large（whisper系エンジン使用時のみ）
WHISPER_LANGUAGE = "ja"   # 日本語固定（Noneで自動検出）
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"  # CPUでの高速化（faster_whisper使用時のみ有効）
WHISPER_CPU_THREADS = 4        # このPCの論理コア数に合わせる

# --- Vosk設定（WHISPER_ENGINE="vosk"時のみ使用） ---
# 完全無料・オフラインで動作し、Whisperよりモデルが軽量なためこのPCのCPUでも動きやすい。
# モデルは https://alphacephei.com/vosk/models から別途ダウンロードして配置する（pipには含まれない）。
# 注意: Vosk(Kaldi)はWindowsで非ASCIIパスを正しく扱えないため、
# プロジェクトフォルダ名「音声認識」配下には置けない。ASCIIのみの場所を指定すること。
VOSK_MODEL_PATH = r"C:\Users\user\vosk-models\vosk-model-ja-0.22"  # 大型モデル（精度優先、小型モデルは同フォルダのvosk-model-small-ja-0.22）

# --- 方向検知設定 ---
# reSpeaker XVF3800実機のみ対応（ダミー実装は削除済み。未接続時は方向なし=常に0度で起動）。
# reSpeaker XVF3800 使用時の校正パラメータ（tools/check_xvf3800.py で確認しながら調整）
XVF3800_ANGLE_OFFSET = 0.0  # 正面(0度)とのズレを補正する度数
XVF3800_INVERT = False      # 回転方向が逆に感じる場合True

# --- 表示設定 ---
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765
