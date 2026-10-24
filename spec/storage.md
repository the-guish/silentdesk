# SilentDesk — Storage

Status: not decided · Last updated: 2026-10-24

Both cores will keep local data in SQLite, with the same schema, so either core can open a database the other wrote. Migrations will live in `spec/sql/` as numbered `.sql` files, which both cores run in order.

No table exists yet. One decision comes first.

## Open decision: encryption at rest

Core principle 1 ([legacy/docs/specs/core.md](../legacy/docs/specs/core.md)) requires all local data to be encrypted at rest, and plain SQLite is not. The legacy app meets it with one encrypted JSON document ([legacy/docs/specs/data-model.md](../legacy/docs/specs/data-model.md#the-vault)).

| Option | Python | Swift | Trade-off |
|--------|--------|-------|-----------|
| **SQLCipher**: the whole database file is encrypted | `sqlcipher3` | SQLCipher C library | Encrypts everything, indexes included, and queries work as usual. Adds a native dependency to both cores; the system SQLite can no longer be used. |
| **Encrypt values**: sensitive columns hold ciphertext | `cryptography` | CryptoKit on Apple, swift-crypto elsewhere | Keeps the system SQLite. Table structure and row counts stay visible, and encrypted columns cannot be searched or sorted. |
| **Keep the vault**: one encrypted JSON document, as in legacy | `cryptography` | CryptoKit | Proven and simple, but every write rewrites the whole document. No SQLite. |

In every option the key is a random 256-bit key kept in the OS credential store (Secret Service on Linux, Keychain on Apple), as in legacy.
