# 音声認識システム 引き継ぎメモ
更新日: 2026-08-27

## 重要: 2026-08-27に大幅軽量化（機能を3つに絞った）
動作が重く実用にならなかったため、以下の3機能だけを残して他は削除した:
1. **音声認識**（マイク→Vosk→文字化）
2. **字幕化**（WebSocket→ブラウザ表示）
3. **方向検知**（reSpeaker XVF3800 DOA、未接続時はダミー）

削除したもの: 話者分離（direction/resemblyzer/pyannote全実装）、話者色分け表示、
コンパスUI、テーマ切替、デモモード、VAD、ノイズ除去、HTTP配信サーバー（字幕ページは
`output/web/index.html` をfile://で直接開く方式に変更。ポート8080は使わなくなった）、
旧世代パイプライン(run_step3/4.py, server.py)。
軽量化前の全機能版は git履歴と `C:\Users\user\Desktop\音声認識_安定版\`（別スナップショット）に残っている。

## プロジェクト場所
`C:\Users\user\Desktop\音声認識\`

## 起動方法
```
cd C:\Users\user\Desktop\音声認識
python run.py
```
ブラウザが自動で開く。開かない場合は `output/web/index.html` を手動で開く（HTTPサーバーは廃止済み）。

診断ツール:
```
python tools/list_mics.py        # 接続中のマイク一覧
python tools/check_xvf3800.py    # reSpeaker XVF3800のUSB制御・オーディオ入力の検出確認
python tools/check_vosk.py       # Voskモデルのロード確認＋マイク録音での文字起こしテスト
python tools/check_mic_gap.py    # マイク録音方式の診断
```

---

## 現在の状態（2026-07-23時点）

### 完了済み
| 項目 | 内容 |
|---|---|
| 3層分離 | 入力(input/)・処理(processing/)・出力(output/)を維持 |
| 音声認識 | `openai-whisper` → `faster-whisper` に切り替え済み（`small`モデル、`beam_size=1`、`int8`）。2026-07-23、携帯性・無料運用を優先し`vosk`エンジンを追加、デフォルトを`config.WHISPER_ENGINE="vosk"`に変更（完全無料・オフライン・軽量。`vosk-model-small-ja-0.22`使用） |
| 話者分離 | `resemblyzer`（デフォルト。2026-07-23、pyannoteの激重フリーズ回避のため戻した）と`pyannote.audio`（`pyannote/embedding`）の両対応。`config.DIARIZER_MODE`で切替 |
| 方向検知 | reSpeaker XVF3800実機のDOA取得に対応（`DOA_MODE="mic_array"`、未接続時はダミーに自動フォールバック） |
| マイク自動検出 | `input/mic_input.py`の`find_input_device()`で、デバイス名+ホストAPIから自動解決 |
| 録音/認識の並行処理 | `recorder_loop`と`pipeline_loop`を分離し、認識処理中もマイクを聞き続ける |
| 長文の自動結合 | チャンク境界をまたいだ発話を連番(seq)で検出し、1つの字幕にまとめて表示 |
| 幻覚(ハルシネーション)対策 | キーワードベースで「ご視聴ありがとうございました」「お疲れ様でした」等の定型文を除去＋セグメント単位の`no_speech_prob`しきい値フィルタ |
| 出力UI | デザイン仕様に沿って刷新済み（576×288、字幕上部3行+コンパス右下、ライト/ダーク切替） |

### ハードウェア構成
- **メインPC**: Intel Core i5-4310M（2014年頃、2コア4スレッド）、メモリ8.5GB
  - → **Whisperの認識処理そのものが1回あたり約7秒かかるのがこのPCの性能上の限界**。これ以上はモデル/パラメータの調整では大きく縮まらないことを確認済み（medium/tiny/beam_size/CPUスレッド数など一通り試した結果）
- **マイク**: 2種類を切り替えて使用中
  1. 汎用USBマイク（感度が低く、増幅が必要。`MIC_DEVICE_NAME="USB Microphone"`）
  2. **reSpeaker XVF3800 USB 4-Mic Array**（`MIC_DEVICE_NAME="reSpeaker"`）: マイクとしてもDOA(方向検知)実機としても使用可能。ただし過去にWindows側のドライバー・電源供給に起因する接続不安定の問題があった（USBポート直挿し推奨）
- マイクを差し替えた際は、`config.py`の`MIC_DEVICE_NAME`と、`run.py`冒頭の`SILENCE_THRESHOLD`/`MAX_GAIN`を、使用マイクに合わせて変更すること（下記「切り替え早見表」参照）

### マイク切り替え早見表
| マイク | `MIC_DEVICE_NAME` | `SILENCE_THRESHOLD`(run.py) | `MAX_GAIN`(run.py) |
|---|---|---|---|
| 汎用USBマイク（感度低い） | `"USB Microphone"` | `0.0001` | `100.0` |
| reSpeaker XVF3800 | `"reSpeaker"` | `0.003` | `20.0` |

---

## 技術構成

### 使用モデル・ライブラリ
| 用途 | ライブラリ | 設定 |
|---|---|---|
| 音声認識 | faster-whisper | モデル: small、言語: ja、beam_size=1、int8、cpu_threads=4 |
| 話者分離 | resemblyzer or pyannote.audio(pyannote/embedding) | `config.DIARIZER_MODE`で切替。しきい値は方式ごとに別設定 |
| 方向検知 | reSpeaker XVF3800実機 or ダミー | `config.DOA_MODE`で切替 |
| ノイズ除去 | noisereduce | `run.py`の`ENABLE_NOISE_REDUCTION`で有効/無効切替（現在False。有効にすると+1〜2秒） |
| 通信 | websockets | ポート: 8765 |
| Web表示 | HTML/CSS/JS | ポート: 8080（`tools/serve_web.py`でキャッシュ無効化配信） |

### 話者分離のしきい値（run.py内、DIARIZER_MODEごとに自動切替）
```python
# resemblyzer
SIMILARITY_THRESHOLD = 0.75   # これ以上で同一話者
NEW_SPEAKER_THRESHOLD = 0.35  # これ未満で新規話者

