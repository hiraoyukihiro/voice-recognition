# 全体設定
# 機能は3つのみ: 音声認識 / 字幕化 / 方向検知（話者分離・VAD等は2026-08-27に軽量化のため削除）

# --- 入力設定 ---
MIC_DEVICE_INDEX = None   # None = 自動検出（MIC_DEVICE_NAMEで検索、失敗時のみシステムデフォルト）
MIC_DEVICE_NAME = "reSpeaker"  # 自動検出時にデバイス名でマッチさせる部分文字列（reSpeakerが無ければシステムデフォルトにフォールバック）

# マイクの機種ごとに音量特性が違うため、実際に選ばれたデバイス名にこの部分文字列が
# 含まれていれば対応する設定を自動適用する（run.py起動時に判定、上から順に最初に一致したものを使う）。
# 新しいマイクを追加した場合はここにプロファイルを足すだけでよい。
MIC_PROFILES = {
    # 2ch混線バグを追っていた時期に原因が分からず0.00003まで下げたが、バグ修正後に実測した
    # 話し声のRMSは0.057〜0.131。0.00003は声の2000分の1で、ほぼ全ての物音を声として扱ってしまい
    # 誤認識の原因になっていたため適正値に戻した（2026-08-27）。
    "reSpeaker": {"silence_threshold": 0.005, "max_gain": 20.0},
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
# 秒: ストリーミング方式でマイクから読み込む単位。
# 0.3秒だと「テ」のような一瞬の破裂音が区切りに当たって分断され、「ベ」に化ける現象を確認した
# （同じ録音でも 0.3秒刻み→「ベスト」、1.0秒刻み→「テスト」。2026-08-27実測）。
# 長くすると子音が壊れにくくなるが、字幕が出るまでの間隔もその分伸びる。
FRAME_DURATION = 1.0

# --- 音声認識設定 ---
# すぐ字幕を出す係。faster_whisper / whisper / vosk
# Voskは「速いが文にできない」、Whisperは「正確だが1発話に約8秒」という正反対の性質。
# そこで Vosk で即座に出し、あとから Whisper が書き直す二段構えにしている（下のCORRECT_*）。
WHISPER_ENGINE = "vosk"

# tiny / base / small / medium / large（whisper系エンジン使用時のみ）
# 実測（実録音4秒×5本、int8、4スレッド、2026-08-30）:
#   tiny  幻覚だらけで使い物にならない（小さい＝速い、ではない）
#   base  平均2.2秒。文にはなるが「給食室→追加」「熱中症→熱前」と言葉を作り変える
#   small 平均9.1秒。正確（給食室・熱中症とも正解）
WHISPER_MODEL = "small"

# --- あとから書き直す係（二段構えの2段目） ---
# Voskが即座に出した粗い字幕を、Whisperが聞き直して正しい文に置き換える。
#
# なぜ間に合うのか:
#   Whisperは音声の長さに関係なく毎回約8秒かかる（内部で必ず30秒に引き伸ばすため）。
#   「4秒の発話ごとに8秒」では追いつかないが、「15秒ぶんをまとめて8秒」なら余裕で間に合う。
#   発話ごとではなく一定間隔でまとめて処理するのが要点。
ENABLE_CORRECTION = True
CORRECT_MODEL = "small"       # 書き直す係のモデル。正確さ優先なのでsmall
CORRECT_INTERVAL = 15.0       # 秒: 何秒ごとに聞き直すか
CORRECT_WINDOW = 15.0         # 秒: 一度に聞き直す長さ
CORRECT_TIMEOUT = 20.0        # 秒: これを超えたら諦める（まれな暴走対策）
CORRECT_MIN_SPEECH = 1.0      # 秒: この長さぶんも声がなければ聞き直さない（無音区間で無駄に動かさない）

# --- 発話の区切り方（whisper系エンジン使用時） ---
# Whisperは音声を必ず内部で30秒に引き伸ばして計算するため、短く刻んで何度も渡すと
# 計算力の大半を捨てることになる。そこで「話し終わるまで貯めてから1回で渡す」方式にする。
# 静かになったことをVADで検知して区切るので、単語の途中で切れる心配もない。
UTTERANCE_SILENCE_HOLD = 0.6    # 秒: これだけ静かになったら「話し終わった」とみなす
UTTERANCE_MIN_SECONDS = 0.4     # 秒: これより短い音は発話とみなさず捨てる
UTTERANCE_MAX_SECONDS = 15.0    # 秒: 話し続けている場合でも、ここで一度区切る
UTTERANCE_FRAME = 0.2           # 秒: マイクから読む単位。短いほど区切りの判定が速い
WHISPER_TIMEOUT = 6.0           # 秒: これを超えたら諦めて次へ進む（まれに起きる暴走対策）
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

# --- VAD設定（人の声かどうかの判定） ---
# 音量だけではエアコンの音などと声を区別できず、Voskが雑音に無理やり文字を当てはめて
# 意味不明な字幕を出してしまう。それを防ぐために「声かどうか」を判定してから認識にかける。
ENABLE_VAD = True
VAD_THRESHOLD = 0.15  # 高いほど声と判定されにくい。0.5だと遠くの本物の声まで捨てたため0.15に（2026-08-27実測）
VAD_CHECK_SECONDS = 1.5   # 直近何秒分を見て声かどうか判定するか
VAD_CHECK_INTERVAL = 1    # 何フレームごとに判定し直すか。FRAME_DURATIONを1.0秒にしたので毎フレーム（＝1秒ごと）で十分軽い

# --- 方向検知設定 ---
# reSpeaker XVF3800実機のみ対応（ダミー実装は削除済み。未接続時は方向なし=常に0度で起動）。
# reSpeaker XVF3800 使用時の校正パラメータ（tools/check_xvf3800.py で確認しながら調整）
XVF3800_ANGLE_OFFSET = 0.0  # 正面(0度)とのズレを補正する度数
XVF3800_INVERT = False      # 回転方向が逆に感じる場合True

# --- 表示設定 ---
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8765

# --- 音イベント検知設定（HoloSound論文の再現）---
# 「今どんな音が鳴ったか」（ノック、火災報知器、電話の着信など19種）を判定して字幕とは別枠で表示する。
# 論文: Guo et al. "HoloSound: Combining Speech and Sound Identification for DHH Users on a HMD" (ASSETS 2020)
ENABLE_SOUND_EVENT = True
SOUND_EVENT_ENGINE = "panns"     # 今はpannsのみ。差し替え時はprocessing/sound_event/に実装を足す

# 論文2.2節: 16kHzで1秒ぶんのバッファを作り、スライディングウィンドウで判定し続ける。
SOUND_EVENT_WINDOW = 1.0         # 秒: 一度に判定にかける音の長さ
SOUND_EVENT_HOP = 0.5            # 秒: 何秒ごとに判定をやり直すか（短いほど反応が速いがCPUを食う）

# 論文2.2節: 自信度50%未満・音量45dB未満は無視する。
SOUND_EVENT_MIN_CONFIDENCE = 0.7  # 0.5だと室内環境音で誤検知が多いため0.7に引き上げ
SOUND_EVENT_MIN_DB = 45.0

# dBFS（録音レベル基準の音量）→ dB SPL（実際の音の大きさ）へ変換する補正値。
# マイクの感度によって違うため、機種ごとに測らないと正しい値にならない。
# None のままだと上のSOUND_EVENT_MIN_DBによる足切りは行わず、自信度だけで判定する。
# 校正手順: python tools/calibrate_db.py （スマホの騒音計アプリと同時に測る）
SOUND_EVENT_DB_OFFSET = None

# 同じ音が連続で何度も並ぶのを防ぐ。同じ種類の音は、この秒数のあいだ再表示しない。
SOUND_EVENT_COOLDOWN = 3.0
# 人の声が主成分の時は音イベントを出さない（字幕係と役割が重なるため。論文も非音声のみ表示）
SOUND_EVENT_EXCLUDE_SPEECH = True
# 学習済みモデルの置き場所。None = ~/panns_data/Cnn14_mAP=0.431.pth を自動で使う
PANNS_CHECKPOINT = None

# --- 表示設定（HoloSound論文のUI再現）---
# 論文Figure 1: 直近3件の音を左下、最大4音源の方向を中央の円弧、字幕は上部または空間配置。
SOUND_EVENT_HISTORY = 3          # 画面に残す音イベントの件数（論文: 3件）
DIRECTION_SECTORS = 12           # 方向を何分割して表示するか（論文: 12方向）
MAX_SOUND_SOURCES = 4            # 同時に円弧を出す音源の最大数（論文: 4）
DIRECTION_BROADCAST_INTERVAL = 0.2  # 秒: 方向を画面へ送り直す間隔
SOURCE_ARC_LIFETIME = 3.0        # 秒: 音が止まってから円弧が消えるまでの時間
SUBTITLE_LINES = 3               # 字幕を何行ぶん残すか（論文の既定は2行、このアプリの仕様は3行）
SUBTITLE_VIEW = "subtitles"      # "subtitles"（画面固定）/ "windows"（方向に応じて配置）。画面でVキー切替可
