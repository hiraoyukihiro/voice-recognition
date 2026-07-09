# 音声認識システム 引き継ぎメモ
更新日: 2026-07-09

## プロジェクト場所
`C:\Users\user\Desktop\音声認識\`

## 起動方法
```
cd C:\Users\user\Desktop\音声認識
python run.py
```
ブラウザが自動で開く。開かない場合は `http://localhost:8080` を手動で開く。

---

## 現在の状態

### 完了済みステップ
| ステップ | 内容 | 備考 |
|---|---|---|
| 1 | プロジェクト雛形 | 3レイヤー分離済み |
| 2 | マイク録音・再生確認 | USBマイク認識済み |
| 3 | 音声認識（Whisper base） | 動作確認済み |
| 4 | 話者分離（resemblyzer） | 動作確認済み |
| 5 | 方向検知ダミー | DummyDOA(sweep)で実装済み |
| 6 | ブラウザ表示UI | コンパス＋字幕色分け実装済み |
| 7 | 全体結合 | run.py で一括起動 |

### 直近の未解決問題
- `http://localhost:8080` を開くと「Directory listing for /」が表示される場合がある
  - **原因**: HTTPサーバーが `output/web/` ではなくルートを配信している
  - **対処**: `run.py` の `start_http_server()` を修正済み（最新版で解決のはず）
  - **確認**: ブラウザでコンパスと字幕エリアが表示されればOK

---

## 技術構成

### 使用モデル・ライブラリ
| 用途 | ライブラリ | 設定 |
|---|---|---|
| 音声認識 | openai-whisper | モデル: base、言語: ja |
| 話者分離 | resemblyzer | 類似度閾値: 0.75 |
| 方向検知 | ダミー実装 | DummyDOA(mode="sweep") |
| 通信 | websockets | ポート: 8765 |
| Web表示 | HTML/CSS/JS | ポート: 8080 |

### 重要な設定値（config.py）
```python
WHISPER_MODEL = "base"
SAMPLE_RATE = 16000
CHUNK_DURATION = 3.0
WEBSOCKET_PORT = 8765
WEB_PORT = 8080
MIC_DEVICE_INDEX = None  # デフォルトマイク（USBマイク）
```

### 音量設定（run.py）
```python
SILENCE_THRESHOLD = 0.003  # これ以下は無音とみなす
AUDIO_GAIN = 10.0           # マイク音量が小さいため10倍増幅
```

---

## 既知の制限と今後の課題

### 同時発話問題 → reSpeaker XVF3800 対応中
- **現状**: reSpeaker XVF3800 USB 4-Mic Array を購入済み（2026-07-09時点でPC未接続）
- **実装済み**: `processing/direction/xvf3800_doa.py`（USB制御転送でAEC_AZIMUTH_VALUESを読み取り、実機DOA角度を取得）
- **依存パッケージ**: `pyusb`, `libusb-package`（インストール済み、requirements.txtにも追加済み）
- **接続後の手順**:
  1. USBでPCに接続
  2. `python tools/check_xvf3800.py` を実行し、①USB制御インターフェースが検出されること、②オーディオ入力一覧に reSpeaker/XVF/XMOS を含むデバイスが出ることを確認
  3. `config.py` の `MIC_DEVICE_INDEX` を確認できたreSpeakerの番号に変更
  4. `config.py` の `DOA_MODE` を `"mic_array"` に変更
  5. 角度がズレている場合は `XVF3800_ANGLE_OFFSET` / `XVF3800_INVERT` を調整して校正
- **未検証**: 実機接続後の動作確認（DOA角度の向き・オフセットの校正、複数話者同時発話時の精度）

### 精度向上
- Whisper `base` → `small` に変更で精度向上（ただし処理速度が落ちる）
- `config.py` の `WHISPER_MODEL = "small"` に変更するだけ

### pyannote.audio への切り替え（話者分離の精度向上）
1. HuggingFace アカウント作成: https://huggingface.co
2. 利用規約への同意が必要なモデル:
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-3.1
3. アクセストークン取得後、`pip install pyannote.audio`
4. `processing/diarization/resemblyzer_diarizer.py` を差し替え

### Even G2 対応（デザイン仕様反映済み、SDK連携は未着手）
- **2026-07-09時点**: デザイン仕様書に基づき `output/web/`（index.html/style.css/app.js）を全面刷新済み
  - レイアウト: 576×288px固定ステージ、字幕上部3行＋コンパス右下68×68px
  - 字幕: 話者色ドット(5px) + 白矢印(8方向) + 話者色テキスト、非アクティブ行は透明度0.4
  - 話者6人分の色分け（A〜F、ダーク/ライト両対応）、Even G2向けに話者記号(A/B/C…)も表示
  - コンパス: リング＋前後左右(漢字)ラベル＋緑の針（CSSアニメーションで滑らかに回転）
  - ライト/ダーク: 自動(prefers-color-scheme)＋手動切替ボタン（自動/ライト/ダーク）、localStorageに保存
  - WebSocketデータ形式を新仕様（`speaker_id`数値0-5, `direction`-180〜180, `is_active`）に対応。
    旧形式（文字列speaker_id, type:"subtitle"）も後方互換で受信可能
  - 画面右上に「サンプル表示」ボタン：バックエンド未接続でもダミーデータで見た目を確認できるシミュレーターモード
- **未対応**: `@evenrealities/even_hub_sdk`（npmパッケージ）の組み込み
  - 理由: このPCにNode.js未インストール。SDKはVite等のビルド環境が前提
  - 対応が必要になったら: Node.js 20 LTS以降をインストール →
    `npm install -g @evenrealities/evenhub-cli @evenrealities/evenhub-simulator` →
    SDKの初期化コード追加（現状は素のHTML/CSS/JSのみ。ビルド不要な範囲で実装済み）
- **要注意**: Python側（`run.py`の`broadcast()`）はまだ旧WebSocket形式で送信している。
  実際に新デザインで話者色・矢印・is_active を正しく反映させるには、`run.py`側の送信データも
  新形式（speaker_idを0始まりの数値に、directionを-180〜180に、is_activeを追加）に合わせる必要がある
- 出力レイヤー差し替え対象（将来Even G2以外に変える場合）: `output/browser_display.py` と `output/web/`

### 開発用サーバーのキャッシュ対策
- `tools/serve_web.py` を追加（`output/web/`をキャッシュ無効ヘッダー付き・マルチスレッドで配信）
- `.claude/launch.json` のプレビュー設定もこちらを使うよう変更済み
- `run.py`の`start_http_server()`にも同様のキャッシュ無効化ヘッダーと`ThreadingHTTPServer`化を適用済み
  （シングルスレッドサーバーだとブラウザの複数同時接続でハングする不具合があったため）

---

## フォルダ構成
```
音声認識/
├── run.py                  ★ メイン起動スクリプト
├── config.py               設定ファイル
├── input/                  入力レイヤー（マイク/ファイル/ダミー）
├── processing/
│   ├── direction/          方向検知（今はダミー）
│   ├── recognition/        Whisper音声認識
│   └── diarization/        話者分離（resemblyzer）
├── output/
│   ├── browser_display.py  WebSocket送信
│   └── web/                ブラウザUI（HTML/CSS/JS）
└── tools/                  動作確認スクリプト群
```
