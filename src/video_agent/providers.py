from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .local_asr import transcribe_with_whisper_cpp


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [position for position in (cleaned.find("{"), cleaned.find("[")) if position >= 0]
        if not start_candidates:
            raise ValueError("模型没有返回有效 JSON")
        start = min(start_candidates)
        decoder = json.JSONDecoder()
        try:
            value, _ = decoder.raw_decode(cleaned[start:])
            return value
        except json.JSONDecodeError as exc:
            raise ValueError("模型没有返回有效 JSON") from exc


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _gemini_inline(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return {
        "inlineData": {
            "mimeType": mime,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    }


class VisionProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.require_api_key()
        self.client = httpx.Client(timeout=settings.request_timeout)

    def analyze_frames(self, prompt: str, frames: list[dict]) -> str:
        if self.settings.provider == "gemini":
            return self._gemini_frames(prompt, frames)
        if self.settings.provider == "openai_compatible":
            return self._openai_frames(prompt, frames)
        raise ValueError(f"不支持的 Provider：{self.settings.provider}")

    def complete_text(self, prompt: str) -> str:
        if self.settings.provider == "gemini":
            return self._gemini_parts([{"text": prompt}])
        if self.settings.provider == "openai_compatible":
            return self._openai_content([{"type": "text", "text": prompt}])
        raise ValueError(f"不支持的 Provider：{self.settings.provider}")

    def _openai_frames(self, prompt: str, frames: list[dict]) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for frame in frames:
            content.append({
                "type": "text",
                "text": f"帧 {frame['index']}，时间 {frame['timecode']}",
            })
            content.append({
                "type": "image_url",
                "image_url": {"url": _image_data_url(Path(frame["path"])), "detail": "auto"},
            })
        return self._openai_content(content)

    def _openai_content(self, content: list[dict]) -> str:
        url = f"{self.settings.base_url}/chat/completions"
        payload = {
            "model": self.settings.vision_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
        }
        if (
            "dashscope.aliyuncs.com" in self.settings.base_url
            and self.settings.vision_model.lower().startswith("qwen")
        ):
            # Qwen's thinking tokens are billed as output. Video analysis needs
            # stable structured JSON more than extra chain-of-thought, so keep
            # the inexpensive non-thinking path explicit.
            payload["enable_thinking"] = False
            payload["response_format"] = {"type": "json_object"}
        response = self.client.post(
            url,
            headers={"Authorization": f"Bearer {self.settings.api_key}"},
            json=payload,
        )
        self._raise(response)
        payload = response.json()
        try:
            value = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"视觉接口返回格式异常：{payload}") from exc
        if isinstance(value, list):
            return "\n".join(str(item.get("text", "")) for item in value if isinstance(item, dict))
        return str(value)

    def _gemini_frames(self, prompt: str, frames: list[dict]) -> str:
        parts: list[dict] = [{"text": prompt}]
        for frame in frames:
            parts.append({"text": f"帧 {frame['index']}，时间 {frame['timecode']}"})
            parts.append(_gemini_inline(Path(frame["path"])))
        return self._gemini_parts(parts)

    def _gemini_parts(self, parts: list[dict]) -> str:
        model = self.settings.vision_model.removeprefix("models/")
        url = f"{self.settings.base_url}/models/{model}:generateContent"
        response = self.client.post(
            url,
            params={"key": self.settings.api_key},
            json={
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.1},
            },
        )
        self._raise(response)
        payload = response.json()
        try:
            return "\n".join(
                item.get("text", "")
                for item in payload["candidates"][0]["content"]["parts"]
                if "text" in item
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini 返回格式异常：{payload}") from exc

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = response.text[:800]
        raise RuntimeError(f"模型接口请求失败（HTTP {response.status_code}）：{detail}")


def transcribe_audio(
    audio_path: Path,
    settings: Settings,
    *,
    output_prefix: Path | None = None,
) -> str:
    if not settings.transcription_enabled:
        return ""
    if settings.transcription_provider == "local_whisper":
        return transcribe_with_whisper_cpp(
            audio_path,
            settings.local_whisper_model_path,
            settings.transcription_language,
            output_prefix or audio_path.with_suffix(""),
            prompt=settings.transcription_prompt,
            timeout=max(600, settings.request_timeout * 10),
        )
    if settings.transcription_provider != "openai_compatible":
        raise ValueError(
            f"不支持的转写 Provider：{settings.transcription_provider}"
        )
    if not settings.transcription_model:
        raise RuntimeError("云端转写已启用，但没有填写转写模型名称")
    key = settings.transcription_api_key or settings.api_key
    base_url = settings.transcription_base_url or settings.base_url
    if not key:
        raise RuntimeError("已配置转写模型，但没有可用的转写 API Key")
    with audio_path.open("rb") as source:
        response = httpx.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={
                "file": (
                    audio_path.name,
                    source,
                    "audio/wav" if audio_path.suffix.lower() == ".wav" else "audio/mpeg",
                )
            },
            data={
                "model": settings.transcription_model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            },
            timeout=settings.request_timeout,
        )
    if not response.is_success:
        raise RuntimeError(
            f"语音转写失败（HTTP {response.status_code}）：{response.text[:800]}"
        )
    payload = response.json()
    if payload.get("segments"):
        return "\n".join(
            f"[{segment.get('start', 0):.2f}-{segment.get('end', 0):.2f}] "
            f"{str(segment.get('text', '')).strip()}"
            for segment in payload["segments"]
        )
    return str(payload.get("text", ""))
