import AVFoundation
import AVKit
import SwiftUI

/// A narrow AppKit bridge used because SwiftUI's VideoPlayer crashes while
/// constructing its representable metadata on the current macOS/Swift toolchain.
struct NativeVideoPlayer: NSViewRepresentable {
    let url: URL
    let seekRequest: PlaybackRequest?

    func makeCoordinator() -> Coordinator {
        Coordinator(url: url)
    }

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .floating
        view.videoGravity = .resizeAspect
        view.showsFullScreenToggleButton = true
        view.player = context.coordinator.player
        return view
    }

    func updateNSView(_ nsView: AVPlayerView, context: Context) {
        if context.coordinator.url != url {
            context.coordinator.replace(with: url)
            nsView.player = context.coordinator.player
        }
        context.coordinator.apply(seekRequest)
    }

    static func dismantleNSView(_ nsView: AVPlayerView, coordinator: Coordinator) {
        coordinator.player.pause()
        nsView.player = nil
    }

    final class Coordinator {
        private(set) var url: URL
        private(set) var player: AVPlayer
        private var lastSeekRequestID: UUID?

        init(url: URL) {
            self.url = url
            self.player = AVPlayer(url: url)
        }

        func replace(with url: URL) {
            player.pause()
            self.url = url
            player = AVPlayer(url: url)
            lastSeekRequestID = nil
        }

        func apply(_ request: PlaybackRequest?) {
            guard let request, request.id != lastSeekRequestID else { return }
            lastSeekRequestID = request.id
            let target = CMTime(seconds: request.seconds, preferredTimescale: 600)
            player.seek(to: target, toleranceBefore: .zero, toleranceAfter: .zero) { [weak player] _ in
                player?.play()
            }
        }
    }
}
