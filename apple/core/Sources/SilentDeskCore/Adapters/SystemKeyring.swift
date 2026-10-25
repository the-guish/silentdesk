/// The OS credential store: the Keychain on Apple platforms. On Linux the
/// Python core, with Secret Service, is the one that ships; this core runs
/// there with the test keyring only.

import Foundation

#if canImport(Security)
import Security

final class KeychainKeyring: Keyring {
    /// The service name every secret is kept under, as in legacy.
    static let service = "com.silentdesk.app"

    private func query(_ name: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: Self.service,
            kSecAttrAccount as String: name,
        ]
    }

    func get(_ name: String) throws -> String? {
        var query = query(name)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess, let data = item as? Data else {
            throw StorageError("The Keychain could not be read (error \(status)).")
        }
        return String(decoding: data, as: UTF8.self)
    }

    func set(_ name: String, _ value: String) throws {
        let data = Data(value.utf8)
        let status = SecItemUpdate(query(name) as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var attributes = query(name)
            attributes[kSecValueData as String] = data
            let added = SecItemAdd(attributes as CFDictionary, nil)
            guard added == errSecSuccess else { throw StorageError("The Keychain could not be written (error \(added)).") }
        } else if status != errSecSuccess {
            throw StorageError("The Keychain could not be written (error \(status)).")
        }
    }

    func delete(_ name: String) throws {
        let status = SecItemDelete(query(name) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw StorageError("The Keychain could not be changed (error \(status)).")
        }
    }
}

typealias SystemKeyring = KeychainKeyring
#else

/// No credential store is wired on this platform.
final class UnavailableKeyring: Keyring {
    private var unavailable: StorageError {
        StorageError("No credential store is available on this platform. Tests set SILENTDESK_TEST_KEYRING.")
    }

    func get(_ name: String) throws -> String? { throw unavailable }
    func set(_ name: String, _ value: String) throws { throw unavailable }
    func delete(_ name: String) throws { throw unavailable }
}

typealias SystemKeyring = UnavailableKeyring
#endif
