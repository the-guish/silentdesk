/// The OS credential store: the Keychain on Apple platforms. On Linux the
/// Python core, with Secret Service, is the one that ships; this core runs
/// there with the test keyring only.

import Foundation

#if canImport(Security)
import Security

final class KeychainKeyring: Keyring {
    /// The service name every secret is kept under, as in legacy.
    static let defaultService = "com.silentdesk.app"

    private let service: String

    /// Tests pass their own `service`, so their items stay apart from the app's.
    init(service: String = KeychainKeyring.defaultService) {
        self.service = service
    }

    /// The item's identity: one generic password per entry name. The login
    /// keychain is used, not the data-protection keychain, which needs a
    /// signed app: the command line and development builds would fail on it.
    /// The app can move the entries once its signing is settled.
    private func query(_ name: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
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

    /// Saved by delete-then-add, so there is no update path to get wrong. The
    /// item stays on this device, is never synchronised, and carries a label
    /// and description the user can recognise in Keychain Access, as
    /// docs/secure-macos-apps.md recommends.
    func set(_ name: String, _ value: String) throws {
        try delete(name)
        var attributes = query(name)
        attributes[kSecValueData as String] = Data(value.utf8)
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        attributes[kSecAttrSynchronizable as String] = false
        attributes[kSecAttrLabel as String] = "SilentDesk: \(name)"
        attributes[kSecAttrDescription as String] = "SilentDesk secret"
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else {
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
