import AppKit
import SwiftUI

struct LinkImportView: View {
    @Bindable var store: AppStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: "link.badge.plus")
                    .font(.system(size: 28))
                    .foregroundStyle(.tint)
                    .frame(width: 48, height: 48)
                    .background(.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 4) {
                    Text("从视频链接加入知识库")
                        .font(.title2.weight(.semibold))
                    Text("支持抖音及其他 yt-dlp 可识别的视频链接。下载后会自动抽取代表帧。")
                        .foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("视频链接")
                    .font(.headline)
                HStack {
                    TextField("https://v.douyin.com/…", text: $store.videoLink)
                        .textFieldStyle(.roundedBorder)
                    Button("粘贴") {
                        if let value = NSPasteboard.general.string(forType: .string) {
                            store.videoLink = value
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Picker("读取登录状态", selection: $store.browserCookieSource) {
                    Text("不读取（先尝试公开链接）").tag("none")
                    Text("Safari").tag("safari")
                    Text("Chrome").tag("chrome")
                    Text("Firefox").tag("firefox")
                    Text("Microsoft Edge").tag("edge")
                }
                Text("若抖音提示需要新 Cookie，请先在所选浏览器登录。登录状态仅由本机下载器读取，不会写入分析报告。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Toggle(
                store.isNarrationMode
                    ? "下载后自动听声音并开始 AI 分析"
                    : "下载并抽帧后自动开始 AI 分析",
                isOn: $store.analyzeAfterLinkImport
            )
                .disabled(
                    store.settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || (store.isNarrationMode && !store.canUseNarrationMode)
                )
            if store.settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text("尚未配置视觉 API Key，因此本次会完成下载和抽帧，但不会自动调用模型。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if store.isNarrationMode && !store.canUseNarrationMode {
                Text("当前是讲解优先模式。请先在设置中启用本地 Whisper 或云端转写；本次仍可下载并抽取普通关键帧。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack {
                Button("取消") { dismiss() }
                Spacer()
                Button("下载并加入知识库") { store.importVideoLink() }
                    .buttonStyle(.borderedProminent)
                    .disabled(store.videoLink.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(24)
        .frame(width: 560)
    }
}
