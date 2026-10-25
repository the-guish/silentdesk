// swift-tools-version: 6.0
import PackageDescription

let applePlatforms: [Platform] = [.macOS, .iOS, .macCatalyst, .tvOS, .watchOS, .visionOS]

let package = Package(
    name: "SilentDeskCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "SilentDeskCore", targets: ["SilentDeskCore"]),
        .executable(name: "silentdesk", targets: ["silentdesk"]),
    ],
    dependencies: [
        // SQLCipher, as Zetetic ships it for Apple platforms: the database is
        // encrypted at rest (spec/storage.md).
        .package(url: "https://github.com/sqlcipher/SQLCipher.swift.git", from: "4.19.0"),
    ],
    targets: [
        // Zetetic's package holds Apple binaries only. On Linux, where CI and
        // development build this core, the distribution's SQLCipher is used
        // instead: apt install libsqlcipher-dev.
        .systemLibrary(name: "CSQLCipher", pkgConfig: "sqlcipher", providers: [.apt(["libsqlcipher-dev"])]),
        // OpenSSL's hashing for the Linux build; Apple platforms use CryptoKit.
        .systemLibrary(name: "COpenSSL", pkgConfig: "libcrypto", providers: [.apt(["libssl-dev"])]),
        // The core's public API, used by the CLI and the apps.
        .target(
            name: "SilentDeskCore",
            dependencies: [
                .product(name: "SQLCipher", package: "SQLCipher.swift", condition: .when(platforms: applePlatforms)),
                .target(name: "CSQLCipher", condition: .when(platforms: [.linux])),
                .target(name: "COpenSSL", condition: .when(platforms: [.linux])),
            ]
        ),
        // The JSON command line from spec/cli.md, as a library so it can be tested.
        .target(name: "SilentDeskCLI", dependencies: ["SilentDeskCore"]),
        .executableTarget(name: "silentdesk", dependencies: ["SilentDeskCLI"]),
        .testTarget(name: "SilentDeskCoreTests", dependencies: ["SilentDeskCore"]),
        .testTarget(name: "SilentDeskCLITests", dependencies: ["SilentDeskCLI"]),
    ]
)
