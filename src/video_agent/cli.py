from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import Settings
from .local_asr import resolve_model_path, whisper_executable
from .media import probe_video
from .video_import import import_video_url
from .workflow import (
    analyze_prepared,
    analyze_video,
    extract_detail,
    prepare_video,
    transcribe_video,
)


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _settings() -> Settings:
    return Settings.from_env(Path.cwd() / ".env")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-agent",
        description="面向 AI Agent 的场景感知视频抽帧与分析工作流",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="检查 FFmpeg、配置和 API Key 状态")

    probe = sub.add_parser("probe", help="读取视频元信息，不调用模型")
    probe.add_argument("video")

    prepare = sub.add_parser("prepare", help="场景检测并抽帧，不调用模型")
    prepare.add_argument("video")
    prepare.add_argument("--interval", type=float)
    prepare.add_argument("--max-frames", type=int)
    prepare.add_argument("--scene-threshold", type=float)
    prepare.add_argument("--output-dir")

    analyze = sub.add_parser("analyze", help="抽帧并调用视觉模型完成分析")
    analyze.add_argument("video")
    analyze.add_argument("--question", "-q", default="这个视频讲了什么？请按时间线分析。")
    analyze.add_argument("--interval", type=float)
    analyze.add_argument("--max-frames", type=int)
    analyze.add_argument("--scene-threshold", type=float)
    analyze.add_argument("--output-dir")
    analyze.add_argument(
        "--mode",
        choices=["balanced", "narration"],
        default="balanced",
        help="balanced 先抽帧；narration 先听声音，再由 AI 定向抽帧",
    )

    analyze_manifest = sub.add_parser(
        "analyze-prepared",
        help="分析已有抽帧清单，避免重复抽帧和重复知识库记录",
    )
    analyze_manifest.add_argument("manifest")
    analyze_manifest.add_argument(
        "--question", "-q", default="这个视频讲了什么？请按时间线分析。"
    )

    transcribe = sub.add_parser(
        "transcribe",
        help="只听取并转写视频声音，不调用视觉模型",
    )
    transcribe.add_argument("video")
    transcribe.add_argument("--output-dir")

    import_url = sub.add_parser(
        "import-url",
        help="从抖音等受支持的视频链接下载到本地知识库",
    )
    import_url.add_argument("url")
    import_url.add_argument(
        "--browser-cookies",
        default="none",
        choices=["none", "safari", "chrome", "chromium", "edge", "firefox"],
    )
    import_url.add_argument("--output-dir")

    detail = sub.add_parser("detail", help="在指定时间附近密集抽帧，不调用模型")
    detail.add_argument("video")
    detail.add_argument("--at", required=True, help="秒数、MM:SS 或 HH:MM:SS")
    detail.add_argument("--radius", type=float, default=2.0)
    detail.add_argument("--fps", type=float, default=2.0)
    detail.add_argument("--output-dir")
    return parser


def doctor(settings: Settings) -> dict:
    local_model = resolve_model_path(settings.local_whisper_model_path)
    local_executable = whisper_executable()
    checks = {
        "ffmpeg": shutil.which("ffmpeg") or "",
        "ffprobe": shutil.which("ffprobe") or "",
        "provider": settings.provider,
        "base_url": settings.base_url,
        "vision_model": settings.vision_model,
        "api_key_configured": bool(settings.api_key),
        "transcription_enabled": settings.transcription_enabled,
        "transcription_provider": settings.transcription_provider,
        "local_whisper_executable": local_executable,
        "local_whisper_model": str(local_model),
        "local_whisper_model_exists": local_model.is_file(),
        "output_dir": str(settings.output_dir),
    }
    checks["ready_for_local_processing"] = bool(checks["ffmpeg"] and checks["ffprobe"])
    checks["ready_for_ai_analysis"] = bool(
        checks["ready_for_local_processing"] and checks["api_key_configured"]
    )
    checks["ready_for_local_transcription"] = bool(
        local_executable and checks["local_whisper_model_exists"]
    )
    return checks


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = _settings()
    try:
        if args.command == "doctor":
            _print(doctor(settings))
        elif args.command == "probe":
            _print(probe_video(args.video).to_dict())
        elif args.command == "prepare":
            _print(prepare_video(
                args.video,
                settings,
                interval=args.interval,
                max_frames=args.max_frames,
                scene_threshold=args.scene_threshold,
                output_dir=args.output_dir,
            ))
        elif args.command == "analyze":
            _print(analyze_video(
                args.video,
                settings,
                question=args.question,
                mode=args.mode,
                interval=args.interval,
                max_frames=args.max_frames,
                scene_threshold=args.scene_threshold,
                output_dir=args.output_dir,
            ))
        elif args.command == "analyze-prepared":
            manifest_path = Path(args.manifest).expanduser().resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            _print(analyze_prepared(manifest, settings, args.question))
        elif args.command == "transcribe":
            _print(transcribe_video(
                args.video,
                settings,
                output_dir=args.output_dir,
            ))
        elif args.command == "import-url":
            destination = Path(args.output_dir) if args.output_dir else settings.output_dir / "imports"
            _print(import_video_url(
                args.url,
                destination,
                browser_cookies=args.browser_cookies,
            ))
        elif args.command == "detail":
            _print(extract_detail(
                args.video,
                args.at,
                settings,
                radius=args.radius,
                fps=args.fps,
                output_dir=args.output_dir,
            ))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
