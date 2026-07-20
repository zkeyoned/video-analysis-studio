from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from opencc import OpenCC


_T2S_CONVERTER = OpenCC("t2s")
_LARGE_V3_TURBO_SIZE = 1_624_555_275


def whisper_executable() -> str:
    """Return the Homebrew/PATH whisper.cpp CLI when it is installed."""
    found = shutil.which("whisper-cli")
    if found:
        return found
    for candidate in (
        "/opt/homebrew/bin/whisper-cli",
        "/usr/local/bin/whisper-cli",
    ):
        if Path(candidate).is_file():
            return candidate
    return ""


def resolve_model_path(model_path: str | Path) -> Path:
    path = Path(model_path).expanduser()
    return path.resolve()


def _srt_seconds(value: str) -> float:
    match = re.fullmatch(r"(\d+):(\d+):(\d+)[,.](\d+)", value.strip())
    if not match:
        raise ValueError(f"无效的 SRT 时间：{value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / (10 ** len(str(millis)))


def to_simplified_chinese(text: str) -> str:
    converted = _T2S_CONVERTER.convert(text)
    return converted.translate(str.maketrans({",": "，", "?": "？", "!": "！"}))


def parse_srt_transcript(text: str, *, simplified_chinese: bool = False) -> str:
    """Convert SRT into compact timestamped lines used by the vision workflow."""
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    segments: list[str] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        start_raw, end_raw = (part.strip() for part in lines[time_index].split("-->", 1))
        start = _srt_seconds(start_raw)
        end = _srt_seconds(end_raw)
        content = " ".join(lines[time_index + 1:]).strip()
        if simplified_chinese:
            content = to_simplified_chinese(content)
        if content:
            segments.append(f"[{start:.2f}-{end:.2f}] {content}")
    return "\n".join(segments)


def parse_whisper_json(text: str, *, simplified_chinese: bool = False) -> str:
    """Build short timestamped clauses from whisper.cpp token timestamps."""
    payload = json.loads(text)
    segments: list[str] = []
    content_parts: list[str] = []
    start: float | None = None
    end = 0.0

    def flush() -> None:
        nonlocal content_parts, start, end
        content = "".join(content_parts).strip()
        if content and start is not None:
            if simplified_chinese:
                content = to_simplified_chinese(content)
            segments.append(f"[{start:.2f}-{end:.2f}] {content}")
        content_parts = []
        start = None
        end = 0.0

    for transcription in payload.get("transcription", []):
        for token in transcription.get("tokens", []):
            token_text = str(token.get("text", ""))
            if not token_text or re.fullmatch(r"\[_[^]]+\]", token_text):
                continue
            offsets = token.get("offsets", {})
            token_start = float(offsets.get("from", 0)) / 1000
            token_end = float(offsets.get("to", offsets.get("from", 0))) / 1000
            if start is None:
                start = token_start
            end = max(end, token_end)
            content_parts.append(token_text)
            duration = end - start
            ends_clause = bool(re.search(r"[,，。.!！?？;；:：]\s*$", token_text))
            if (ends_clause and duration >= 1.0) or duration >= 8.0:
                flush()
        flush()
    return "\n".join(segments)


def transcribe_with_whisper_cpp(
    audio_path: Path,
    model_path: str | Path,
    language: str,
    output_prefix: Path,
    prompt: str = "",
    timeout: float = 1800,
) -> str:
    executable = whisper_executable()
    if not executable:
        raise RuntimeError(
            "未安装本地听觉引擎 whisper.cpp。可运行 script/setup_local_whisper.sh 安装。"
        )
    model = resolve_model_path(model_path)
    if not model.is_file():
        raise RuntimeError(
            f"找不到本地 Whisper 模型：{model}。可运行 script/setup_local_whisper.sh 下载。"
        )
    if model.name == "ggml-large-v3-turbo.bin" and model.stat().st_size != _LARGE_V3_TURBO_SIZE:
        raise RuntimeError("large-v3-turbo 模型文件不完整，请重新运行听觉模型安装器")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    args = [
        executable,
        "-m", str(model),
        "-f", str(audio_path.resolve()),
        "-l", language or "auto",
        "-osrt",
        "-ojf",
        "-of", str(output_prefix.resolve()),
        "-np",
    ]
    if prompt.strip():
        args.extend(["--prompt", prompt.strip(), "--carry-initial-prompt"])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("本地语音转写超时") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "本地语音转写失败")
    json_path = output_prefix.with_suffix(".json")
    simplify = (language or "auto").lower() in {"zh", "auto"}
    if json_path.is_file():
        transcript = parse_whisper_json(
            json_path.read_text(encoding="utf-8"),
            simplified_chinese=simplify,
        )
        if transcript:
            return transcript
    srt_path = output_prefix.with_suffix(".srt")
    if not srt_path.is_file():
        raise RuntimeError("whisper.cpp 未生成转写结果")
    return parse_srt_transcript(
        srt_path.read_text(encoding="utf-8"),
        simplified_chinese=simplify,
    )
