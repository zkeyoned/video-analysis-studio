from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    has_audio: bool
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def require_binaries() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(f"缺少依赖：{', '.join(missing)}。macOS 可运行 brew install ffmpeg")


def _run(args: list[str], timeout: float = 300) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"未找到命令：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"视频处理超时：{args[0]}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"命令执行失败：{args[0]}")
    return result


def parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = float(right)
        return float(left) / denominator if denominator else 0.0
    return float(value)


def probe_video(video_path: str | Path) -> VideoInfo:
    require_binaries()
    path = Path(video_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"视频不存在：{path}")
    result = _run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video:
        raise ValueError(f"文件中没有视频流：{path}")
    duration = float(video.get("duration") or payload.get("format", {}).get("duration") or 0)
    return VideoInfo(
        path=str(path),
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        codec=str(video.get("codec_name") or "unknown"),
        has_audio=any(item.get("codec_type") == "audio" for item in streams),
        size_bytes=path.stat().st_size,
    )


def parse_timestamp(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return max(0.0, float(value))
    raw = value.strip()
    if not raw:
        raise ValueError("时间戳不能为空")
    parts = raw.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            seconds = float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"时间戳格式无效：{value}") from exc
    return max(0.0, seconds)


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def uniform_timestamps(duration: float, interval: float) -> list[float]:
    if duration <= 0:
        return [0.0]
    values = [0.0]
    current = interval
    while current < duration:
        values.append(current)
        current += interval
    # Container duration can extend beyond the final decodable frame. Keep a
    # small safety margin instead of seeking to the exact media endpoint.
    ending = max(0.0, duration - min(0.25, interval / 2))
    if ending - values[-1] > min(1.0, interval / 3):
        values.append(ending)
    return values


