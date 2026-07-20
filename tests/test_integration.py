from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from video_agent.config import Settings
from video_agent.media import probe_video
from video_agent.workflow import analyze_video, extract_detail, prepare_video


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")
def test_prepare_and_detail_workflow(tmp_path, monkeypatch):
    video = tmp_path / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1:r=10",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1:r=10",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[out]",
        "-map", "[out]", "-pix_fmt", "yuv420p", "-y", str(video),
    ], check=True)
    monkeypatch.setenv("VIDEO_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    settings = Settings.from_env(tmp_path / "missing.env")

    info = probe_video(video)
    assert 1.9 <= info.duration <= 2.1

    manifest = prepare_video(video, settings, interval=0.75, max_frames=8)
    assert manifest["frames"]
    assert (tmp_path / "output").is_dir()
    assert all(Path(frame["path"]).is_file() for frame in manifest["frames"])

    sidecar = video.with_name(f"{video.name}.source.json")
    sidecar.write_text('{"author":"测试作者","source_url":"https://example.com/video"}')
    sourced_manifest = prepare_video(video, settings, interval=1, max_frames=4)
    assert sourced_manifest["source"]["author"] == "测试作者"

    detail = extract_detail(video, "00:01", settings, radius=0.5, fps=2)
    assert len(detail["frames"]) == 3


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")
def test_narration_mode_transcribes_before_guided_frame_analysis(tmp_path, monkeypatch):
    video = tmp_path / "narration.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3:r=10",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-shortest", "-pix_fmt", "yuv420p", "-y", str(video),
    ], check=True)
    monkeypatch.setenv("VIDEO_AGENT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("VIDEO_AGENT_TRANSCRIPTION_PROVIDER", "local_whisper")
    settings = Settings.from_env(tmp_path / "missing.env")

    transcript = "[0.00-1.50] 打开设置页面\n[1.50-2.90] 选择视觉模型"

    def fake_transcribe(video_info, session, current_settings):
        (session / "transcript.txt").write_text(transcript, encoding="utf-8")
        return transcript

    class FakeProvider:
        def __init__(self, current_settings):
            pass

        def complete_text(self, prompt):
            if "规划视觉取证位置" in prompt:
                return """{
                    "overview": "演示设置",
                    "spoken_keywords": [{"timecode": "00:00:01", "term": "视觉模型"}],
                    "visual_requests": [{
                        "start": 0.5,
                        "end": 2.5,
                        "reason": "确认设置页面",
                        "sampling": "dense"
                    }]
                }"""
            return """{
                "summary": "演示视觉模型设置",
                "answer": "先打开设置，再选择模型。",
                "timeline": [{"timecode": "00:00:01", "event": "设置模型", "evidence": "both"}],
                "keywords": [{"timecode": "00:00:01", "term": "视觉模型", "source": "audio", "context": "设置项"}],
                "people_objects_places": ["设置页面"],
                "visible_text": [],
                "uncertainties": [],
                "recommended_followups": []
            }"""

        def analyze_frames(self, prompt, frames):
            assert "打开设置页面" in prompt or "选择视觉模型" in prompt
            return """{
                "segment_summary": "设置操作",
                "events": [],
                "entities": ["设置页面"],
                "audio_keywords": [],
                "visible_text": [],
                "uncertainties": [],
                "detail_requests": []
            }"""

    monkeypatch.setattr("video_agent.workflow._transcribe_into_session", fake_transcribe)
    monkeypatch.setattr("video_agent.workflow.VisionProvider", FakeProvider)

    result = analyze_video(
        video,
        settings,
        "整理操作步骤",
        mode="narration",
        max_frames=8,
        interval=15,
    )
    assert result["analysis_mode"] == "narration"
    assert result["transcript"] == transcript
    assert result["sampling"]["strategy"].startswith("audio_guided")
    assert result["sampling"]["guidance_request_count"] == 1
    assert result["result"]["summary"] == "演示视觉模型设置"
    assert Path(result["session_dir"], "audio-guidance.json").is_file()
