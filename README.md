# 音声認識システム

## フォルダ構成

```
音声認識/
├── input/           入力レイヤー（マイク・ファイル・ダミー）
├── processing/      処理レイヤー（方向検知・音声認識・話者分離）
│   ├── direction/   DOA（方向推定）
│   ├── recognition/ ASR（音声→テキスト）
│   └── diarization/ 話者分離
├── output/          出力レイヤー（WebSocket + ブラウザUI）
│   └── web/         HTML/CSS/JS
├── test_audio/      テスト用WAVファイル置き場
├── config.py        各種設定
├── server.py        メインパイプライン
└── requirements.txt
```

## セットアップ

```bash
pip install -r requirements.txt
```

## 起動方法

```bash
# マイク入力で起動
python server.py mic

# テスト用ファイルで起動
python server.py file test_audio/sample.wav

# ダミーデータで起動（マイク不要）
python server.py dummy
```

ブラウザで `output/web/index.html` を開く。

## ステップ別メモ

| ステップ | 内容 | 状態 |
|---|---|---|
| 1 | 雛形作成 | ✅ |
| 2 | マイク録音・再生確認 | 次 |
| 3 | 音声認識（Whisper base） | - |
| 4 | 話者分離（resemblyzer → pyannote） | - |
| 5 | 方向検知ダミー実装 | ✅（雛形に含む） |
| 6 | 表示画面作成 | ✅（雛形に含む） |
| 7 | 全体結合 | - |

## pyannote.audio への切り替え（ステップ4）

1. HuggingFace アカウントを作成: https://huggingface.co
2. 以下の2つのモデルページで利用規約に同意:
   - `pyannote/speaker-diarization-3.1`
   - `pyannote/segmentation-3.0`
3. アクセストークンを取得: Settings → Access Tokens → New token
4. `pip install pyannote.audio torch`
5. `processing/diarization/` に `pyannote_diarizer.py` を追加
6. `config.py` の `DIARIZER_MODE = "pyannote"` に変更
