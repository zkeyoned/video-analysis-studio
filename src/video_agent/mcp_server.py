from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .media import probe_video as read_video_info
from .workflow import analyze_video as run_analysis
from .workflow import extract_detail, prepare_video as run_prepare


mcp = FastMCP("video-analysis-agent")


def _settings() -> Settings:
    return Settings.from_env(Path.cwd() / ".env")


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


@mcp.tool()
def probe_video(video_path: str) -> str:
    """读取本地视频的时长、尺寸、帧率、编码和音轨信息，不调用 AI。"""
    return _json(probe_video_file(video_path))


def probe_video_file(video_path: str) -> dict:
    return read_video_info(video_path).to_dict()


@mcp.tool()
def prepare_video(
    video_path: str,
    interval_seconds: float = 6.0,
    max_frames: int = 60,
    scene_threshold: float = 0.30,
) -> str:
    """检测视频镜头并抽取带时间戳的代表帧；不调用 AI，适合先了解素材规模。"""
    return _json(run_prepare(
        video_path,
        _settings(),
        interval=interval_seconds,
        max_frames=max_frames,
        scene_threshold=scene_threshold,
    ))


@mcp.tool()
def analyze_video(
    video_path: str,
    question: str = "这个视频讲了什么？请按时间线分析。",
    interval_seconds: float = 6.0,
    max_frames: int = 60,
) -> str:
    """智能抽帧后调用已配置的视觉模型，返回摘要、时间线和证据。需要 API Key。"""
    return _json(run_analysis(
        video_path,
        _settings(),
        question=question,
        interval=interval_seconds,
        max_frames=max_frames,
    ))


@mcp.tool()
def extract_frames_at(
    video_path: str,
    timecode: str,
    radius_seconds: float = 2.0,
    frames_per_second: float = 2.0,
) -> str:
    """在某个时间点前后密集抽帧，用于复查快速动作或模型不确定的位置。"""
    return _json(extract_detail(
        video_path,
        timecode,
        _settings(),
        radius=radius_seconds,
        fps=frames_per_second,
    ))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
