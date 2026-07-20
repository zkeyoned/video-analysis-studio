// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VideoAgentDesktop",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "VideoAgentDesktop", targets: ["VideoAgentDesktop"])
    ],
    targets: [
        .executableTarget(
            name: "VideoAgentDesktop",
            path: "Sources/VideoAgentDesktop"
        ),
        .testTarget(
            name: "VideoAgentDesktopTests",
            dependencies: ["VideoAgentDesktop"]
        )
    ]
)
