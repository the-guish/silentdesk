// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SilentDeskCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "SilentDeskCore", targets: ["SilentDeskCore"]),
        .executable(name: "silentdesk", targets: ["silentdesk"]),
    ],
    targets: [
        // The core's public API, used by the CLI and the apps.
        .target(name: "SilentDeskCore"),
        // The JSON command line from spec/cli.md, as a library so it can be tested.
        .target(name: "SilentDeskCLI", dependencies: ["SilentDeskCore"]),
        .executableTarget(name: "silentdesk", dependencies: ["SilentDeskCLI"]),
        .testTarget(name: "SilentDeskCoreTests", dependencies: ["SilentDeskCore"]),
        .testTarget(name: "SilentDeskCLITests", dependencies: ["SilentDeskCLI"]),
    ]
)
