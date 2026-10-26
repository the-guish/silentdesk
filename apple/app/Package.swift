// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SilentDeskApp",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../core"),
    ],
    targets: [
        // What the windows show and do, without SwiftUI, so it builds and is
        // tested on Linux too.
        .target(
            name: "SilentDeskAppModel",
            dependencies: [.product(name: "SilentDeskCore", package: "core")]
        ),
        .testTarget(name: "SilentDeskAppModelTests", dependencies: ["SilentDeskAppModel"]),
    ]
)

#if os(macOS)
// The SwiftUI app. Scripts/bundle.sh wraps it in SilentDesk.app. Not named
// SilentDesk: macOS's file system ignores case, so its build folder would be
// the core's `silentdesk` command line's.
package.products = [.executable(name: "SilentDeskMac", targets: ["SilentDeskMac"])]
package.targets.append(
    .executableTarget(
        name: "SilentDeskMac",
        dependencies: ["SilentDeskAppModel", .product(name: "SilentDeskCore", package: "core")]
    )
)
#endif
