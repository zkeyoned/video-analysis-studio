from pathlib import Path

from video_agent.media import (
    choose_timestamps,
    detail_timestamps,
    format_timestamp,
    parse_rate,
    parse_timestamp,
    scene_representative_timestamps,
    uniform_timestamps,
)
from video_agent import media


def test_parse_timestamp_formats():
    assert parse_timestamp("12.5") == 12.5
    assert parse_timestamp("01:02.5") == 62.5
    assert parse_timestamp("01:02:03") == 3723.0
    assert format_timestamp(62.5) == "00:01:02.500"


def test_parse_rate():
    assert round(parse_rate("30000/1001"), 3) == 29.97
    assert parse_rate("25") == 25
    assert parse_rate("0/0") == 0


def test_uniform_includes_video_edges():
    assert uniform_timestamps(12, 5) == [0.0, 5, 10, 11.75]


def test_sampling_respects_frame_limit_and_timeline():
    selected = choose_timestamps(
        duration=120,
        interval=10,
        scene_times=[3, 4, 11, 19, 21, 33, 48, 61, 85, 101, 110],
        max_frames=8,
    )
    assert len(selected) == 8
    assert selected == sorted(selected)
    assert selected[0] == 0
    assert selected[-1] > 100


def test_scene_sampling_uses_shot_interior_not_cut_frames():
    representatives = scene_representative_timestamps(
        duration=30,
        scene_times=[10, 20],
        samples_per_scene=1,
    )
    assert representatives == [5.0, 15.0, 25.0]
    assert 10 not in representatives
    assert 20 not in representatives


def test_detail_sampling_is_bounded():
    values = detail_timestamps("00:10", duration=12, radius=2, fps=2)
    assert values[0] == 8
    assert values[-1] == 11.5
    assert len(values) == 8


def test_extract_frames_skips_one_undecodable_timestamp(tmp_path, monkeypatch):
    def fake_extract(video_path, timestamp, output_path, width=1280, backoffs=(0.0,)):
        if timestamp >= 2:
            raise RuntimeError("bad tail")
        path = output_path
        path.write_bytes(b"jpeg")
        return path, timestamp

    monkeypatch.setattr(media, "extract_frame_resilient", fake_extract)
    frames = media.extract_frames(
        tmp_path / "video.mp4",
        [0.0, 1.0, 2.0],
        tmp_path / "frames",
    )
    assert [frame["timestamp"] for frame in frames] == [0.0, 1.0]
    assert [frame["index"] for frame in frames] == [1, 2]


def test_extract_frame_retries_slightly_earlier(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, timeout=300):
        timestamp = float(args[args.index("-ss") + 1])
        calls.append(timestamp)
        if timestamp == 10.0:
            raise RuntimeError("seek failed")
        Path(args[-1]).write_bytes(b"jpeg")

    monkeypatch.setattr(media, "_run", fake_run)
    path, actual = media.extract_frame_resilient(
        tmp_path / "video.mp4",
        10.0,
        tmp_path / "frame.jpg",
    )
    assert path.is_file()
    assert actual == 9.9
    assert calls == [10.0, 9.9]
