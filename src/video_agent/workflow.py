from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .media import (
    choose_timestamps,
    detail_timestamps,
    detect_scene_timestamps,
    extract_audio,
    extract_frames,
    parse_timestamp,
    probe_video,
    scene_representative_timestamps,
    uniform_timestamps,
)
from .providers import VisionProvider, extract_json, transcribe_audio


FRAME_PROMPT = """你正在分析同一段视频中按时间排序的一批画面。
用户问题：{question}
这批画面时间范围内的音频转写：
{transcript_excerpt}

请分别使用画面证据和声音证据，不要把台词描述误写成画面中已确认发生的事实。完整关注人物、地点、物品、动作、关系、事件、屏幕文字、前后因果和剧情转折，不要只选少数概括词。
返回严格 JSON，不要使用 Markdown：
{{
  "segment_summary": "这一批画面的概括",
  "events": [
    {{"timecode": "HH:MM:SS", "description": "发生的事情", "evidence": "visual|audio|both", "confidence": 0.0}}
  ],
  "entities": ["人物、物体、地点或界面元素"],
  "audio_keywords": [{{"timecode": "HH:MM:SS", "term": "声音中明确出现的关键词"}}],
  "visible_text": [{{"timecode": "HH:MM:SS", "text": "画面文字"}}],
  "uncertainties": ["无法从抽帧确认的内容"],
  "detail_requests": [
    {{"timecode": "HH:MM:SS", "reason": "为什么需要在附近密集抽帧"}}
  ]
}}
如果没有需要二次查看的位置，detail_requests 返回空数组。"""


FINAL_PROMPT = """请把以下分批视频分析与音频转写合并成最终报告。
用户问题：{question}
视频元信息：{video_info}
声音优先规划：{audio_guidance}
分批画面分析：{analyses}
音频转写：{transcript}

规则：
1. 保持时间顺序；画面证据与声音证据互相校验。
2. 不确定内容明确标记，不要编造抽帧之间发生的动作。
3. 回答用户问题，同时给出可复用的结构化结果。
4. 完整提取人物、地点、物品、动作、关系、事件、主题和剧情转折等关键词；不要只返回少数高层概括词。
5. keywords 中必须保留转写里明确说出的关键词，并给出最接近的时间；不能确认时才标 uncertain。
6. 返回严格 JSON，不要使用 Markdown。

JSON 结构：
{{
  "summary": "完整视频摘要",
  "answer": "针对用户问题的直接回答",
  "timeline": [{{"timecode": "HH:MM:SS", "event": "事件", "evidence": "visual|audio|both"}}],
  "keywords": [{{"timecode": "HH:MM:SS", "term": "关键词", "source": "audio|visual|both", "context": "它在视频中的含义"}}],
  "people_objects_places": ["实体"],
  "visible_text": [{{"timecode": "HH:MM:SS", "text": "文字"}}],
  "uncertainties": ["不确定性或可能遗漏之处"],
  "recommended_followups": ["后续问题或应密集检查的片段"]
}}"""


AUDIO_GUIDANCE_PROMPT = """你正在为一段讲解类视频规划视觉取证位置。这是第 {part_index}/{part_count} 段带时间戳的声音转写。
用户希望分析：{question}
声音转写：
{transcript}

先只根据声音理解内容，再判断哪些时间范围必须查看画面才能确认。重点选择：软件或网站界面、按钮操作、参数设置、实物展示、图表、屏幕文字、前后效果和声音无法独立证明的动作。纯口头观点不必反复看说话者画面。

返回严格 JSON，不要使用 Markdown：
{{
  "overview": "这一段讲解的内容",
  "spoken_keywords": [{{"timecode": "HH:MM:SS", "term": "声音中明确说出的关键词"}}],
  "visual_requests": [
    {{
      "start": 12.3,
      "end": 18.0,
      "reason": "需要从画面确认什么",
      "sampling": "single|normal|dense"
    }}
  ]
}}

规则：
1. start 和 end 必须使用转写方括号中的秒数，不能编造超出本段的时间。
2. single 用于静态展示，normal 用于一般界面或物品，dense 用于连续点击、快速操作或明显变化。
3. 尽量覆盖用户问题涉及的每个具体工具、步骤、对象和结果；同一连续操作不要拆成大量重复请求。
4. 如果这一段不需要画面确认，visual_requests 返回空数组。
"""


