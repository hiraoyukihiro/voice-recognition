# 全体設定
import os

# --- 入力設定 ---
MIC_DEVICE_INDEX = None   # None = 自動検出（MIC_DEVICE_NAMEで検索、失敗時のみシステムデフォルト）
MIC_DEVICE_NAME = "USB Microphone"  # 自動検出時にデバイス名でマッチさせる部分文字列（reSpeakerを外し通常のUSBマイクに変更）
SAMPLE_RATE = 16000       # Hz (Whisperは16kHz推奨)
CHUNK_DURATION = 4.0      # 秒: 一度に処理する音声の長さ（短いと単語の途中で切れて誤認識するため、字幕速度より精度優先で長めに）
CHANNELS = 1              # モノラル

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
# pyannote側の実装は残してあるので、値を"pyannote"に戻せばいつでも再度試せる。
DIARIZER_MODE = "resemblyzer"  # resemblyzer / pyannote

# --- テストファイル ---
TEST_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "test_audio")
