# 全体設定
import os

# --- 入力設定 ---
MIC_DEVICE_INDEX = None   # None = 自動検出（MIC_DEVICE_NAMEで検索、失敗時のみシステムデフォルト）
MIC_DEVICE_NAME = "USB Microphone"  # 自動検出時にデバイス名でマッチさせる部分文字列
SAMPLE_RATE = 16000       # Hz (Whisperは16kHz推奨)
CHANNELS = 1              # モノラル

# --- 音声認識設定 ---
WHISPER_ENGINE = "faster_whisper"  # faster_whisper / whisper
WHISPER_MODEL = "small"   # tiny / base / small / medium / large
WHISPER_LANGUAGE = "ja"   # 日本語固定（Noneで自動検出）
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"  # CPUでの高速化（faster_whisper使用時のみ有効）

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
DIARIZER_MODE = "resemblyzer"  # resemblyzer / pyannote

# --- テストファイル ---
TEST_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "test_audio")
