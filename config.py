# 全体設定
import os

# --- 入力設定 ---
MIC_DEVICE_INDEX = None   # None = 自動検出（MIC_DEVICE_NAMEで検索、失敗時のみシステムデフォルト）
MIC_DEVICE_NAME = "reSpeaker"  # 自動検出時にデバイス名でマッチさせる部分文字列（USBマイクを外しreSpeakerに変更）

# マイクの機種ごとに音量特性が違うため、実際に選ばれたデバイス名にこの部分文字列が
# 含まれていれば対応する設定を自動適用する（run.py起動時に判定、上から順に最初に一致したものを使う）。
# 新しいマイクを追加した場合はここにプロファイルを足すだけでよい。
MIC_PROFILES = {
    "reSpeaker": {"silence_threshold": 0.0045, "max_gain": 20.0},       # しきい値はUSBマイクと共通化。増幅上限はビームフォーミング内蔵で信号が強いため低め
    "USB Microphone": {"silence_threshold": 0.0045, "max_gain": 50.0},  # 音量が小さいマイク
}
DEFAULT_MIC_PROFILE = {"silence_threshold": 0.003, "max_gain": 20.0}  # 未知のマイク用の標準値

# 実機を差し替えなくても、上のMIC_PROFILESのキー名（例:"USB Microphone"）を指定すれば
# 自動判定を無視してそのプロファイルを強制的に使う。「元に戻して」と言われたらNoneに戻せばよい。
FORCE_MIC_PROFILE = None  # None = 実際に接続されているマイクから自動判定
SAMPLE_RATE = 16000       # Hz (Whisperは16kHz推奨)
CHUNK_DURATION = 4.0      # 秒: STREAMING_ASR=False（従来方式）の時のみ使用。一度に処理する音声の長さ
CHANNELS = 1              # モノラル

# --- ストリーミング認識設定（WHISPER_ENGINE="vosk"の時のみ有効） ---
# True: 音声を流し込み続け、Vosk自身に「文の区切り（無音）」を判定させる新方式。
#       CHUNK_DURATIONで機械的に区切らないため単語が途中で切れにくく、区切りが
#       確定した瞬間に字幕を出せるので体感速度も上がる。
# False: 従来方式（CHUNK_DURATION秒ごとに強制的に区切ってから認識にかける）。
#        何か問題があれば、ここをFalseにすればいつでも前の方式に戻せる。
STREAMING_ASR = True
FRAME_DURATION = 0.3      # 秒: ストリーミング方式でマイクから読み込む単位。
# 以前は「毎回マイクを開き直す」実装だったため、短くしすぎるとデバイスのウォームアップ時間
# だけで終わっていたが、開きっぱなしのInputStreamに変更した現在はその制約はない。
# 値を小さくすると途中経過(partial)の更新頻度が上がり体感速度が上がる可能性があるが、
# 未検証のため変更する場合は実際に喋って試すこと。

# --- 音声認識設定 ---
WHISPER_ENGINE = "vosk"  # faster_whisper / whisper / vosk
WHISPER_MODEL = "small"   # tiny / base / small / medium / large（tinyはハルシネーションで逆に遅くなり精度も悪化したため不採用）
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

# --- VAD設定（音声区間検出） ---
# 音量(SILENCE_THRESHOLD)だけでは車の音などの非音声ノイズと声を区別できないため、
# Silero VAD（無料・オフライン・軽量）で「人の声かどうか」を判定してから認識にかける。
ENABLE_VAD = False  # 実際の声まで「声ではない」とスキップする誤判定が目立つため一旦無効化。ノイズ由来の誤字幕が増えるようなら閾値を下げた上で再有効化を検討
VAD_THRESHOLD = 0.35  # 0〜1。高いほど声と判定されにくくなる。小さい声を誤ってノイズ判定しないよう下げた（誤検知が多ければ上げる）

# --- 方向検知設定 ---
DOA_MODE = "mic_array"    # dummy / mic_array / even_g2

# reSpeaker XVF3800 使用時の校正パラメータ（tools/check_xvf3800.py で確認しながら調整）
XVF3800_ANGLE_OFFSET = 0.0  # 正面(0度)とのズレを補正する度数
XVF3800_INVERT = False      # 回転方向が逆に感じる場合True

# --- 表示設定 ---
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765
WEB_PORT = 8080

# --- 話者分離設定 ---
# pyannoteは精度が高いが数百秒単位でフリーズする既知の不具合があり、
# フリーズ中はキューが溢れ続けて長時間認識が止まる原因になるためresemblyzerに戻した。
# その後、先生の引き継ぎ資料（why-we-changed.pdf）の提案で方向(DOA)ベースに変更した。
# 「誰なのか」ではなく「さっきと違う方向から聞こえた」の区別だけでよく、方向はXVF3800が
# 教えてくれるため声の特徴量計算そのものが不要になる（軽量・フリーズなし）。
# 弱点: 同じ方向の2人は区別できない／話者が動くと別人扱いになる／反響の多い部屋では方向がぶれる。
# 声ベースに戻す場合は"resemblyzer"か"pyannote"に（実装は残してある）。
DIARIZER_MODE = "direction"  # direction / resemblyzer / pyannote
DIRECTION_ANGLE_TOLERANCE = 30.0  # 度: これ以内の方向差なら同一話者とみなす（processing/diarization/direction_diarizer.py）

# --- テストファイル ---
TEST_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "test_audio")
