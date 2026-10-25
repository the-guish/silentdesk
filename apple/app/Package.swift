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
// The SwiftUI app. Scripts/bundle.sh wraps it in SilentDesk.app.
package.products = [.executable(name: "SilentDesk", targets: ["SilentDesk"])]
package.targets.append(
    .executableTarget(
        name: "SilentDesk",
        dependencies: ["SilentDeskAppModel", .product(name: "SilentDeskCore", package: "core")]
    )
)
#endif
