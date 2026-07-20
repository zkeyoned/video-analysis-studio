import Foundation

struct VideoInfo: Codable, Sendable {
    let path: String
    let duration: Double
    let width: Int
    let height: Int
    let fps: Double
    let codec: String
    let hasAudio: Bool
    let sizeBytes: Int
}

struct FrameItem: Codable, Identifiable, Hashable, Sendable {
    let index: Int
    let timestamp: Double
    let timecode: String
    let path: String

    var id: String { path }
    var fileURL: URL { URL(fileURLWithPath: path) }
}

struct SamplingInfo: Codable, Sendable {
    let strategy: String?
    let requestedFrameCount: Int?
    let intervalSeconds: Double
    let sceneThreshold: Double
    let sceneChangesDetected: Int
    let guidanceRequestCount: Int?
    let frameCount: Int
    let skippedUndecodableFrames: Int?
    let maxFrames: Int
}

struct PlaybackRequest: Equatable, Sendable {
    let id: UUID
    let seconds: Double

    init(seconds: Double) {
        id = UUID()
        self.seconds = max(0, seconds)
    }
}

struct TranscriptCue: Identifiable, Sendable {
    let start: Double
    let end: Double
    let text: String

    var id: String { "\(start)-\(end)-\(text)" }
    var timecode: String { Formatters.duration(start) }
}

struct SourceMetadata: Codable, Sendable, Hashable {
    let title: String?
    let sourceURL: String?
    let sourceID: String?
    let author: String?
    let description: String?
    let thumbnail: String?
    let extractor: String?
}

struct ImportedVideo: Codable, Sendable {
    let path: String
    let title: String
    let sourceURL: String
    let sourceID: String
    let author: String
    let description: String
    let duration: Double
    let thumbnail: String
    let extractor: String
    let metadataPath: String
}

struct ManifestEnvelope: Codable, Sendable {
    let sessionDir: String
    let video: VideoInfo
    let source: SourceMetadata?
    let sampling: SamplingInfo
    let sceneTimestamps: [Double]
    let frames: [FrameItem]
}

struct TimelineEvent: Codable, Identifiable, Sendable {
    let timecode: String
    let event: String
    let evidence: String

    var id: String { "\(timecode)-\(event)" }
}

struct AnalysisResult: Codable, Sendable {
    let summary: String
    let answer: String
    let timeline: [TimelineEvent]
    let keywords: [KeywordItem]?
    let peopleObjectsPlaces: [String]
    let visibleText: [VisibleText]
    let uncertainties: [String]
    let recommendedFollowups: [String]
}

struct KeywordItem: Codable, Identifiable, Sendable {
    let timecode: String?
    let term: String
    let source: String?
    let context: String?

    var id: String { "\(timecode ?? "")-\(term)" }
}

struct VisibleText: Codable, Identifiable, Sendable {
    let timecode: String
    let text: String

    var id: String { "\(timecode)-\(text)" }
}

struct AnalysisEnvelope: Codable, Sendable {
    let sessionDir: String
    let question: String
    let provider: String
    let model: String
    let video: VideoInfo
    let source: SourceMetadata?
    let sampling: SamplingInfo
    let analysisMode: String?
    let transcript: String
    let result: AnalysisResult
}

struct SessionSummary: Identifiable, Hashable, Sendable {
    let directory: URL
    let title: String
    let date: Date
    let frameCount: Int
    let hasAnalysis: Bool
    let summary: String
    let keywords: [String]
    let author: String
    let sourceURL: String
    let searchIndex: String

    var id: String { directory.path }

    func matches(_ query: String) -> Bool {
        let value = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return true }
        let haystack = ([title, summary, author, sourceURL, searchIndex] + keywords)
            .joined(separator: " ")
        return haystack.localizedCaseInsensitiveContains(value)
    }
}

enum WorkspaceSelection: Hashable {
    case newAnalysis
    case session(String)
}

extension JSONDecoder {
    static var videoAgent: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
