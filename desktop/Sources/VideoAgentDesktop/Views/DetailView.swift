import AppKit
import SwiftUI

struct DetailView: View {
    @Bindable var store: AppStore

    var body: some View {
        Group {
            if let videoURL = store.selectedVideoURL {
                workspace(videoURL)
            } else {
                emptyState
            }
        }
        .navigationTitle(store.selectedVideoURL?.deletingPathExtension().lastPathComponent ?? "新建分析")
    }

    private var emptyState: some View {
        VStack(spacing: 22) {
            ZStack {
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(.tint.opacity(0.10))
                    .frame(width: 116, height: 116)
                Image(systemName: "sparkles.rectangle.stack")
                    .font(.system(size: 48, weight: .light))
                    .foregroundStyle(.tint)
            }
            VStack(spacing: 8) {
                Text("把收藏的视频变成知识库")
                    .font(.largeTitle.weight(.semibold))
                Text("导入本地视频或粘贴抖音链接，自动听声音、看画面、生成摘要与关键词，以后随时搜索。")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 700)
            }

            HStack(spacing: 12) {
                Button("选择本地视频…") { store.chooseVideo() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut("o")
                Button("粘贴视频链接…") { store.isShowingLinkImporter = true }
                    .buttonStyle(.bordered)
            }
            .controlSize(.large)

            HStack(spacing: 10) {
                FlowBadge(icon: "square.and.arrow.down", title: "导入")
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                FlowBadge(icon: "waveform", title: "听声音")
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                FlowBadge(icon: "photo.stack", title: "看画面")
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                FlowBadge(icon: "text.viewfinder", title: "摘要与关键词")
                Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                FlowBadge(icon: "magnifyingglass", title: "随时搜索")
            }

            if !store.recentSessions.isEmpty {
                Text("知识库已有 \(store.recentSessions.count) 条处理记录，可在左侧搜索。")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                Text("支持 MP4、MOV、AVI，以及 yt-dlp 可识别的视频站点")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
        .dropDestination(for: URL.self) { urls, _ in
            guard let first = urls.first else { return false }
            store.selectVideo(first)
            return true
        }
    }

    private func workspace(_ videoURL: URL) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header(videoURL)
                HStack(alignment: .top, spacing: 18) {
                    NativeVideoPlayer(
                        url: videoURL,
                        seekRequest: store.playbackRequest
                    )
                        .frame(minWidth: 460, minHeight: 260)
                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(.separator.opacity(0.5), lineWidth: 1)
                        }
                    analysisControls
                        .frame(width: 360)
                }

                if store.isBusy {
                    HStack(spacing: 12) {
                        ProgressView()
                            .controlSize(.small)
                        Text(store.statusMessage)
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                }

                if !store.errorMessage.isEmpty {
                    Label(store.errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                }

                if !store.frames.isEmpty {
                    frameGallery
                }

                if let result = store.analysisResult {
                    resultSection(result)
                    if !store.transcript.isEmpty {
                        transcriptSection(store.transcript)
                    }
                } else if !store.report.isEmpty {
                    reportSection(store.report)
                }
            }
            .padding(24)
            .frame(maxWidth: 1240)
            .frame(maxWidth: .infinity)
        }
    }

