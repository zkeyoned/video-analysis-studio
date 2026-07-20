import SwiftUI

struct ContentView: View {
    @Bindable var store: AppStore

    var body: some View {
        NavigationSplitView {
            SidebarView(store: store)
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 320)
        } detail: {
            DetailView(store: store)
        }
        .toolbar {
            ToolbarItemGroup {
                Button {
                    store.chooseVideo()
                } label: {
                    Label("打开视频", systemImage: "plus.rectangle.on.folder")
                }
                .help("打开视频（⌘O）")

                Button {
                    store.isShowingLinkImporter = true
                } label: {
                    Label("导入视频链接", systemImage: "link.badge.plus")
                }
                .help("从抖音等视频链接加入知识库")

                SettingsLink {
                    Label("模型设置", systemImage: "gearshape")
                }
                .help("配置视觉模型和 API Key")
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .chooseVideo)) { _ in
            store.chooseVideo()
        }
        .onReceive(NotificationCenter.default.publisher(for: .startAnalysis)) { _ in
            store.analyze()
        }
        .onReceive(NotificationCenter.default.publisher(for: .importVideoLink)) { _ in
            store.isShowingLinkImporter = true
        }
        .sheet(isPresented: $store.isShowingLinkImporter) {
            LinkImportView(store: store)
        }
    }
}
