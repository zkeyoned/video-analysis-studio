@preconcurrency import Foundation

enum BackendError: LocalizedError {
    case projectNotFound
    case uvNotFound
    case commandFailed(String)
    case invalidOutput(String)

    var errorDescription: String? {
        switch self {
        case .projectNotFound:
            return "找不到 video-agent 后端目录。"
        case .uvNotFound:
            return "找不到 uv，请先安装 uv。"
        case .commandFailed(let message):
            return message
        case .invalidOutput(let message):
            return "后端输出无法解析：\(message)"
        }
    }
}

final class BackendService: @unchecked Sendable {
    func projectRoot() throws -> URL {
        try locateProjectRoot()
    }

    func run(
        arguments: [String],
        environment: [String: String]
    ) async throws -> Data {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let result = try self.runSync(arguments: arguments, environment: environment)
                    continuation.resume(returning: result)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func runSync(arguments: [String], environment: [String: String]) throws -> Data {
        let project = try locateProjectRoot()
        let uv = try locateUV()
        let process = Process()
        let stdout = Pipe()
        let stderr = Pipe()
        process.executableURL = uv
        process.arguments = ["--directory", project.path, "run", "video-agent"] + arguments
        process.environment = environment
        process.standardOutput = stdout
        process.standardError = stderr
        try process.run()
        process.waitUntilExit()
        let output = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        guard process.terminationStatus == 0 else {
            let detail = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            throw BackendError.commandFailed(detail?.isEmpty == false ? detail! : "视频处理失败。")
        }
        guard !output.isEmpty else {
            throw BackendError.invalidOutput("返回内容为空")
        }
        return output
    }

    private func locateUV() throws -> URL {
        for path in ["/opt/homebrew/bin/uv", "/usr/local/bin/uv"] where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        throw BackendError.uvNotFound
    }

    private func locateProjectRoot() throws -> URL {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let environmentPath = ProcessInfo.processInfo.environment["VIDEO_AGENT_PROJECT_ROOT"],
           !environmentPath.isEmpty {
            candidates.append(URL(fileURLWithPath: environmentPath))
        }
        if let bundledPath = Bundle.main.object(forInfoDictionaryKey: "VideoAgentProjectRoot") as? String,
           !bundledPath.isEmpty {
            candidates.append(URL(fileURLWithPath: bundledPath))
        }
        candidates.append(URL(fileURLWithPath: fm.currentDirectoryPath))
        var cursor = Bundle.main.bundleURL
        for _ in 0..<6 {
            candidates.append(cursor)
            cursor.deleteLastPathComponent()
        }
        for candidate in candidates {
            let direct = candidate.appendingPathComponent("pyproject.toml")
            if fm.fileExists(atPath: direct.path), candidate.lastPathComponent == "video-agent" {
                return candidate
            }
            let nested = candidate.appendingPathComponent("video-agent")
            if fm.fileExists(atPath: nested.appendingPathComponent("pyproject.toml").path) {
                return nested
            }
        }
        throw BackendError.projectNotFound
    }
}
