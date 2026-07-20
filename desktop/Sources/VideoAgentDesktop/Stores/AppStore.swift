import AppKit
import Foundation
import Observation
import UniformTypeIdentifiers

extension Notification.Name {
    static let chooseVideo = Notification.Name("VideoAgentDesktop.chooseVideo")
    static let importVideoLink = Notification.Name("VideoAgentDesktop.importVideoLink")
    static let startAnalysis = Notification.Name("VideoAgentDesktop.startAnalysis")
}

@MainActor
@Observable
final class AppStore {
    var selectedVideoURL: URL?
    var videoInfo: VideoInfo?
    var sourceMetadata: SourceMetadata?
    var frames: [FrameItem] = []
    var report = ""
    var transcript = ""
    var analysisResult: AnalysisResult?
    var question = "请概括视频内容，按时间线列出关键事件，并完整提取人物、地点、物品、动作、关系、事件和剧情转折等关键词。"
    var analysisMode = "narration"
    var interval = 6.0
    var coverageInterval = 20.0
    var maxFrames = 60
    var isBusy = false
    var statusMessage = "选择一个视频开始"
    var errorMessage = ""
    var sessionDirectory: URL?
    var recentSessions: [SessionSummary] = []
    var searchText = ""
    var isShowingLinkImporter = false
    var videoLink = ""
    var browserCookieSource = "none"
    var analyzeAfterLinkImport = true
    var selection: WorkspaceSelection? = .newAnalysis
    var playbackRequest: PlaybackRequest?

    let settings: SettingsStore
    private let backend = BackendService()

    init(settings: SettingsStore) {
        self.settings = settings
        refreshRecentSessions()
        if let path = ProcessInfo.processInfo.arguments.dropFirst().first,
           FileManager.default.fileExists(atPath: path) {
            selectVideo(URL(fileURLWithPath: path))
        }
    }

    var filteredSessions: [SessionSummary] {
        recentSessions.filter { $0.matches(searchText) }
    }

    var isNarrationMode: Bool { analysisMode == "narration" }

    var canUseNarrationMode: Bool {
        !["", "none", "disabled"].contains(settings.transcriptionProvider)
    }

