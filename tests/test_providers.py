import json
from types import SimpleNamespace

import httpx

from video_agent.providers import VisionProvider, extract_json
from video_agent.local_asr import parse_srt_transcript, parse_whisper_json
from video_agent.workflow import (
    analyze_frames_json,
    choose_audio_guided_timestamps,
    chunk_transcript,
    extract_or_repair_json,
    plan_audio_guidance,
    transcript_for_range,
)


def test_extract_plain_json():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_extract_fenced_json():
    assert extract_json('说明\n```json\n{"value": 3}\n```') == {"value": 3}


def test_extract_json_surrounded_by_text():
    assert extract_json('结果如下： {"items": [1, 2]} 完成') == {"items": [1, 2]}


def test_parse_local_whisper_srt_with_timestamps():
    value = parse_srt_transcript(
        """1
00:00:01,000 --> 00:00:03,500
他后来发现了关键暗号

2
00:00:04,000 --> 00:00:06,000
警方开始调查
"""
    )
    assert "[1.00-3.50] 他后来发现了关键暗号" in value
    assert "[4.00-6.00] 警方开始调查" in value


def test_local_whisper_transcript_is_converted_to_simplified_chinese():
    value = parse_srt_transcript(
        """1
00:00:00,000 --> 00:00:02,000
這個視頻轉發給自己,整理到飛書表格裡
""",
        simplified_chinese=True,
    )
    assert value == "[0.00-2.00] 这个视频转发给自己，整理到飞书表格里"


def test_whisper_json_uses_token_timestamps_for_short_clauses():
    value = parse_whisper_json(
        json.dumps({
            "transcription": [{
                "tokens": [
                    {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                    {"text": "這個", "offsets": {"from": 100, "to": 500}},
                    {"text": "教程", "offsets": {"from": 500, "to": 1100}},
                    {"text": "，", "offsets": {"from": 1100, "to": 1200}},
                    {"text": "整理到", "offsets": {"from": 1200, "to": 1800}},
                    {"text": "飛書表格", "offsets": {"from": 1800, "to": 2500}},
                    {"text": "。", "offsets": {"from": 2500, "to": 2600}},
                    {"text": "[_TT_130]", "offsets": {"from": 2600, "to": 2600}},
                ]
            }]
        }, ensure_ascii=False),
        simplified_chinese=True,
    )
    assert value.splitlines() == [
        "[0.10-1.20] 这个教程，",
        "[1.20-2.60] 整理到飞书表格。",
    ]


def test_transcript_excerpt_follows_frame_batch_time():
    transcript = "\n".join([
        "[1.00-3.50] 他后来发现了关键暗号",
        "[20.00-22.00] 另一段对白",
    ])
    excerpt = transcript_for_range(transcript, 0, 8)
    assert "关键暗号" in excerpt
    assert "另一段对白" not in excerpt


def test_chunk_transcript_keeps_timestamped_lines_intact():
    transcript = "\n".join([
        "[0.00-2.00] 打开设置页面",
        "[2.00-4.00] 选择视觉模型",
        "[4.00-6.00] 保存设置",
    ])
    chunks = chunk_transcript(transcript, max_chars=40)
    assert len(chunks) > 1
    assert "打开设置页面" in chunks[0]
    assert all(line.startswith("[") for chunk in chunks for line in chunk.splitlines())


def test_audio_guidance_uses_transcript_times():
    class FakeProvider:
        def complete_text(self, prompt):
            assert "打开设置页面" in prompt
            return """{
                "overview": "演示模型设置",
                "spoken_keywords": [{"timecode": "00:00:02", "term": "视觉模型"}],
                "visual_requests": [{
                    "start": 1.0,
                    "end": 5.0,
                    "reason": "确认设置项和模型名称",
                    "sampling": "dense"
                }]
            }"""

    guidance = plan_audio_guidance(
        "[0.00-3.00] 打开设置页面\n[3.00-6.00] 选择视觉模型",
        10.0,
        "整理操作步骤",
        FakeProvider(),
    )
    request = guidance["visual_requests"][0]
    assert request["start"] == 1.0
    assert request["end"] == 5.0
    assert request["sampling"] == "dense"


def test_audio_guided_timestamps_include_targets_and_safety_coverage():
    guidance = {
        "visual_requests": [{
            "start": 40.0,
            "end": 44.0,
            "reason": "确认按钮操作",
            "sampling": "dense",
        }]
    }
    timestamps = choose_audio_guided_timestamps(
        100.0,
        guidance,
        [20.0, 42.0, 80.0],
        max_frames=20,
        coverage_interval=30.0,
    )
    assert timestamps[0] == 0.0
    assert any(40.0 <= value <= 44.0 for value in timestamps)
    assert any(value >= 80.0 for value in timestamps)
    assert len(timestamps) <= 20


def test_dashscope_qwen_disables_thinking_and_requests_json():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3-vl-flash"
        assert payload["enable_thinking"] is False
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok":true}'}}]},
        )

    provider = object.__new__(VisionProvider)
    provider.settings = SimpleNamespace(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="test-key",
        vision_model="qwen3-vl-flash",
    )
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert provider._openai_content([{"type": "text", "text": "返回 JSON"}]) == '{"ok":true}'


def test_invalid_model_json_is_repaired_with_text_only_call():
    class FakeProvider:
        def complete_text(self, prompt):
            assert "待修复内容" in prompt
            return '{"summary":"修复完成"}'

    value = extract_or_repair_json(
        '{"summary":"缺少结尾"',
        FakeProvider(),
        "测试报告",
    )
    assert value == {"summary": "修复完成"}


def test_frame_json_retries_after_failed_repair():
    class FakeProvider:
        def __init__(self):
            self.frame_calls = 0

        def analyze_frames(self, prompt, frames):
            self.frame_calls += 1
            if self.frame_calls == 1:
                return "完全不是 JSON"
            assert "上一次输出无法解析" in prompt
            return '{"events":[]}'

        def complete_text(self, prompt):
            return "仍然不是 JSON"

    provider = FakeProvider()
    value = analyze_frames_json(provider, "返回 JSON", [], "批次测试")
    assert value == {"events": []}
    assert provider.frame_calls == 2