JSON_REPAIR_PROMPT = """下面是一段模型本应返回的 JSON，但它可能有缺失括号、未转义字符、Markdown 包裹或末尾截断。
任务类型：{context}
请在不编造新事实的前提下修复为一个完整、可解析的 JSON 对象。只返回 JSON，不要解释。

待修复内容：
{raw}
"""


_TRANSCRIPT_SEGMENT = re.compile(
    r"^\[(?P<start>\d+(?:\.\d+)?)-(?P<end>\d+(?:\.\d+)?)\]\s*(?P<text>.*)$"
)


def transcript_for_range(
    transcript: str,
    start: float,
    end: float,
    *,
    padding: float = 3.0,
    max_chars: int = 6000,
) -> str:
    """Return transcript segments overlapping a frame batch's time window."""
    if not transcript.strip():
        return "（未启用或没有识别出声音）"
    matched: list[str] = []
    saw_timestamps = False
    lower = max(0.0, start - padding)
    upper = end + padding
    for line in transcript.splitlines():
        segment = _TRANSCRIPT_SEGMENT.match(line.strip())
        if not segment:
            continue
        saw_timestamps = True
        segment_start = float(segment.group("start"))
        segment_end = float(segment.group("end"))
        if segment_end >= lower and segment_start <= upper:
            matched.append(line.strip())
    value = "\n".join(matched)
    if not saw_timestamps:
        value = transcript
    if not value:
        return "（这个时间范围没有识别出对白）"
    return value[:max_chars]


def extract_or_repair_json(
    raw: str,
    provider: VisionProvider,
    context: str,
) -> dict:
    """Parse model JSON, using one cheap text-only repair call if needed."""
    try:
        value = extract_json(raw)
    except ValueError as original:
        repaired = provider.complete_text(JSON_REPAIR_PROMPT.format(
            context=context,
            raw=raw[:60000],
        ))
        try:
            value = extract_json(repaired)
        except ValueError:
            raise original
    if not isinstance(value, dict):
        raise ValueError("模型返回的 JSON 不是对象")
    return value


def analyze_frames_json(
    provider: VisionProvider,
    prompt: str,
    frames: list[dict],
    context: str,
) -> dict:
    """Analyze an image batch and retry once only if JSON repair also fails."""
    last_error: ValueError | None = None
    for attempt in range(2):
        retry_note = (
            "\n上一次输出无法解析。请缩短描述，并确保返回完整合法的 JSON 对象。"
            if attempt else ""
        )
        raw = provider.analyze_frames(prompt + retry_note, frames)
        try:
            return extract_or_repair_json(raw, provider, context)
        except ValueError as exc:
            last_error = exc
    raise last_error or ValueError("模型没有返回有效 JSON")


def complete_text_json(
    provider: VisionProvider,
    prompt: str,
    context: str,
) -> dict:
    """Complete a text-only JSON task with repair and one bounded retry."""
    last_error: ValueError | None = None
    for attempt in range(2):
        retry_note = (
            "\n上一次输出无法解析。请只返回一个完整、合法的 JSON 对象。"
            if attempt else ""
        )
        raw = provider.complete_text(prompt + retry_note)
        try:
            return extract_or_repair_json(raw, provider, context)
        except ValueError as exc:
            last_error = exc
    raise last_error or ValueError("模型没有返回有效 JSON")


def chunk_transcript(transcript: str, max_chars: int = 24000) -> list[str]:
    """Split a timestamped transcript without breaking ordinary cue lines."""
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    if not lines:
        return []
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        addition = len(line) + (1 if current else 0)
        if current and size + addition > max_chars:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _request_seconds(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return parse_timestamp(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _normalize_guidance(payload: object, duration: float) -> dict:
    if not isinstance(payload, dict):
        return {"overview": "", "spoken_keywords": [], "visual_requests": []}
    requests: list[dict] = []
    raw_requests = payload.get("visual_requests", [])
    if isinstance(raw_requests, list):
        for raw in raw_requests:
            if not isinstance(raw, dict):
                continue
            start = _request_seconds(
                raw.get("start", raw.get("timecode")), 0.0
            )
            end = _request_seconds(raw.get("end"), start + 2.0)
            start = min(max(0.0, start), max(0.0, duration))
            end = min(max(start, end), max(0.0, duration))
            sampling = str(raw.get("sampling", "normal")).lower()
            if sampling not in {"single", "normal", "dense"}:
                sampling = "normal"
            requests.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "reason": str(raw.get("reason", "核对讲解对应的画面")),
                "sampling": sampling,
            })
    keywords = payload.get("spoken_keywords", [])
    return {
        "overview": str(payload.get("overview", "")),
        "spoken_keywords": keywords if isinstance(keywords, list) else [],
        "visual_requests": requests,
    }


