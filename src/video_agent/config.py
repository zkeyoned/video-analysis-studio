from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load a small, dependency-free subset of .env syntax."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    base_url: str
    vision_model: str
    transcription_provider: str
    transcription_model: str
    transcription_base_url: str
    transcription_api_key: str
    local_whisper_model_path: Path
    transcription_language: str
    transcription_prompt: str
    output_dir: Path
    frame_interval: float
    max_frames: int
    scene_threshold: float
    batch_size: int
    max_detail_requests: int
    frame_width: int
    request_timeout: float

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "Settings":
        load_dotenv(env_path)
        provider = os.environ.get("VIDEO_AGENT_PROVIDER", "openai_compatible").strip()
        transcription_model = os.environ.get(
            "VIDEO_AGENT_TRANSCRIPTION_MODEL", ""
        ).strip()
        transcription_provider = os.environ.get(
            "VIDEO_AGENT_TRANSCRIPTION_PROVIDER", ""
        ).strip()
        if not transcription_provider:
            # Keep old .env files working: setting a cloud transcription model
            # used to be the only switch that enabled audio transcription.
            transcription_provider = (
                "openai_compatible" if transcription_model else "none"
            )
        default_base = (
            "https://generativelanguage.googleapis.com/v1beta"
            if provider == "gemini"
            else "https://api.openai.com/v1"
        )
        return cls(
            provider=provider,
            api_key=os.environ.get("VIDEO_AGENT_API_KEY", "").strip(),
            base_url=os.environ.get("VIDEO_AGENT_BASE_URL", default_base).rstrip("/"),
            vision_model=os.environ.get("VIDEO_AGENT_VISION_MODEL", "gpt-4.1-mini").strip(),
            transcription_provider=transcription_provider,
            transcription_model=transcription_model,
            transcription_base_url=os.environ.get(
                "VIDEO_AGENT_TRANSCRIPTION_BASE_URL", ""
            ).rstrip("/"),
            transcription_api_key=os.environ.get(
                "VIDEO_AGENT_TRANSCRIPTION_API_KEY", ""
            ).strip(),
            local_whisper_model_path=Path(
                os.environ.get(
                    "VIDEO_AGENT_LOCAL_WHISPER_MODEL", "models/ggml-large-v3-turbo.bin"
                )
            ).expanduser(),
            transcription_language=(
                os.environ.get("VIDEO_AGENT_TRANSCRIPTION_LANGUAGE", "zh").strip()
                or "auto"
            ),
            transcription_prompt=os.environ.get(
                "VIDEO_AGENT_TRANSCRIPTION_PROMPT",
                "教程、收藏夹、抖音、私信、下载视频、爬取视频、飞书表格、Codex、GitHub、AI、API、关键词。",
            ).strip(),
            output_dir=Path(os.environ.get("VIDEO_AGENT_OUTPUT_DIR", "output")),
            frame_interval=max(0.25, _float("VIDEO_AGENT_FRAME_INTERVAL", 6.0)),
            max_frames=max(1, _int("VIDEO_AGENT_MAX_FRAMES", 60)),
            scene_threshold=min(1.0, max(0.01, _float("VIDEO_AGENT_SCENE_THRESHOLD", 0.30))),
            batch_size=max(1, _int("VIDEO_AGENT_BATCH_SIZE", 12)),
            max_detail_requests=max(0, _int("VIDEO_AGENT_MAX_DETAIL_REQUESTS", 3)),
            frame_width=max(320, _int("VIDEO_AGENT_FRAME_WIDTH", 1280)),
            request_timeout=max(10.0, _float("VIDEO_AGENT_REQUEST_TIMEOUT", 180.0)),
        )

    def require_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "尚未配置视觉模型 API Key。请复制 .env.example 为 .env 后填写 "
                "VIDEO_AGENT_API_KEY。"
            )

    @property
    def transcription_enabled(self) -> bool:
        return self.transcription_provider not in {"", "none", "disabled"}
