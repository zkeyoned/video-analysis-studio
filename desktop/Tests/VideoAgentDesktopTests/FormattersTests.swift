import Foundation
import Testing
@testable import VideoAgentDesktop

@Test func durationFormatting() {
    #expect(Formatters.duration(65) == "1:05")
    #expect(Formatters.duration(3661) == "1:01:01")
}

@Test func snakeCaseManifestDecoding() throws {
    let json = #"{"path":"/tmp/a.mp4","duration":10,"width":1920,"height":1080,"fps":30,"codec":"h264","has_audio":true,"size_bytes":123}"#
    let value = try JSONDecoder.videoAgent.decode(VideoInfo.self, from: Data(json.utf8))
    #expect(value.hasAudio)
    #expect(value.sizeBytes == 123)
}

@Test func knowledgeLibrarySearchIncludesSummaryAndTranscript() {
    let item = SessionSummary(
        directory: URL(fileURLWithPath: "/tmp/demo"),
        title: "Agent 教程",
        date: .now,
        frameCount: 12,
        hasAnalysis: true,
        summary: "演示如何管理收藏夹",
        keywords: ["Codex", "自动化"],
        author: "DannyZ",
        sourceURL: "https://example.com",
        searchIndex: "把视频完整地看一遍"
    )
    #expect(item.matches("收藏夹"))
    #expect(item.matches("完整地看"))
    #expect(!item.matches("烹饪"))
}

@Test func parsesReportAndTranscriptTimecodes() {
    #expect(Formatters.timecodeSeconds("00:01:25.500") == 85.5)
    #expect(Formatters.timecodeSeconds("01:25") == 85)

    let cues = Formatters.transcriptCues(
        "[1.00-3.50] 打开设置页面\n[4.00-6.00] 选择视觉模型"
    )
    #expect(cues.count == 2)
    #expect(cues[0].start == 1)
    #expect(cues[1].text == "选择视觉模型")
}
