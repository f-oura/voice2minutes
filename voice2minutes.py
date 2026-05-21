#!/usr/bin/env python3
"""
voice2minutes - ボイスメモ文字起こし＆会議要約ツール

MacBookの純正ボイスメモの録音ファイルを文字起こしし、
LLMで会議要約を作成する自動化スクリプト。
"""

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ボイスメモのデフォルトディレクトリ
VOICE_MEMOS_DIR = Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"


def check_dependencies() -> bool:
    """依存関係のチェック"""
    errors = []

    # ffmpegのチェック
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("ffmpeg: OK")
    except FileNotFoundError:
        errors.append("ffmpegがインストールされていません。`brew install ffmpeg`でインストールしてください。")
    except subprocess.CalledProcessError as e:
        errors.append(f"ffmpegの実行に失敗しました: {e}")

    # faster-whisperのチェック
    try:
        import faster_whisper
        logger.info("faster-whisper: OK")
    except ImportError:
        errors.append("faster-whisperがインストールされていません。`pip install faster-whisper`でインストールしてください。")

    if errors:
        for error in errors:
            logger.error(error)
        return False
    return True


def find_latest_voice_memo(directory: Path = VOICE_MEMOS_DIR) -> Optional[Path]:
    """最新のボイスメモファイルを検索"""
    if not directory.exists():
        logger.error(f"ボイスメモディレクトリが見つかりません: {directory}")
        return None

    m4a_files = list(directory.glob("*.m4a"))
    if not m4a_files:
        logger.error(f"ディレクトリ内に.m4aファイルが見つかりません: {directory}")
        return None

    # 更新日時でソートして最新を取得
    latest_file = max(m4a_files, key=lambda f: f.stat().st_mtime)
    logger.info(f"最新のボイスメモを検出: {latest_file.name}")
    return latest_file


def convert_to_wav(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    ffmpegを使用してm4aをwavに変換
    16kHz, 16bit, mono
    """
    if output_path is None:
        output_path = input_path.with_suffix(".wav")

    logger.info(f"音声変換開始: {input_path.name} -> {output_path.name}")

    cmd = [
        "ffmpeg",
        "-y",  # 上書き確認なし
        "-i", str(input_path),
        "-ar", "16000",  # 16kHz
        "-ac", "1",  # mono
        "-sample_fmt", "s16",  # 16bit
        "-f", "wav",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("音声変換完了")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"音声変換に失敗しました: {e.stderr}")
        raise


def transcribe_audio(wav_path: Path, model_size: str = "large-v3") -> list[dict]:
    """
    faster-whisperを使用して音声を文字起こし

    Returns:
        list[dict]: セグメントのリスト。各セグメントは以下のキーを持つ:
            - start: 開始時間（秒）
            - end: 終了時間（秒）
            - text: テキスト
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.error("faster-whisperがインポートできません。インストールを確認してください。")
        raise

    logger.info(f"文字起こし開始 (モデル: {model_size})")
    logger.info("モデルをロード中...")

    # Apple Silicon向け設定
    # compute_type="int8"はCPUでの推論に最適
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
    )

    logger.info("文字起こし処理中...")
    segments, info = model.transcribe(
        str(wav_path),
        language="ja",
        beam_size=5,
        vad_filter=True,  # 無音区間のフィルタリング
    )

    logger.info(f"検出言語: {info.language} (確率: {info.language_probability:.2f})")

    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        })
        # 進捗表示
        logger.info(f"[{format_timestamp(segment.start)} -> {format_timestamp(segment.end)}] {segment.text.strip()}")

    logger.info(f"文字起こし完了: {len(results)}セグメント")
    return results


def format_timestamp(seconds: float) -> str:
    """秒数をHH:MM:SS形式に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_transcript(segments: list[dict], include_timestamps: bool = True) -> str:
    """文字起こし結果をテキスト形式にフォーマット"""
    lines = []
    for seg in segments:
        if include_timestamps:
            timestamp = f"[{format_timestamp(seg['start'])} -> {format_timestamp(seg['end'])}]"
            lines.append(f"{timestamp} {seg['text']}")
        else:
            lines.append(seg['text'])
    return "\n".join(lines)


def summarize_with_ollama(
    transcript: str,
    model: str = "llama3:8b",
    base_url: str = "http://localhost:11434"
) -> str:
    """Ollamaを使用して要約を生成"""
    import json
    import urllib.request
    import urllib.error

    logger.info(f"Ollamaで要約生成中 (モデル: {model})...")

    prompt = f"""以下は会議の文字起こしです。この内容を以下の形式で日本語で要約してください：

## 会議概要
（会議の主なトピックを1-2文で）

## 主な議題
- （箇条書きで主要な議題を列挙）

## 決定事項
- （決定された事項を箇条書き）

## アクションアイテム
- （誰が何をするかを箇条書き）

## その他のメモ
- （その他重要な情報）

---
文字起こし:
{transcript}
"""

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    try:
        req = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
            logger.info("Ollama要約生成完了")
            return result.get("response", "")
    except urllib.error.URLError as e:
        logger.error(f"Ollamaへの接続に失敗しました: {e}")
        logger.error("Ollamaが起動していることを確認してください。")
        raise
    except Exception as e:
        logger.error(f"Ollama要約生成中にエラーが発生しました: {e}")
        raise


def summarize_with_anthropic(transcript: str, api_key: Optional[str] = None) -> str:
    """Anthropic APIを使用して要約を生成"""
    import json
    import urllib.request
    import urllib.error

    if api_key is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEYが設定されていません。環境変数または引数で指定してください。")

    logger.info("Anthropic API (Claude 3.5 Sonnet)で要約生成中...")

    prompt = f"""以下は会議の文字起こしです。この内容を以下の形式で日本語で要約してください：