def _fallback_guidance_requests(transcript: str, duration: float) -> list[dict]:
    cues: list[tuple[float, float, str]] = []
    for line in transcript.splitlines():
        match = _TRANSCRIPT_SEGMENT.match(line.strip())
        if not match:
            continue
        cues.append((
            float(match.group("start")),
            float(match.group("end")),
            match.group("text"),
        ))
    if not cues:
        return []
    limit = min(12, len(cues))
    indices = sorted(set(
        round(index * (len(cues) - 1) / max(1, limit - 1))
        for index in range(limit)
    ))
    return [
        {
            "start": round(min(max(0.0, cues[index][0]), duration), 3),
            "end": round(min(max(cues[index][0], cues[index][1]), duration), 3),
            "reason": f"核对这段讲解对应的画面：{cues[index][2][:80]}",
            "sampling": "normal",
        }
        for index in indices
    ]


def plan_audio_guidance(
    transcript: str,
    duration: float,
    question: str,
    provider: VisionProvider,
) -> dict:
    """Ask the text-capable model which transcript ranges need visual proof."""
    chunks = chunk_transcript(transcript)
    combined = {
        "strategy": "transcript_first_visual_planning",
        "overview_parts": [],
        "spoken_keywords": [],
        "visual_requests": [],
    }
    for index, chunk in enumerate(chunks, start=1):
        prompt = AUDIO_GUIDANCE_PROMPT.format(
            part_index=index,
            part_count=len(chunks),
            question=question,
            transcript=chunk,
        )
        try:
            planned = _normalize_guidance(
                complete_text_json(provider, prompt, "声音重点与视觉取证规划"),
                duration,
            )
        except ValueError:
            planned = _normalize_guidance({}, duration)
        if planned["overview"]:
            combined["overview_parts"].append(planned["overview"])
        combined["spoken_keywords"].extend(planned["spoken_keywords"])
        combined["visual_requests"].extend(planned["visual_requests"])
    if not combined["visual_requests"]:
        combined["visual_requests"] = _fallback_guidance_requests(
            transcript, duration
        )
        combined["used_fallback_requests"] = True
    else:
        combined["used_fallback_requests"] = False
    return combined


