from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


SUPPORTED_COOKIE_BROWSERS = {"", "none", "safari", "chrome", "chromium", "edge", "firefox"}


def _validate_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入完整的视频链接，例如 https://v.douyin.com/...")
    return url


def _downloaded_path(info: dict, ydl: YoutubeDL, directory: Path) -> Path:
    candidates: list[Path] = []
    for item in info.get("requested_downloads") or []:
        filepath = item.get("filepath") if isinstance(item, dict) else None
        if filepath:
            candidates.append(Path(filepath))
    candidates.append(Path(ydl.prepare_filename(info)))
    identifier = str(info.get("id") or "")
    if identifier:
        candidates.extend(directory.glob(f"*{identifier}*"))
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() not in {".json", ".part", ".ytdl"}:
            return candidate.resolve()
    raise RuntimeError("视频下载完成，但没有找到生成的媒体文件")


def import_video_url(
    url: str,
    output_dir: str | Path,
    *,
    browser_cookies: str = "none",
) -> dict:
    """Download one public video URL for local analysis using yt-dlp."""
    source_url = _validate_url(url)
    browser = browser_cookies.strip().lower()
    if browser not in SUPPORTED_COOKIE_BROWSERS:
        raise ValueError(f"不支持的浏览器 Cookie 来源：{browser_cookies}")

    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    options: dict = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(directory / "%(title).90B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": False,
        "restrictfilenames": False,
    }
    if browser not in {"", "none"}:
        options["cookiesfrombrowser"] = (browser, None, None, None)

    try:
        with YoutubeDL(options) as ydl:
            payload = ydl.extract_info(source_url, download=True)
            if not isinstance(payload, dict):
                raise RuntimeError("视频站点没有返回可用信息")
            info = payload.get("entries", [payload])[0] if payload.get("entries") else payload
            if not isinstance(info, dict):
                raise RuntimeError("视频站点没有返回可用信息")
            path = _downloaded_path(info, ydl, directory)
    except DownloadError as exc:
        message = str(exc).replace("ERROR: ", "").strip()
        if "cookie" in message.lower():
            raise RuntimeError(
                "该链接需要新的登录 Cookie。请先在浏览器登录抖音，再选择对应浏览器重试。"
            ) from exc
        raise RuntimeError(f"视频链接导入失败：{message}") from exc

    result = {
        "path": str(path),
        "title": str(info.get("title") or path.stem),
        "source_url": str(info.get("webpage_url") or source_url),
        "source_id": str(info.get("id") or ""),
        "author": str(info.get("uploader") or info.get("creator") or ""),
        "description": str(info.get("description") or ""),
        "duration": float(info.get("duration") or 0),
        "thumbnail": str(info.get("thumbnail") or ""),
        "extractor": str(info.get("extractor_key") or info.get("extractor") or ""),
    }
    metadata_path = path.with_name(f"{path.name}.source.json")
    metadata_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result["metadata_path"] = str(metadata_path)
    return result