## 会議概要
（会議の主なトピックを1-2文で）

## 主な議題
- （箇条書きで主要な議題を列挙）

## 決定事項
- （決定された事項を箇条書き）

## アクションアイテム
- （誰が何をするかを箇条書き）

## その他のメモ
- （その他重要な情報）

---
文字起こし:
{transcript}
"""

    data = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            logger.info("Anthropic API要約生成完了")
            content = result.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "")
            return ""
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"Anthropic APIエラー: {e.code} - {error_body}")
        raise
    except Exception as e:
        logger.error(f"Anthropic API要約生成中にエラーが発生しました: {e}")
        raise


def save_outputs(
    transcript: str,
    summary: str,
    output_dir: Path,
    base_name: str,
) -> tuple[Path, Path]:
    """文字起こしと要約をファイルに保存"""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    transcript_path = output_dir / f"{base_name}_{timestamp}_transcript.txt"
    summary_path = output_dir / f"{base_name}_{timestamp}_summary.md"

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    logger.info(f"文字起こしを保存: {transcript_path}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# 会議要約\n\n")
        f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(summary)
    logger.info(f"要約を保存: {summary_path}")

    return transcript_path, summary_path


def main():
    parser = argparse.ArgumentParser(
        description="voice2minutes - ボイスメモ文字起こし＆会議要約ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 最新のボイスメモを処理（Ollamaで要約）
  python voice2minutes.py --summarizer ollama

  # 特定のファイルを処理（Anthropic APIで要約）
  python voice2minutes.py -i /path/to/audio.m4a --summarizer anthropic

  # 要約をスキップして文字起こしのみ
  python voice2minutes.py --no-summary
        """,
    )

    parser.add_argument(
        "-i", "--input",
        type=Path,
        help="入力音声ファイルのパス（省略時は最新のボイスメモを使用）",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="出力ディレクトリ（デフォルト: カレントディレクトリ）",
    )
    parser.add_argument(
        "--summarizer",
        choices=["ollama", "anthropic", "none"],
        default="ollama",
        help="要約に使用するLLM（デフォルト: ollama）",
    )
    parser.add_argument(
        "--ollama-model",
        default="llama3:8b",
        help="Ollamaで使用するモデル（デフォルト: llama3:8b）",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="OllamaのベースURL（デフォルト: http://localhost:11434）",
    )
    parser.add_argument(
        "--anthropic-key",
        help="Anthropic APIキー（省略時は環境変数ANTHROPIC_API_KEYを使用）",
    )
    parser.add_argument(
        "--whisper-model",
        default="large-v3",
        help="Whisperモデルサイズ（デフォルト: large-v3）",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="要約をスキップして文字起こしのみ実行",
    )
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="変換したWAVファイルを保持する",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細なログ出力",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 依存関係チェック
    logger.info("=== voice2minutes 開始 ===")
    if not check_dependencies():
        sys.exit(1)

    # 入力ファイルの決定
    if args.input:
        input_path = args.input
        if not input_path.exists():
            logger.error(f"入力ファイルが見つかりません: {input_path}")
            sys.exit(1)
    else:
        input_path = find_latest_voice_memo()
        if input_path is None:
            sys.exit(1)

    logger.info(f"入力ファイル: {input_path}")

    # 一時ディレクトリまたは出力ディレクトリにWAVを作成
    if args.keep_wav:
        wav_path = args.output_dir / input_path.with_suffix(".wav").name
    else:
        temp_dir = tempfile.mkdtemp()
        wav_path = Path(temp_dir) / "audio.wav"

    try:
        # 音声変換
        wav_path = convert_to_wav(input_path, wav_path)

        # 文字起こし
        segments = transcribe_audio(wav_path, model_size=args.whisper_model)
        transcript = format_transcript(segments, include_timestamps=True)

        # 要約
        summary = ""
        if not args.no_summary and args.summarizer != "none":
            transcript_for_summary = format_transcript(segments, include_timestamps=False)
            if args.summarizer == "ollama":
                summary = summarize_with_ollama(
                    transcript_for_summary,
                    model=args.ollama_model,
                    base_url=args.ollama_url,
                )
            elif args.summarizer == "anthropic":
                summary = summarize_with_anthropic(
                    transcript_for_summary,
                    api_key=args.anthropic_key,
                )

        # 出力保存
        base_name = input_path.stem
        transcript_path, summary_path = save_outputs(
            transcript,
            summary if summary else "（要約はスキップされました）",
            args.output_dir,
            base_name,
        )

        logger.info("=== 処理完了 ===")
        logger.info(f"文字起こし: {transcript_path}")
        logger.info(f"要約: {summary_path}")

    finally:
        # 一時ファイルのクリーンアップ
        if not args.keep_wav and wav_path.exists():
            wav_path.unlink()
            if wav_path.parent.exists() and wav_path.parent != args.output_dir:
                wav_path.parent.rmdir()


if __name__ == "__main__":
    main()
