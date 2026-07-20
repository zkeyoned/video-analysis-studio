import Foundation
import Observation

@MainActor
@Observable
final class SettingsStore {
    var providerPreset: String
    var provider: String
    var baseURL: String
    var model: String
    var apiKey: String
    var transcriptionProvider: String
    var transcriptionModel: String
    var transcriptionBaseURL: String
    var localWhisperModelPath: String
    var transcriptionLanguage: String
    var transcriptionPrompt: String
    var saveMessage = ""

    private let defaults = UserDefaults.standard

    init() {
        let storedProvider = defaults.string(forKey: "provider") ?? "openai_compatible"
        let storedBaseURL = defaults.string(forKey: "baseURL") ?? "https://dashscope.aliyuncs.com/compatible-mode/v1"
        let storedModel = defaults.string(forKey: "model")
        let resolvedPreset = defaults.string(forKey: "providerPreset")
            ?? Self.inferPreset(provider: storedProvider, baseURL: storedBaseURL)
        provider = storedProvider
        baseURL = storedBaseURL
        providerPreset = resolvedPreset
        // qwen-vl-max was the old app default. Move that default to the much
        // cheaper current multi-image model; saving Settings persists it.
        if resolvedPreset == "qwen",
           storedModel == nil || storedModel == "qwen-vl-max" {
            model = "qwen3-vl-flash"
        } else {
            model = storedModel ?? "qwen3-vl-flash"
        }
        transcriptionProvider = defaults.string(forKey: "transcriptionProvider") ?? "none"
        transcriptionModel = defaults.string(forKey: "transcriptionModel") ?? ""
        transcriptionBaseURL = defaults.string(forKey: "transcriptionBaseURL") ?? ""
        let storedWhisperModelPath = defaults.string(forKey: "localWhisperModelPath")
        let usesOldWhisperModel = storedWhisperModelPath.map {
            URL(fileURLWithPath: $0).lastPathComponent == "ggml-small.bin"
        } ?? true
        if usesOldWhisperModel {
            localWhisperModelPath = "models/ggml-large-v3-turbo.bin"
        } else {
            localWhisperModelPath = storedWhisperModelPath!
        }
        transcriptionLanguage = defaults.string(forKey: "transcriptionLanguage") ?? "zh"
        transcriptionPrompt = defaults.string(forKey: "transcriptionPrompt")
            ?? "教程、收藏夹、抖音、私信、下载视频、爬取视频、飞书表格、Codex、GitHub、AI、API、关键词。"
        apiKey = KeychainService.readAPIKey()
    }

    func applyProviderPreset() {
        switch providerPreset {
        case "qwen":
            provider = "openai_compatible"
            baseURL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            model = "qwen3-vl-flash"
        case "doubao":
            provider = "openai_compatible"
            baseURL = "https://ark.cn-beijing.volces.com/api/v3"
            model = ""
        case "zhipu":
            provider = "openai_compatible"
            baseURL = "https://open.bigmodel.cn/api/paas/v4"
            model = "glm-4.5v"
        case "gemini":
            provider = "gemini"
            baseURL = "https://generativelanguage.googleapis.com/v1beta"
            model = "gemini-2.5-flash"
        default:
            provider = "openai_compatible"
            if baseURL.contains("generativelanguage.googleapis.com") || baseURL.isEmpty {
                baseURL = "https://api.openai.com/v1"
            }
        }
    }

    private static func inferPreset(provider: String, baseURL: String) -> String {
        if provider == "gemini" { return "gemini" }
        if baseURL.contains("dashscope.aliyuncs.com") { return "qwen" }
        if baseURL.contains("volces.com") { return "doubao" }
        if baseURL.contains("bigmodel.cn") { return "zhipu" }
        return "custom"
    }

    var modelFieldLabel: String {
        providerPreset == "doubao" ? "模型名称或推理接入点 ID" : "模型名称"
    }

    var providerDisplayName: String {
        switch providerPreset {
        case "qwen": return "通义千问"
        case "doubao": return "豆包"
        case "zhipu": return "智谱 GLM"
        case "gemini": return "Gemini"
        default: return "自定义接口"
        }
    }

    var transcriptionDisplayName: String {
        switch transcriptionProvider {
        case "local_whisper":
            return localWhisperReady
                ? "本地 Whisper（已安装）"
                : "本地 Whisper（未安装）"
        case "openai_compatible": return "云端转写"
        default: return "未启用听觉"
        }
    }

    var localWhisperReady: Bool {
        let fm = FileManager.default
        let executableReady = [
            "/opt/homebrew/bin/whisper-cli",
            "/usr/local/bin/whisper-cli",
        ].contains { fm.isExecutableFile(atPath: $0) }
        let rawPath = localWhisperModelPath.trimmingCharacters(in: .whitespacesAndNewlines)
        let modelURL: URL
        if NSString(string: rawPath).isAbsolutePath {
            modelURL = URL(fileURLWithPath: rawPath)
        } else if let root = try? BackendService().projectRoot() {
            modelURL = root.appendingPathComponent(rawPath)
        } else {
            return false
        }
        guard executableReady && fm.fileExists(atPath: modelURL.path) else {
            return false
        }
        if modelURL.lastPathComponent == "ggml-large-v3-turbo.bin" {
            let attributes = try? fm.attributesOfItem(atPath: modelURL.path)
            let bytes = (attributes?[.size] as? NSNumber)?.int64Value ?? 0
            return bytes == 1_624_555_275
        }
        return true
    }

    func save() {
        defaults.set(providerPreset, forKey: "providerPreset")
        defaults.set(provider, forKey: "provider")
        defaults.set(baseURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "baseURL")
        defaults.set(model.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "model")
        defaults.set(transcriptionProvider, forKey: "transcriptionProvider")
        defaults.set(transcriptionModel.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "transcriptionModel")
        defaults.set(transcriptionBaseURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "transcriptionBaseURL")
        defaults.set(localWhisperModelPath.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "localWhisperModelPath")
        defaults.set(transcriptionLanguage, forKey: "transcriptionLanguage")
        defaults.set(transcriptionPrompt.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "transcriptionPrompt")
        do {
            try KeychainService.saveAPIKey(apiKey.trimmingCharacters(in: .whitespacesAndNewlines))
            saveMessage = "设置已保存，API Key 存储在 macOS 钥匙串中。"
        } catch {
            saveMessage = "保存 API Key 失败：\(error.localizedDescription)"
        }
    }

    var processEnvironment: [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        environment["VIDEO_AGENT_PROVIDER"] = provider
        environment["VIDEO_AGENT_BASE_URL"] = baseURL
        environment["VIDEO_AGENT_VISION_MODEL"] = model
        environment["VIDEO_AGENT_API_KEY"] = apiKey
        environment["VIDEO_AGENT_TRANSCRIPTION_PROVIDER"] = transcriptionProvider
        environment["VIDEO_AGENT_TRANSCRIPTION_MODEL"] = transcriptionModel
        environment["VIDEO_AGENT_TRANSCRIPTION_BASE_URL"] = transcriptionBaseURL
        environment["VIDEO_AGENT_LOCAL_WHISPER_MODEL"] = localWhisperModelPath
        environment["VIDEO_AGENT_TRANSCRIPTION_LANGUAGE"] = transcriptionLanguage
        environment["VIDEO_AGENT_TRANSCRIPTION_PROMPT"] = transcriptionPrompt
        return environment
    }
}
