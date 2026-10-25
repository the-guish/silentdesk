/// SHA-256, for PKCE code challenges: CryptoKit on Apple platforms, OpenSSL
/// on Linux, so the core carries no cryptography of its own.

import Foundation
#if canImport(CryptoKit)
import CryptoKit
#else
import COpenSSL
#endif

enum Hashing {
    static func sha256(_ data: Data) -> Data {
        #if canImport(CryptoKit)
        return Data(SHA256.hash(data: data))
        #else
        var digest = [UInt8](repeating: 0, count: 64)
        var length: UInt32 = 0
        // A pointer is passed even for empty input, which OpenSSL hashes too.
        let bytes = data.isEmpty ? [0] : [UInt8](data)
        bytes.withUnsafeBufferPointer { buffer in
            _ = EVP_Digest(buffer.baseAddress, data.count, &digest, &length, EVP_sha256(), nil)
        }
        return Data(digest.prefix(Int(length)))
        #endif
    }
}
