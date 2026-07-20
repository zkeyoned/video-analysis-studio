import SwiftUI

struct SidebarView: View {
    @Bindable var store: AppStore

    var body: some View {
        List(selection: $store.selection) {
            Section("工作台") {
                Label("新建分析", systemImage: "sparkles.rectangle.stack")
                    .tag(WorkspaceSelection.newAnalysis)
            }

            if !store.recentSessions.isEmpty {
                Section("视频知识库") {
                    ForEach(store.filteredSessions) { session in
                        HStack(spacing: 10) {
                            Image(systemName: session.hasAnalysis ? "text.viewfinder" : "photo.stack")
                                .foregroundStyle(session.hasAnalysis ? Color.accentColor : Color.secondary)
                                .frame(width: 16)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(session.title)
                                    .lineLimit(1)
                                Text(session.summary.isEmpty
                                     ? "\(session.frameCount) 帧 · \(Formatters.sessionDate(session.date))"
                                     : session.summary)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        .tag(WorkspaceSelection.session(session.id))
                    }
                    if store.filteredSessions.isEmpty {
                        Text("没有匹配的视频")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("视频分析台")
        .searchable(text: $store.searchText, prompt: "搜索标题、摘要或关键词")
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: 8) {
                Circle()
                    .fill(store.isBusy ? Color.orange : Color.green)
                    .frame(width: 7, height: 7)
                Text(store.statusMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
            }
            .padding(12)
            .background(.bar)
        }
        .onChange(of: store.selection) { _, selection in
            guard let selection else { return }
            switch selection {
            case .newAnalysis:
                if store.sessionDirectory != nil { store.newAnalysis() }
            case .session(let id):
                if let session = store.recentSessions.first(where: { $0.id == id }) {
                    store.loadSession(session)
                }
            }
        }
    }
}