def detect_scene_timestamps(video_path: str | Path, threshold: float = 0.30) -> list[float]:
    """Use FFmpeg's scene score and parse timestamps from showinfo output."""
    path = Path(video_path).expanduser().resolve()
    expression = f"select=gt(scene\\,{threshold}),showinfo"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vf", expression, "-an", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "场景检测失败")
    found = [float(value) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
    return sorted(set(round(value, 3) for value in found))


def choose_timestamps(
    duration: float,
    interval: float,
    scene_times: Iterable[float],
    max_frames: int,
) -> list[float]:
    """Blend whole-video coverage with representative points inside each scene.

    FFmpeg reports the first frame after a cut. Sending those cut frames directly
    often captures fades, black frames, or incomplete transitions. Sampling inside
    each scene is much more useful for films and commentary videos.
    """
    uniform = uniform_timestamps(duration, interval)
    scenes = [value for value in scene_times if 0 <= value <= duration]
    representatives = scene_representative_timestamps(duration, scenes)
    candidates = sorted(
        set(round(value, 3) for value in [*uniform, *representatives])
    )
    if len(candidates) <= max_frames:
        return candidates

    # Always retain evenly distributed coverage; fill remaining slots with scene
    # representatives furthest from timestamps that are already selected.
    coverage_count = max(2, min(len(uniform), max_frames // 2))
    if coverage_count == 1:
        selected = [uniform[0]]
    else:
        indices = [round(i * (len(uniform) - 1) / (coverage_count - 1)) for i in range(coverage_count)]
        selected = [uniform[index] for index in sorted(set(indices))]
    remaining = [value for value in representatives if value not in selected]
    while remaining and len(selected) < max_frames:
        best = max(remaining, key=lambda value: min(abs(value - old) for old in selected))
        selected.append(best)
        remaining.remove(best)
    if len(selected) < max_frames:
        for value in candidates:
            if value not in selected:
                selected.append(value)
                if len(selected) == max_frames:
                    break
    return sorted(round(value, 3) for value in selected[:max_frames])


def scene_representative_timestamps(
    duration: float,
    scene_times: Iterable[float],
    samples_per_scene: int = 2,
) -> list[float]:
    """Choose stable frames inside every detected scene instead of on its cut."""
    if duration <= 0:
        return [0.0]
    safe_end = max(0.0, duration - 0.1)
    cuts = sorted(
        set(
            round(value, 3)
            for value in scene_times
            if 0.15 < value < duration - 0.15
        )
    )
    boundaries = [0.0, *cuts, duration]
    representatives: list[float] = []
    for start, end in zip(boundaries, boundaries[1:]):
        length = end - start
        if length <= 0:
            continue
        if samples_per_scene <= 1 or length < 1.5:
            points = [start + length * 0.5]
        else:
            # 30% and 70% avoid transition edges while still covering actions
            # that happen near the beginning or end of a longer shot.
            points = [
                start + length * (index + 1) / (samples_per_scene + 1)
                for index in range(samples_per_scene)
            ]
        representatives.extend(min(max(0.0, point), safe_end) for point in points)
    return sorted(set(round(value, 3) for value in representatives))


def extract_frame(
    video_path: str | Path,
    timestamp: float,
    output_path: str | Path,
    width: int = 1280,
) -> Path:
    path, _ = extract_frame_resilient(
        video_path, timestamp, output_path, width
    )
    return path


def extract_frame_resilient(
    video_path: str | Path,
    timestamp: float,
    output_path: str | Path,
    width: int = 1280,
    backoffs: tuple[float, ...] = (0.0, 0.1, 0.25, 0.5, 1.0),
) -> tuple[Path, float]:
    """Extract a frame, retrying slightly earlier for damaged seek points.

    Some downloaded MP4 files advertise a duration that extends beyond their
    last decodable video packet. A small backwards retry handles keyframe/seek
    edge cases without pretending that a much earlier frame belongs to the
    requested timestamp.
    """
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: RuntimeError | None = None
    attempted: set[float] = set()
    for backoff in backoffs:
        actual = round(max(0.0, timestamp - max(0.0, backoff)), 3)
        if actual in attempted:
            continue
        attempted.add(actual)
        destination.unlink(missing_ok=True)
        try:
            _run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{actual:.3f}",
                "-i", str(Path(video_path).expanduser().resolve()), "-frames:v", "1",
                "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", "-y", str(destination),
            ])
            if destination.is_file() and destination.stat().st_size > 0:
                return destination, actual
        except RuntimeError as exc:
            last_error = exc
    destination.unlink(missing_ok=True)
    detail = f"：{last_error}" if last_error else ""
    raise RuntimeError(f"抽帧失败 {format_timestamp(timestamp)}{detail}")


def extract_frames(
    video_path: str | Path,
    timestamps: Iterable[float],
    output_dir: str | Path,
    width: int = 1280,
) -> list[dict]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    frames = []
    for requested_index, timestamp in enumerate(timestamps, start=1):
        candidate = directory / f".candidate_{requested_index:04d}.jpg"
        try:
            path, actual = extract_frame_resilient(
                video_path, timestamp, candidate, width
            )
        except RuntimeError:
            # A single corrupt tail frame should not discard all valid frames.
            # If every candidate fails, raise a clear error below.
            continue
        index = len(frames) + 1
        name = f"frame_{index:04d}_{int(actual * 1000):010d}ms.jpg"
        final_path = directory / name
        path.replace(final_path)
        item = {
            "index": index,
            "timestamp": round(actual, 3),
            "timecode": format_timestamp(actual),
            "path": str(final_path.resolve()),
        }
        if abs(actual - timestamp) >= 0.001:
            item["requested_timestamp"] = round(timestamp, 3)
        frames.append(item)
    if not frames:
        raise RuntimeError("视频中没有可解码的画面，文件可能已损坏或下载不完整")
    return frames


def detail_timestamps(
    center: str | float,
    duration: float,
    radius: float = 2.0,
    fps: float = 2.0,
    max_frames: int = 24,
) -> list[float]:
    point = min(parse_timestamp(center), max(0.0, duration))
    step = 1.0 / max(0.1, fps)
    start = max(0.0, point - max(0.0, radius))
    safe_end = max(0.0, duration - 0.1)
    end = min(safe_end, point + max(0.0, radius))
    count = min(max_frames, int(math.floor((end - start) / step)) + 1)
    return [round(start + i * step, 3) for i in range(count)]


def extract_audio(video_path: str | Path, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
    ]
    if destination.suffix.lower() == ".wav":
        args.extend(["-c:a", "pcm_s16le"])
    else:
        args.extend(["-b:a", "48k"])
    args.extend(["-y", str(destination)])
    _run(args)
    return destination