    func chooseVideo() {
        let panel = NSOpenPanel()
        panel.title = "选择要分析的视频"
        panel.prompt = "选择视频"
        panel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie, .avi]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        selectVideo(url)
    }

    func selectVideo(_ url: URL) {
        guard url.isFileURL else { return }
        selectedVideoURL = url
        selection = .newAnalysis
        videoInfo = nil
        sourceMetadata = nil
        frames = []
        report = ""
        transcript = ""
        analysisResult = nil
        playbackRequest = nil
        errorMessage = ""
        statusMessage = "正在读取视频信息…"
        Task { await probeSelectedVideo() }
    }

    func prepare() {
        guard let video = selectedVideoURL else { return }
        begin("正在检测镜头并抽取关键帧…")
        Task {
            do {
                let data = try await backend.run(
                    arguments: [
                        "prepare", video.path,
                        "--interval", String(interval),
                        "--max-frames", String(maxFrames)
                    ],
                    environment: settings.processEnvironment
                )
                let manifest = try JSONDecoder.videoAgent.decode(ManifestEnvelope.self, from: data)
                apply(manifest)
                statusMessage = samplingStatus(manifest)
                finish()
            } catch {
                fail(error)
            }
        }
    }

    func importVideoLink() {
        let link = videoLink.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: link), let scheme = url.scheme,
              ["http", "https"].contains(scheme.lowercased()) else {
            errorMessage = "请输入完整的视频链接。"
            statusMessage = "链接格式不正确"
            return
        }

        isShowingLinkImporter = false
        begin("正在下载视频并加入知识库…")
        Task {
            do {
                let data = try await backend.run(
                    arguments: [
                        "import-url", link,
                        "--browser-cookies", browserCookieSource
                    ],
                    environment: settings.processEnvironment
                )
                let imported = try JSONDecoder.videoAgent.decode(ImportedVideo.self, from: data)
                let videoURL = URL(fileURLWithPath: imported.path)

                selectedVideoURL = videoURL
                selection = .newAnalysis
                videoInfo = nil
                sourceMetadata = nil
                frames = []
                report = ""
                transcript = ""
                analysisResult = nil
                errorMessage = ""
                statusMessage = "下载完成，正在读取视频…"

                let probeData = try await backend.run(
                    arguments: ["probe", videoURL.path],
                    environment: settings.processEnvironment
                )
                videoInfo = try JSONDecoder.videoAgent.decode(VideoInfo.self, from: probeData)
                let canAutoAnalyze = analyzeAfterLinkImport
                    && !settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    && (!isNarrationMode || canUseNarrationMode)
                if canAutoAnalyze && isNarrationMode {
                    videoLink = ""
                    finish()
                    analyze()
                    return
                }
                statusMessage = "正在抽取镜头内部代表帧…"

                let manifestData = try await backend.run(
                    arguments: [
                        "prepare", videoURL.path,
                        "--interval", String(interval),
                        "--max-frames", String(maxFrames)
                    ],
                    environment: settings.processEnvironment
                )
                let manifest = try JSONDecoder.videoAgent.decode(ManifestEnvelope.self, from: manifestData)
                apply(manifest)
                videoLink = ""
                statusMessage = "已加入知识库，\(samplingStatus(manifest))"
                finish()

                if canAutoAnalyze {
                    analyze()
                }
            } catch {
                fail(error)
            }
        }
    }

    func analyze() {
        guard let video = selectedVideoURL else { return }
        guard !settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "请先打开设置，填写视觉模型 API Key。"
            statusMessage = "缺少 API Key"
            return
        }
        guard !settings.model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "请先在设置中填写视觉模型名称或推理接入点 ID。"
            statusMessage = "缺少模型名称"
            return
        }
        guard !isNarrationMode || canUseNarrationMode else {
            errorMessage = "讲解视频模式需要先在设置中启用本地 Whisper 或云端转写。"
            statusMessage = "尚未启用听觉模型"
            return
        }
        begin(isNarrationMode
              ? "正在听完整段视频，并让 AI 选择需要查看的时间…"
              : "正在抽帧并调用视觉模型，这可能需要几分钟…")
        Task {
            do {
                let arguments: [String]
                if isNarrationMode {
                    arguments = [
                        "analyze", video.path,
                        "--mode", "narration",
                        "--question", question,
                        "--interval", String(coverageInterval),
                        "--max-frames", String(maxFrames)
                    ]
                } else if let sessionDirectory,
                   !frames.isEmpty,
                   FileManager.default.fileExists(
                       atPath: sessionDirectory.appendingPathComponent("manifest.json").path
                   ) {
                    arguments = [
                        "analyze-prepared",
                        sessionDirectory.appendingPathComponent("manifest.json").path,
                        "--question", question
                    ]
                } else {
                    arguments = [
                        "analyze", video.path,
                        "--question", question,
                        "--interval", String(interval),
                        "--max-frames", String(maxFrames)
                    ]
                }
                let data = try await backend.run(
                    arguments: arguments,
                    environment: settings.processEnvironment
                )
                let analysis = try JSONDecoder.videoAgent.decode(AnalysisEnvelope.self, from: data)
                let directory = URL(fileURLWithPath: analysis.sessionDir)
                let manifestURL = directory.appendingPathComponent("manifest.json")
                let manifestData = try Data(contentsOf: manifestURL)
                let manifest = try JSONDecoder.videoAgent.decode(ManifestEnvelope.self, from: manifestData)
                apply(manifest)
                analysisResult = analysis.result
                transcript = analysis.transcript
                if analysis.analysisMode == "narration" {
                    analysisMode = "narration"
                }
                report = (try? String(contentsOf: directory.appendingPathComponent("report.md"), encoding: .utf8)) ?? analysis.result.summary
                statusMessage = analysis.analysisMode == "narration"
                    ? "声音主线与定向画面分析完成"
                    : "分析完成"
                finish()
            } catch {
                fail(error)
            }
        }
    }

    func loadSession(_ summary: SessionSummary) {
        do {
            let manifestData = try Data(contentsOf: summary.directory.appendingPathComponent("manifest.json"))
            let manifest = try JSONDecoder.videoAgent.decode(ManifestEnvelope.self, from: manifestData)
            apply(manifest)
            let analysisURL = summary.directory.appendingPathComponent("analysis.json")
            if FileManager.default.fileExists(atPath: analysisURL.path) {
                let data = try Data(contentsOf: analysisURL)
                let analysis = try JSONDecoder.videoAgent.decode(AnalysisEnvelope.self, from: data)
                analysisResult = analysis.result
                transcript = analysis.transcript
                question = analysis.question
                if let mode = analysis.analysisMode {
                    analysisMode = mode
                }
                report = (try? String(contentsOf: summary.directory.appendingPathComponent("report.md"), encoding: .utf8)) ?? analysis.result.summary
            } else {
                analysisResult = nil
                transcript = ""
                report = ""
            }
            statusMessage = summary.hasAnalysis ? "已载入分析记录" : "已载入抽帧记录"
            errorMessage = ""
        } catch {
            fail(error)
        }
    }

    func newAnalysis() {
        selection = .newAnalysis
        selectedVideoURL = nil
        videoInfo = nil
        sourceMetadata = nil
        frames = []
        report = ""
        transcript = ""
        analysisResult = nil
        playbackRequest = nil
        sessionDirectory = nil
        statusMessage = "选择一个视频开始"
        errorMessage = ""
    }

    func refreshRecentSessions() {
        guard let root = try? backend.projectRoot().appendingPathComponent("output") else { return }
        let keys: Set<URLResourceKey> = [.contentModificationDateKey, .isDirectoryKey]
        guard let directories = try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: Array(keys),
            options: [.skipsHiddenFiles]
        ) else { return }
        recentSessions = directories.compactMap { directory in
            guard let values = try? directory.resourceValues(forKeys: keys), values.isDirectory == true else { return nil }
            let manifestURL = directory.appendingPathComponent("manifest.json")
            guard let data = try? Data(contentsOf: manifestURL),
                  let manifest = try? JSONDecoder.videoAgent.decode(ManifestEnvelope.self, from: data) else { return nil }
            let analyzed = FileManager.default.fileExists(atPath: directory.appendingPathComponent("analysis.json").path)
            let analysis: AnalysisEnvelope? = {
                guard analyzed,
                      let data = try? Data(contentsOf: directory.appendingPathComponent("analysis.json")) else {
                    return nil
                }
                return try? JSONDecoder.videoAgent.decode(AnalysisEnvelope.self, from: data)
            }()
            let source = analysis?.source ?? manifest.source
            return SessionSummary(
                directory: directory,
                title: source?.title.flatMap { $0.isEmpty ? nil : $0 }
                    ?? URL(fileURLWithPath: manifest.video.path).deletingPathExtension().lastPathComponent,
                date: values.contentModificationDate ?? .distantPast,
                frameCount: manifest.frames.count,
                hasAnalysis: analyzed,
                summary: analysis?.result.summary ?? "",
                keywords: analysis?.result.keywords?.map(\.term) ?? [],
                author: source?.author ?? "",
                sourceURL: source?.sourceURL ?? "",
                searchIndex: analysis?.transcript ?? ""
            )
        }
        .sorted { $0.date > $1.date }
    }

    private func probeSelectedVideo() async {
        guard let video = selectedVideoURL else { return }
        do {
            let data = try await backend.run(
                arguments: ["probe", video.path],
                environment: settings.processEnvironment
            )
            videoInfo = try JSONDecoder.videoAgent.decode(VideoInfo.self, from: data)
            statusMessage = "视频已就绪"
        } catch {
            fail(error)
        }
    }

    private func begin(_ message: String) {
        isBusy = true
        errorMessage = ""
        statusMessage = message
    }

    private func finish() {
        isBusy = false
        refreshRecentSessions()
    }

    private func fail(_ error: Error) {
        isBusy = false
        errorMessage = error.localizedDescription
        statusMessage = "处理失败"
    }

    private func apply(_ manifest: ManifestEnvelope) {
        selectedVideoURL = URL(fileURLWithPath: manifest.video.path)
        videoInfo = manifest.video
        sourceMetadata = manifest.source
        frames = manifest.frames
        sessionDirectory = URL(fileURLWithPath: manifest.sessionDir)
    }

    func seek(to seconds: Double) {
        playbackRequest = PlaybackRequest(seconds: seconds)
    }

    func seek(to timecode: String) {
        guard let seconds = Formatters.timecodeSeconds(timecode) else { return }
        seek(to: seconds)
    }

    private func samplingStatus(_ manifest: ManifestEnvelope) -> String {
        let skipped = manifest.sampling.skippedUndecodableFrames ?? 0
        let prefix: String
        if let count = manifest.sampling.guidanceRequestCount, count > 0 {
            prefix = "声音定位 (count) 个重点，抽取 (manifest.frames.count) 张画面"
        } else {
            prefix = "已抽取 (manifest.frames.count) 张关键帧"
        }
        if skipped > 0 {
            return "\(prefix)，跳过 \(skipped) 个不可解码时间点"
        }
        return prefix
    }
}
