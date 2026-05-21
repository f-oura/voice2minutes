# voice2minutes

MacBookの純正ボイスメモの録音ファイルを文字起こしし、LLMで会議要約を作成する自動化ツール。

## 機能

- ボイスメモの最新ファイルを自動検出
- ffmpegによる音声変換（16kHz, 16bit, mono）
- faster-whisper（large-v3モデル）による日本語文字起こし
- タイムスタンプ付きの文字起こし出力
- LLMによる会議要約（Ollama または Anthropic API）

## 前提条件

- macOS (Apple Silicon環境推奨)
- Python 3.10+
- ffmpeg

## インストール

### 1. ffmpegのインストール

```bash
brew install ffmpeg
```

### 2. Pythonライブラリのインストール

```bash
pip install -r requirements.txt
```

### 3. （オプション）Ollamaのセットアップ

ローカルLLMで要約する場合：

```bash
# Ollamaのインストール
brew install ollama

# Ollamaサービスの起動
ollama serve

# モデルのダウンロード（別ターミナルで）
ollama pull llama3:8b
```

### 4. （オプション）Anthropic APIキーの設定

Anthropic APIで要約する場合：

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## 使い方

### 基本的な使い方

```bash
# 最新のボイスメモを処理（Ollamaで要約）
python voice2minutes.py

# 特定のファイルを指定
python voice2minutes.py -i /path/to/audio.m4a
```

### 要約方法の選択

```bash
# Ollamaで要約（デフォルト）
python voice2minutes.py --summarizer ollama

# Anthropic APIで要約
python voice2minutes.py --summarizer anthropic

# 要約をスキップ（文字起こしのみ）
python voice2minutes.py --summarizer none
# または
python voice2minutes.py --no-summary
```

### その他のオプション

```bash
# 出力ディレクトリを指定
python voice2minutes.py -o /path/to/output

# Ollamaの別モデルを使用
python voice2minutes.py --ollama-model gemma2:9b

# Whisperの小さいモデルを使用（高速化）
python voice2minutes.py --whisper-model medium

# 変換したWAVファイルを保持
python voice2minutes.py --keep-wav

# 詳細ログ
python voice2minutes.py -v
```

### 全オプション一覧

```
usage: voice2minutes.py [-h] [-i INPUT] [-o OUTPUT_DIR]
                        [--summarizer {ollama,anthropic,none}]
                        [--ollama-model OLLAMA_MODEL] [--ollama-url OLLAMA_URL]
                        [--anthropic-key ANTHROPIC_KEY]
                        [--whisper-model WHISPER_MODEL] [--no-summary]
                        [--keep-wav] [-v]

オプション:
  -i, --input           入力音声ファイルのパス（省略時は最新のボイスメモを使用）
  -o, --output-dir      出力ディレクトリ（デフォルト: カレントディレクトリ）
  --summarizer          要約に使用するLLM（ollama/anthropic/none）
  --ollama-model        Ollamaで使用するモデル（デフォルト: llama3:8b）
  --ollama-url          OllamaのベースURL（デフォルト: http://localhost:11434）
  --anthropic-key       Anthropic APIキー
  --whisper-model       Whisperモデルサイズ（デフォルト: large-v3）
  --no-summary          要約をスキップ
  --keep-wav            変換したWAVファイルを保持
  -v, --verbose         詳細なログ出力
```

## 出力ファイル

- `{ファイル名}_{日時}_transcript.txt` - タイムスタンプ付き文字起こし
- `{ファイル名}_{日時}_summary.md` - 会議要約（Markdown形式）

## トラブルシューティング

### ffmpegが見つからない

```bash
brew install ffmpeg
```

### faster-whisperのインポートエラー

```bash
pip install --upgrade faster-whisper
```

### Ollamaに接続できない

```bash
# Ollamaが起動しているか確認
ollama serve

# モデルがダウンロードされているか確認
ollama list
```

### Anthropic APIエラー

- APIキーが正しく設定されているか確認
- APIの利用制限に達していないか確認

## ライセンス

MIT License
