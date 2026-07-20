from pathlib import Path

import pytest

from video_agent.video_import import _downloaded_path, _validate_url


def test_validate_video_url():
    assert _validate_url(" https://v.douyin.com/example/ ") == "https://v.douyin.com/example/"
    with pytest.raises(ValueError):
        _validate_url("不是链接")


def test_find_downloaded_path_from_requested_downloads(tmp_path: Path):
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"video")

    class StubYDL:
        def prepare_filename(self, info):
            return str(tmp_path / "missing.webm")

    result = _downloaded_path(
        {"requested_downloads": [{"filepath": str(video)}]},
        StubYDL(),  # type: ignore[arg-type]
        tmp_path,
    )
    assert result == video.resolve()