    private func header(_ videoURL: URL) -> some View {
        HStack(spacing: 14) {
            Image(systemName: "film.stack")
                .font(.system(size: 24))
                .foregroundStyle(.tint)
                .frame(width: 46, height: 46)
                .background(.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 11))
            VStack(alignment: .leading, spacing: 3) {
                Text(videoURL.deletingPathExtension().lastPathComponent)
                    .font(.title2.weight(.semibold))
                    .lineLimit(1)
                if let info = store.videoInfo {
                    Text("\(Formatters.duration(info.duration)) · \(info.width)×\(info.height) · \(String(format: "%.1f", info.fps)) FPS · \(Formatters.fileSize(info.sizeBytes))")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    if let source = store.sourceMetadata {
                        HStack(spacing: 6) {
                            if let author = source.author, !author.isEmpty {
                                Text(author)
                            }
                            if let value = source.sourceURL,
                               let url = URL(string: value) {
                                Button("打开原链接") { NSWorkspace.shared.open(url) }
                                    .buttonStyle(.link)
                            }
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                } else {
                    Text("正在读取视频信息…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button("更换视频") { store.chooseVideo() }
        }
    }

    private var analysisControls: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("分析任务", systemImage: "wand.and.stars")
                .font(.headline)
            Picker("分析方式", selection: $store.analysisMode) {
                Text("讲解优先").tag("narration")
                Text("画面优先").tag("balanced")
            }
            .pickerStyle(.segmented)
            Text(store.isNarrationMode
                 ? "先听完整语音，由 AI 挑选需要看画面的时间，再定向抽帧。"
                 : "先按镜头变化和固定间隔抽帧，再结合同期声音分析。")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextEditor(text: $store.question)
                .font(.body)
                .scrollContentBackground(.hidden)
                .padding(8)
                .frame(height: 92)
                .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 9))

            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    Text(store.isNarrationMode ? "保底画面" : "抽帧间隔")
                    if store.isNarrationMode {
                        Picker("保底画面间隔", selection: $store.coverageInterval) {
                            Text("15 秒").tag(15.0)
                            Text("20 秒").tag(20.0)
                            Text("30 秒").tag(30.0)
                            Text("60 秒").tag(60.0)
                        }
                        .labelsHidden()
                    } else {
                        Picker("抽帧间隔", selection: $store.interval) {
                            Text("3 秒").tag(3.0)
                            Text("6 秒").tag(6.0)
                            Text("10 秒").tag(10.0)
                            Text("15 秒").tag(15.0)
                        }
                        .labelsHidden()
                    }
                }
                GridRow {
                    Text("最多帧数")
                    Stepper("\(store.maxFrames) 帧", value: $store.maxFrames, in: 12...120, step: 12)
                }
            }
            .font(.callout)

            HStack {
                Button("只抽关键帧") { store.prepare() }
                    .buttonStyle(.bordered)
                Button("开始 AI 分析") { store.analyze() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: [.command])
            }
            .disabled(store.isBusy || store.videoInfo == nil)

