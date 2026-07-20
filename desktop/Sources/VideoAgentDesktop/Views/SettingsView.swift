import AppKit
import SwiftUI

struct SettingsView: View {
    @Bindable var settings: SettingsStore

    var body: some View {
        Form {
            Section("视觉模型") {
                Picker("国内接口预设", selection: $settings.providerPreset) {
                    Text("通义千问 Qwen（推荐）").tag("qwen")
                    Text("豆包视觉模型").tag("doubao")
                    Text("智谱 GLM 视觉").tag("zhipu")
                    Text("自定义 OpenAI 兼容").tag("custom")
                    Text("Google Gemini").tag("gemini")
                }
                .onChange(of: settings.providerPreset) { _, _ in
                    settings.applyProviderPreset()
                }
                TextField("API Base URL", text: $settings.baseURL)
                    .textFieldStyle(.roundedBorder)
                TextField(settings.modelFieldLabel, text: $settings.model)
                    .textFieldStyle(.roundedBorder)
                SecureField("API Key", text: $settings.apiKey)
                    .textFieldStyle(.roundedBorder)
                if settings.providerPreset == "qwen" {
                    Text("默认使用 qwen3-vl-flash：适合多张关键帧分析，费用明显低于旧的 qwen-vl-max。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if settings.providerPreset == "doubao" {
                    Text("豆包控制台可能要求填写模型名或你创建的推理接入点 ID。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("听觉模型") {
                Picker("声音处理", selection: $settings.transcriptionProvider) {
                    Text("关闭，只看画面").tag("none")
                    Text("本地 Whisper（免费、不上传）").tag("local_whisper")
                    Text("云端 OpenAI 兼容转写").tag("openai_compatible")
                }
                if settings.transcriptionProvider == "local_whisper" {
                    TextField("本地模型路径", text: $settings.localWhisperModelPath)
                        .textFieldStyle(.roundedBorder)
                    Picker("对白语言", selection: $settings.transcriptionLanguage) {
                        Text("中文").tag("zh")
                        Text("自动检测").tag("auto")
                        Text("英文").tag("en")
                    }
                    TextField("术语提示（可添加人名、产品名和常用词）", text: $settings.transcriptionPrompt, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .lineLimit(2...4)
                    if settings.localWhisperReady {
                        Label("large-v3-turbo 已安装；中文结果会自动转换成简体。", systemImage: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(.green)
                    } else {
                        Text("尚未安装完成。运行一键安装器后会安装 whisper.cpp，并下载约 1.5 GB 的 large-v3-turbo 多语言模型。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Button("在 Finder 中显示一键安装器") {
                        if let root = try? BackendService().projectRoot() {
                            NSWorkspace.shared.activateFileViewerSelecting([
                                root.appendingPathComponent("安装免费听觉模型.command")
                            ])
                        }
                    }
                } else if settings.transcriptionProvider == "openai_compatible" {
                    TextField("转写 Base URL（留空沿用视觉接口）", text: $settings.transcriptionBaseURL)
                        .textFieldStyle(.roundedBorder)
                    TextField("转写模型，例如 whisper-1", text: $settings.transcriptionModel)
                        .textFieldStyle(.roundedBorder)
                    Text("云端转写默认沿用上面的 API Key。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("关闭时不会提取或上传音频，声音中的剧情关键词可能被漏掉。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            HStack {
                Text(settings.saveMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("保存设置") { settings.save() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .formStyle(.grouped)
        .scenePadding()
        .frame(width: 600, height: 650)
    }
}
