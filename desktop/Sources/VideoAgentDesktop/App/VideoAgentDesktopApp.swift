import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
@MainActor
struct VideoAgentDesktopApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var settings: SettingsStore
    @State private var store: AppStore

    init() {
        let settingsStore = SettingsStore()
        _settings = State(initialValue: settingsStore)
        _store = State(initialValue: AppStore(settings: settingsStore))
    }

    var body: some Scene {
        WindowGroup("视频分析台") {
            ContentView(store: store)
                .environment(settings)
                .frame(minWidth: 1060, minHeight: 720)
        }
        .defaultSize(width: 1280, height: 820)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("打开视频…") {
                    NotificationCenter.default.post(name: .chooseVideo, object: nil)
                }
                .keyboardShortcut("o")
                Button("导入视频链接…") {
                    NotificationCenter.default.post(name: .importVideoLink, object: nil)
                }
                .keyboardShortcut("l", modifiers: [.command, .shift])
            }
            CommandMenu("分析") {
                Button("开始 AI 分析") {
                    NotificationCenter.default.post(name: .startAnalysis, object: nil)
                }
                .keyboardShortcut(.return, modifiers: [.command])
            }
        }

        Settings {
            SettingsView(settings: settings)
        }
    }
}