def _evenly_limit(values: list[float], limit: int) -> list[float]:
    if limit <= 0 or not values:
        return []
    if len(values) <= limit:
        return values
    if limit == 1:
        return [values[len(values) // 2]]
    indices = sorted(set(
        round(index * (len(values) - 1) / (limit - 1))
        for index in range(limit)
    ))
    return [values[index] for index in indices]


def _dedupe_nearby(values: list[float], gap: float = 0.2) -> list[float]:
    selected: list[float] = []
    for value in sorted(set(round(item, 3) for item in values)):
        if not selected or value - selected[-1] >= gap:
            selected.append(value)
    return selected


def choose_audio_guided_timestamps(
    duration: float,
    guidance: dict,
    scene_times: list[float],
    max_frames: int,
    coverage_interval: float = 20.0,
) -> list[float]:
    """Blend AI-requested ranges with sparse whole-video safety coverage."""
    frame_limit = max(1, max_frames)
    safe_end = max(0.0, duration - 0.1)
    scene_points = scene_representative_timestamps(
        duration, scene_times, samples_per_scene=1
    )
    targeted: list[float] = []
    for request in guidance.get("visual_requests", []):
        if not isinstance(request, dict):
            continue
        start = min(max(0.0, float(request.get("start", 0.0))), safe_end)
        end = min(max(start, float(request.get("end", start))), safe_end)
        span = max(0.0, end - start)
        sampling = request.get("sampling", "normal")
        if sampling == "single" or span < 0.4:
            points = [start + span / 2]
        elif sampling == "dense":
            count = min(12, max(3, int(span / 0.75) + 1))
            points = [
                start + span * index / max(1, count - 1)
                for index in range(count)
            ]
        else:
            points = [
                start + span * 0.2,
                start + span * 0.5,
                start + span * 0.8,
            ]
        points.extend(
            value for value in scene_points
            if start - 0.5 <= value <= end + 0.5
        )
        targeted.extend(points)
    targeted = _dedupe_nearby(
        [min(max(0.0, value), safe_end) for value in targeted]
    )

    coverage_count = min(max(1, frame_limit // 5), 12)
    coverage = uniform_timestamps(
        duration, max(10.0, coverage_interval)
    )
    coverage.extend(_evenly_limit(scene_points, coverage_count))
    coverage = _evenly_limit(_dedupe_nearby(coverage), coverage_count)

    target_limit = max(0, frame_limit - len(coverage))
    selected_targets = _evenly_limit(targeted, target_limit)
    combined = _dedupe_nearby([*coverage, *selected_targets])
    if not combined:
        return [0.0]
    return _evenly_limit(combined, frame_limit)


def _safe_stem(path: Path) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", path.stem, flags=re.UNICODE).strip("-")
    return value[:60] or "video"


def _session_dir(video_path: Path, output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = output_root / f"{_safe_stem(video_path)}-{stamp}-{uuid4().hex[:6]}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _load_source_metadata(source: Path) -> dict:
    sidecar = source.with_name(f"{source.name}.source.json")
    if not sidecar.is_file():
        return {}
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def prepare_video(
    video_path: str | Path,
    settings: Settings,
    *,
    interval: float | None = None,
    max_frames: int | None = None,
    scene_threshold: float | None = None,
    output_dir: str | Path | None = None,
) -> dict:
    source = Path(video_path).expanduser().resolve()
    info = probe_video(source)
    threshold = scene_threshold if scene_threshold is not None else settings.scene_threshold
    frame_interval = interval if interval is not None else settings.frame_interval
    frame_limit = max_frames if max_frames is not None else settings.max_frames
    scenes = detect_scene_timestamps(source, threshold)
    timestamps = choose_timestamps(info.duration, frame_interval, scenes, frame_limit)
    root = Path(output_dir) if output_dir else settings.output_dir
    root = root.expanduser().resolve()
    session = _session_dir(source, root)
    frames = extract_frames(source, timestamps, session / "frames", settings.frame_width)
    source_metadata = _load_source_metadata(source)
    manifest = {
        "session_dir": str(session),
        "video": info.to_dict(),
        "source": source_metadata,
        "sampling": {
            "strategy": "scene_representatives+uniform_coverage",
            "interval_seconds": frame_interval,
            "scene_threshold": threshold,
            "scene_changes_detected": len(scenes),
            "requested_frame_count": len(timestamps),
            "frame_count": len(frames),
            "skipped_undecodable_frames": len(timestamps) - len(frames),
            "max_frames": frame_limit,
        },
        "scene_timestamps": scenes,
        "frames": frames,
    }
    (session / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def prepare_audio_guided_video(
    video_path: str | Path,
    settings: Settings,
    question: str,
    *,
    coverage_interval: float | None = None,
    max_frames: int | None = None,
    scene_threshold: float | None = None,
    output_dir: str | Path | None = None,
) -> tuple[dict, str]:
    """Transcribe first, then let AI select visually important time ranges."""
    source = Path(video_path).expanduser().resolve()
    info = probe_video(source)
    if not info.has_audio:
        raise RuntimeError("讲解视频模式需要声音，但这个视频没有音轨")
    if not settings.transcription_enabled:
        raise RuntimeError(
            "讲解视频模式需要先启用听觉模型。请在设置中选择本地 Whisper 或云端转写。"
        )
    root = Path(output_dir) if output_dir else settings.output_dir
    session = _session_dir(source, root.expanduser().resolve())
    transcript = _transcribe_into_session(info.to_dict(), session, settings)
    if not transcript.strip():
        raise RuntimeError("没有识别出可用于讲解分析的声音内容")

    provider = VisionProvider(settings)
    guidance = plan_audio_guidance(
        transcript, info.duration, question, provider
    )
    threshold = (
        scene_threshold if scene_threshold is not None else settings.scene_threshold
    )
    frame_limit = max_frames if max_frames is not None else settings.max_frames
    interval = (
        coverage_interval
        if coverage_interval is not None
        else max(15.0, settings.frame_interval)
    )
    scenes = detect_scene_timestamps(source, threshold)
    timestamps = choose_audio_guided_timestamps(
        info.duration,
        guidance,
        scenes,
        frame_limit,
        coverage_interval=interval,
    )
    frames = extract_frames(
        source, timestamps, session / "frames", settings.frame_width
    )
    manifest = {
        "session_dir": str(session),
        "video": info.to_dict(),
        "source": _load_source_metadata(source),
        "sampling": {
            "strategy": "audio_guided+scene_representatives+sparse_coverage",
            "interval_seconds": interval,
            "scene_threshold": threshold,
            "scene_changes_detected": len(scenes),
            "guidance_request_count": len(guidance["visual_requests"]),
            "requested_frame_count": len(timestamps),
            "frame_count": len(frames),
            "skipped_undecodable_frames": len(timestamps) - len(frames),
            "max_frames": frame_limit,
        },
        "scene_timestamps": scenes,
        "audio_guidance": guidance,
        "frames": frames,
    }
    (session / "audio-guidance.json").write_text(
        json.dumps(guidance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (session / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest, transcript


def analyze_prepared(
    manifest: dict,
    settings: Settings,
    question: str,
    *,
    transcript: str | None = None,
    audio_guidance: dict | None = None,
) -> dict:
    session = Path(manifest["session_dir"])
    video = manifest["video"]
    if transcript is None:
        transcript = _transcribe_into_session(video, session, settings)

    provider = VisionProvider(settings)
    frames = manifest["frames"]
    batches = [frames[index:index + settings.batch_size] for index in range(0, len(frames), settings.batch_size)]
    analyses = []
    for index, batch in enumerate(batches, start=1):
        excerpt = transcript_for_range(
            transcript,
            float(batch[0]["timestamp"]),
            float(batch[-1]["timestamp"]),
        )
        prompt = FRAME_PROMPT.format(
            question=question,
            transcript_excerpt=excerpt,
        )
        try:
            batch_result = analyze_frames_json(
                provider,
                prompt,
                batch,
                f"第 {index} 批视频画面分析",
            )
        except ValueError as exc:
            raise ValueError(f"第 {index} 批画面分析未返回有效 JSON") from exc
        analyses.append({
            "batch": index,
            "frame_count": len(batch),
            "result": batch_result,
        })

    # Let the first-pass model request denser evidence around ambiguous or fast
    # moments. Limit this loop so model output cannot create unbounded cost.
    detail_requests: list[dict] = []
    seen_timecodes: set[str] = set()
    for analysis in analyses if settings.max_detail_requests > 0 else []:
        for request in analysis["result"].get("detail_requests", []):
            timecode = str(request.get("timecode", "")).strip()
            if not timecode or timecode in seen_timecodes:
                continue
            seen_timecodes.add(timecode)
            detail_requests.append(request)
            if len(detail_requests) >= settings.max_detail_requests:
                break
        if len(detail_requests) >= settings.max_detail_requests:
            break

    duration = float(manifest["video"].get("duration") or 0)
    for index, request in enumerate(detail_requests, start=1):
        timecode = str(request["timecode"])
        try:
            timestamps = detail_timestamps(
                timecode, duration, radius=1.5, fps=2.0, max_frames=12
            )
        except ValueError:
            continue
        detail_frames = extract_frames(
            manifest["video"]["path"],
            timestamps,
            session / "detail-frames" / f"request-{index}",
            settings.frame_width,
        )
        reason = str(request.get("reason", "模型要求补充细节"))
        detail_excerpt = transcript_for_range(
            transcript,
            timestamps[0],
            timestamps[-1],
        )
        detail_prompt = FRAME_PROMPT.format(
            question=f"{question}\n重点复查 {timecode} 附近：{reason}",
            transcript_excerpt=detail_excerpt,
        )
        try:
            detail_result = analyze_frames_json(
                provider,
                detail_prompt,
                detail_frames,
                f"{timecode} 附近的补充画面分析",
            )
        except ValueError as exc:
            raise ValueError(f"{timecode} 附近的补充分析未返回有效 JSON") from exc
        analyses.append({
            "batch": f"detail-{index}",
            "requested_timecode": timecode,
            "reason": reason,
            "frame_count": len(detail_frames),
            "result": detail_result,
        })

    final_prompt = FINAL_PROMPT.format(
        question=question,
        video_info=json.dumps(
            {"video": video, "source": manifest.get("source", {})},
            ensure_ascii=False,
        ),
        audio_guidance=json.dumps(
            audio_guidance or manifest.get("audio_guidance", {}),
            ensure_ascii=False,
        ),
        analyses=json.dumps(analyses, ensure_ascii=False),
        transcript=(transcript[:80000] or "（未启用音频转写）"),
    )
    try:
        final = complete_text_json(provider, final_prompt, "最终视频分析报告")
    except ValueError as exc:
        raise ValueError("最终报告没有返回有效 JSON") from exc
    result = {
        "session_dir": manifest["session_dir"],
        "question": question,
        "provider": settings.provider,
        "model": settings.vision_model,
        "transcription_provider": settings.transcription_provider,
        "video": video,
        "source": manifest.get("source", {}),
        "sampling": manifest["sampling"],
        "analysis_mode": "narration" if audio_guidance else "balanced",
        "audio_guidance": audio_guidance or manifest.get("audio_guidance", {}),
        "batch_analyses": analyses,
        "transcript": transcript,
        "result": final,
    }
    (session / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (session / "report.md").write_text(render_markdown(result), encoding="utf-8")
    return result


def _transcribe_into_session(video: dict, session: Path, settings: Settings) -> str:
    if not settings.transcription_enabled or not video.get("has_audio"):
        return ""
    suffix = ".wav" if settings.transcription_provider == "local_whisper" else ".mp3"
    audio_path = extract_audio(video["path"], session / f"audio{suffix}")
    transcript = transcribe_audio(
        audio_path,
        settings,
        output_prefix=session / "whisper-transcript",
    )
    (session / "transcript.txt").write_text(transcript, encoding="utf-8")
    return transcript


def transcribe_video(
    video_path: str | Path,
    settings: Settings,
    *,
    output_dir: str | Path | None = None,
) -> dict:
    """Transcribe a video's audio without requiring any visual-model API key."""
    source = Path(video_path).expanduser().resolve()
    info = probe_video(source)
    if not info.has_audio:
        raise RuntimeError("视频中没有音轨")
    if not settings.transcription_enabled:
        raise RuntimeError("尚未启用听觉模型，请在设置中选择本地 Whisper 或云端转写")
    root = Path(output_dir) if output_dir else settings.output_dir
    session = _session_dir(source, root.expanduser().resolve())
    transcript = _transcribe_into_session(info.to_dict(), session, settings)
    result = {
        "session_dir": str(session),
        "video": info.to_dict(),
        "transcription_provider": settings.transcription_provider,
        "language": settings.transcription_language,
        "transcript": transcript,
    }
    (session / "transcription.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def analyze_video(
    video_path: str | Path,
    settings: Settings,
    question: str = "这个视频讲了什么？请按时间线分析。",
    mode: str = "balanced",
    **prepare_options,
) -> dict:
    if mode == "narration":
        manifest, transcript = prepare_audio_guided_video(
            video_path,
            settings,
            question,
            coverage_interval=prepare_options.get("interval"),
            max_frames=prepare_options.get("max_frames"),
            scene_threshold=prepare_options.get("scene_threshold"),
            output_dir=prepare_options.get("output_dir"),
        )
        return analyze_prepared(
            manifest,
            settings,
            question,
            transcript=transcript,
            audio_guidance=manifest["audio_guidance"],
        )
    manifest = prepare_video(video_path, settings, **prepare_options)
    return analyze_prepared(manifest, settings, question)


def extract_detail(
    video_path: str | Path,
    at: str | float,
    settings: Settings,
    *,
    radius: float = 2.0,
    fps: float = 2.0,
    output_dir: str | Path | None = None,
) -> dict:
    source = Path(video_path).expanduser().resolve()
    info = probe_video(source)
    timestamps = detail_timestamps(at, info.duration, radius, fps)
    root = Path(output_dir) if output_dir else settings.output_dir
    session = _session_dir(source, root.expanduser().resolve())
    frames = extract_frames(source, timestamps, session / "detail-frames", settings.frame_width)
    result = {
        "session_dir": str(session),
        "video": info.to_dict(),
        "center": at,
        "radius": radius,
        "fps": fps,
        "frames": frames,
    }
    (session / "detail.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def render_markdown(analysis: dict) -> str:
    result = analysis.get("result", {})
    lines = [
        "# 视频分析报告",
        "",
        f"- 问题：{analysis.get('question', '')}",
        f"- 模型：{analysis.get('provider', '')} / {analysis.get('model', '')}",
        f"- 视频：{analysis.get('video', {}).get('path', '')}",
        "",
        "## 摘要",
        "",
        str(result.get("summary", "")),
        "",
        "## 直接回答",
        "",
        str(result.get("answer", "")),
        "",
        "## 时间线",
        "",
    ]
    for item in result.get("timeline", []):
        lines.append(f"- `{item.get('timecode', '')}` {item.get('event', '')}（{item.get('evidence', '')}）")
    lines.extend(["", "## 关键词", ""])
    for item in result.get("keywords", []):
        lines.append(
            f"- `{item.get('timecode', '')}` **{item.get('term', '')}**："
            f"{item.get('context', '')}（{item.get('source', '')}）"
        )
    lines.extend(["", "## 不确定性", ""])
    for item in result.get("uncertainties", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