# pyannote（resemblyzerよりスコアが全体的に低く出る傾向。調整途上）
SIMILARITY_THRESHOLD = 0.5
NEW_SPEAKER_THRESHOLD = 0.15
```
`NEW_SPEAKER_COOLDOWN = 8.0`秒（新規話者登録の連発防止）、`EMBEDDING_UPDATE_RATE = 0.3`（高確信度一致時に声の特徴を少しずつ更新）。

### 主要パイプライン設定（run.py / config.py）
```python
CHUNK_DURATION = 1.5       # 秒（reSpeaker接続時に短縮を検証中。短すぎると認識漏れ増加に注意）
FLUSH_TIMEOUT = CHUNK_DURATION + 1.5  # これだけ次のチャンクが来なければ文を確定
queue maxsize = 8          # 処理待ち音声チャンクの上限。溢れたら最新優先で古いものを破棄
```

---

## 既知の問題・未解決事項

### 1. Whisper認識速度がこのPCの性能限界（根本解決は困難）
- 1発話(1.5〜3秒)あたり約7秒かかる。continuous に話し続けると処理待ちキューが溜まり、
  古い発話が破棄されるか、字幕が遅延して蓄積する（`queue maxsize=8`で多少緩和）
- 試して効果がなかった/悪化したもの: `tiny`モデル（幻覚で逆に遅くなり精度も悪化）、チャンク1.2秒（認識漏れ増加）
- 抜本解決には次のいずれかが必要（ユーザーは一旦ローカル処理継続を選択）:
  - クラウド音声認識API（Google/Azure等）への切り替え
  - より高性能なPC/GPUの用意

### 2. pyannote.audio導入に伴う不安定さ（2026-07-23時点でresemblyzerに戻して回避中）
- **対応**: 「原因不明の激重フリーズ」がキュー溢れ・長時間無認識の最有力原因だったため、`config.DIARIZER_MODE`を`"resemblyzer"`に戻した。pyannote側の実装は残してあり、いつでも切り戻せる
- 以下は切り戻す場合の既知の注意点（調査中のまま）
- **HuggingFace関連の既知の落とし穴**（解決済みだが再発しうる）:
  - `huggingface_hub`が1.x系だと`pyannote.audio 4.0.7`のgatedモデル取得が`401 GatedRepoError`で失敗する
    → `pip install "huggingface_hub<1.0"`で固定（`requirements.txt`に記載済み）
  - `omegaconf`が自動インストールされないため`pip install omegaconf`が別途必要（`requirements.txt`に記載済み）
  - `pyannote/embedding`は`pyannote/speaker-diarization-3.1`等とは**別に**HuggingFace上でゲート同意が必要
- **しきい値が未調整**: pyannote版のSIMILARITY_THRESHOLD/NEW_SPEAKER_THRESHOLDは暫定値。実データでの再調整が必要
- **原因不明の激重フリーズ**: 通常7秒程度の認識処理が、稀に132秒・517秒など異常に長くかかることがある。
  熱暴走ではないことは確認済み。メモリは8.5GB中6GB使用と余裕は少なめ（pyannote.audio(PyTorch)導入で使用量増加）。
  Windows Defenderのリアルタイムスキャン等、他の要因も疑われるが未特定
- ユーザーは「pyannote.audioの安定化を続ける」か「resemblyzerに戻す」かを保留中

### 3. reSpeaker XVF3800の接続不安定性
- 過去にWindows側でドライバーが一切当たらない（Code 28）、Zadigで解決したがマイクとして認識されなくなる、
  という問題があった。現状はマイク+DOA制御の両方が動く状態まで来ているが、**USB切断・再接続を繰り返すと
  再発する可能性がある**ため、`tools/check_xvf3800.py`で毎回接続確認してから使うこと

### 4. Voskモデルの配置場所（重要・Windows固有の地雷）
- Vosk(内部でKaldiのC++実装)はWindowsで非ASCIIパスのモデル読み込みに失敗する。
  このプロジェクトのフォルダ名「音声認識」自体が非ASCIIのため、**プロジェクト内(`models/`等)にはVoskモデルを置けない**
- そのため`config.VOSK_MODEL_PATH`は `C:\Users\user\vosk-models\vosk-model-small-ja-0.22` というASCIIのみの固定パスを直接指定している。他のPCに移行する際もこの制約を忘れないこと
- 精度が足りない場合は同じ場所に`vosk-model-ja-0.22`(1GB、高精度版)を追加ダウンロードし、`VOSK_MODEL_PATH`を切り替えれば良い

### 5. Even G2対応（SDK連携は未着手）
- 出力UI（`output/web/`）はデザイン仕様通り実装済み、PCブラウザで動作確認済み
- `@evenrealities/even_hub_sdk`の組み込みは未着手（このPCにNode.js未インストールのため）
- Python側(`run.py`の`broadcast()`)は新WebSocket形式（`speaker_id`数値、`direction`-180〜180、`is_active`）に
  まだ対応していない。現状は旧形式（文字列speaker_id、`type:"subtitle"`）のまま送信しており、
  フロントエンドの新デザインとは後方互換のみで正式対応していない

---

## フォルダ構成
```
音声認識/
├── run.py                          ★ メイン起動スクリプト
├── config.py                       設定ファイル
├── input/
│   └── mic_input.py                マイク抽象化・自動デバイス検出
├── processing/
│   ├── direction/
│   │   ├── dummy_doa.py            ダミー方向検知
│   │   └── xvf3800_doa.py          reSpeaker実機DOA
│   ├── recognition/
│   │   ├── whisper_asr.py          openai-whisper実装（フォールバック）
│   │   ├── faster_whisper_asr.py   faster-whisper実装
│   │   └── vosk_asr.py             Vosk実装（メイン。無料・オフライン・軽量）
│   └── diarization/
│       ├── resemblyzer_diarizer.py resemblyzer実装
│       └── pyannote_diarizer.py    pyannote.audio(embedding)実装
├── output/
│   ├── browser_display.py          WebSocket送信
│   └── web/                        ブラウザUI（HTML/CSS/JS）
└── tools/
    ├── list_mics.py                 マイク一覧
    ├── check_xvf3800.py             reSpeaker接続診断
    ├── check_hf_token.py            HuggingFaceトークン診断
    ├── check_vosk.py                Voskモデルロード・文字起こし確認
    └── serve_web.py                 output/web/ 単体プレビュー用サーバー
```
