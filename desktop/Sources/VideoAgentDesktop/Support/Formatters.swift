import Foundation

enum Formatters {
    static func duration(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "—" }
        let total = Int(seconds.rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let remaining = total % 60
        return hours > 0
            ? String(format: "%d:%02d:%02d", hours, minutes, remaining)
            : String(format: "%d:%02d", minutes, remaining)
    }

    static func fileSize(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    static func sessionDate(_ date: Date) -> String {
        date.formatted(date: .abbreviated, time: .shortened)
    }

    static func timecodeSeconds(_ value: String) -> Double? {
        let parts = value.trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: ":")
            .compactMap { Double($0) }
        guard !parts.isEmpty, parts.count <= 3 else { return nil }
        switch parts.count {
        case 1:
            return max(0, parts[0])
        case 2:
            return max(0, parts[0] * 60 + parts[1])
        default:
            return max(0, parts[0] * 3600 + parts[1] * 60 + parts[2])
        }
    }

    static func transcriptCues(_ transcript: String) -> [TranscriptCue] {
        transcript.split(whereSeparator: \.isNewline).compactMap { rawLine in
            let line = String(rawLine).trimmingCharacters(in: .whitespaces)
            guard line.first == "[",
                  let closing = line.firstIndex(of: "]") else { return nil }
            let range = line[line.index(after: line.startIndex)..<closing]
            let bounds = range.split(separator: "-", maxSplits: 1)
            guard bounds.count == 2,
                  let start = Double(bounds[0]),
                  let end = Double(bounds[1]) else { return nil }
            let textStart = line.index(after: closing)
            let text = line[textStart...].trimmingCharacters(in: .whitespaces)
            guard !text.isEmpty else { return nil }
            return TranscriptCue(start: start, end: end, text: text)
        }
    }
}