            if store.settings.apiKey.isEmpty {
                SettingsLink {
                    Label("先配置视觉模型 API Key", systemImage: "key")
                        .font(.caption)
                }
            } else if store.isNarrationMode && !store.canUseNarrationMode {
                SettingsLink {
                    Label("讲解优先需要先启用听觉模型", systemImage: "waveform.badge.exclamationmark")
                        .font(.caption)
                }
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    Label("\(store.settings.providerDisplayName) · \(store.settings.model)", systemImage: "checkmark.shield")
                    Label(store.settings.transcriptionDisplayName, systemImage: "waveform")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var frameGallery: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("关键帧", systemImage: "photo.stack")
                    .font(.title3.weight(.semibold))
                Text("\(store.frames.count) 张")
                    .foregroundStyle(.secondary)
                Spacer()
                if let directory = store.sessionDirectory {
                    Button("在 Finder 中显示") { NSWorkspace.shared.activateFileViewerSelecting([directory]) }
                }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180, maximum: 260), spacing: 12)], spacing: 12) {
                ForEach(store.frames) { frame in
                    FrameCard(frame: frame)
                }
            }
        }
    }

    private func resultSection(_ result: AnalysisResult) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("AI 分析报告", systemImage: "doc.text.magnifyingglass")
                .font(.title2.weight(.semibold))
            Text(result.summary)
                .font(.body)
                .textSelection(.enabled)
            if !result.answer.isEmpty {
                Text(result.answer)
                    .font(.body)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                    .textSelection(.enabled)
            }
            if !result.timeline.isEmpty {
                Text("时间线")
                    .font(.headline)
                ForEach(result.timeline) { event in
                    HStack(alignment: .top, spacing: 12) {
                        Button(event.timecode) { store.seek(to: event.timecode) }
                            .buttonStyle(.link)
                            .font(.system(.callout, design: .monospaced).weight(.medium))
                            .frame(width: 90, alignment: .leading)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(event.event)
                            Text(event.evidence)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if let keywords = result.keywords, !keywords.isEmpty {
                Text("声音与剧情关键词")
                    .font(.headline)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180))], alignment: .leading, spacing: 8) {
                    ForEach(keywords) { keyword in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(keyword.term).fontWeight(.semibold)
                                Spacer()
                                if let timecode = keyword.timecode, !timecode.isEmpty {
                                    Button(timecode) { store.seek(to: timecode) }
                                        .buttonStyle(.link)
                                        .font(.system(.caption, design: .monospaced))
                                }
                            }
                            if let context = keyword.context, !context.isEmpty {
                                Text(context)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(10)
                        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            if !result.peopleObjectsPlaces.isEmpty {
                Text("人物、地点与物品")
                    .font(.headline)
                FlowLayout(items: result.peopleObjectsPlaces)
            }
            if !result.visibleText.isEmpty {
                DisclosureGroup("识别到的画面文字（\(result.visibleText.count)）") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(result.visibleText) { item in
                            HStack(alignment: .top, spacing: 10) {
                                Button(item.timecode) { store.seek(to: item.timecode) }
                                    .buttonStyle(.link)
                                    .font(.system(.callout, design: .monospaced))
                                Text(item.text)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                    .font(.callout)
                    .padding(.top, 8)
                }
            }
            if !result.uncertainties.isEmpty {
                DisclosureGroup("需要复查（\(result.uncertainties.count)）") {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(result.uncertainties, id: \.self) { item in
                            Label(item, systemImage: "questionmark.circle")
                        }
                    }
                    .font(.callout)
                    .padding(.top, 8)
                }
            }
        }
        .padding(20)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
    }

    private func transcriptSection(_ value: String) -> some View {
        let cues = Formatters.transcriptCues(value)
        return DisclosureGroup {
            if cues.isEmpty {
                Text(value)
                    .font(.system(.callout, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 10)
            } else {
                LazyVStack(alignment: .leading, spacing: 9) {
                    ForEach(cues) { cue in
                        HStack(alignment: .top, spacing: 12) {
                            Button(cue.timecode) { store.seek(to: cue.start) }
                                .buttonStyle(.link)
                                .font(.system(.callout, design: .monospaced))
                                .frame(width: 62, alignment: .leading)
                            Text(cue.text)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .padding(.top, 10)
            }
        } label: {
            Label("完整声音转写", systemImage: "waveform.badge.magnifyingglass")
                .font(.title3.weight(.semibold))
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
    }

    private func reportSection(_ value: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("分析报告", systemImage: "doc.text")
                .font(.title2.weight(.semibold))
            Text((try? AttributedString(markdown: value)) ?? AttributedString(value))
                .textSelection(.enabled)
        }
        .padding(20)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
    }
}

private struct FlowBadge: View {
    let icon: String
    let title: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.caption.weight(.medium))
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(.quaternary.opacity(0.7), in: Capsule())
    }
}

private struct FlowLayout: View {
    let items: [String]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 120))], alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.callout)
                    .lineLimit(1)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }
}

private struct FrameCard: View {
    let frame: FrameItem

    var body: some View {
        Button {
            NSWorkspace.shared.open(frame.fileURL)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                if let image = NSImage(contentsOf: frame.fileURL) {
                    Image(nsImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(height: 112)
                        .clipped()
                } else {
                    Rectangle()
                        .fill(.quaternary)
                        .frame(height: 112)
                        .overlay { Image(systemName: "photo") }
                }
                HStack {
                    Text(frame.timecode)
                        .font(.system(.caption, design: .monospaced))
                    Spacer()
                    Image(systemName: "arrow.up.right.square")
                        .foregroundStyle(.tertiary)
                }
                .padding(9)
            }
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(.separator.opacity(0.45), lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
        .help("打开 \(frame.timecode) 关键帧")
    }
}
