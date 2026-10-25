# SilentDesk — Storage

Status: decided, not built · Last updated: 2026-10-25

Both cores keep local data in one SQLite database file, with the same schema, so either core can open a database the other wrote. Migrations will live in `spec/sql/` as numbered `.sql` files, which both cores run in order. No table exists yet.

## Encryption at rest: SQLCipher

Core principle 1 ([legacy/docs/specs/core.md](../legacy/docs/specs/core.md)) requires all local data to be encrypted at rest. The database is a [SQLCipher](https://www.zetetic.net/sqlcipher/) file: the whole file is encrypted, indexes included, and queries work as in plain SQLite.

| Core | Library |
|------|---------|
| Python | `sqlcipher3`, whose `sqlcipher3-binary` wheel bundles SQLCipher |
| Swift | SQLCipher's Swift package; the system SQLite cannot be used |

- **Key:** a random 256-bit key, generated on first run and kept in the OS credential store (Secret Service on Linux, Keychain on Apple), as in legacy. It is passed to SQLCipher as a raw key, so no passphrase derivation runs on open.
- **Missing key:** if the key is gone but the database file exists, the core refuses to open it rather than create a new key and lose the data, as in legacy.

### Options that were considered

| Option | Why not |
|--------|---------|
| Encrypt values in plain SQLite | Table structure and row counts stay visible, and encrypted columns cannot be searched or sorted. |
| Keep the legacy vault, one encrypted JSON document | Every write rewrites the whole document, and Apple's CryptoKit lacks its cipher (XChaCha20-Poly1305). |

## Secrets

Secrets are not in the database: they live in the OS credential store, under service `com.silentdesk.app`, one entry each. Both cores use these entry names:

| Entry | Holds |
|-------|-------|
| `database-key` | The database's key |
| `gmail-refresh-token` | Gmail's OAuth refresh token |
| `google-tasks-refresh-token` | Google Tasks' OAuth refresh token |

A service counts as connected when its entry is present. Tests can replace the credential store with a file; see [cli.md](cli.md#test-keyring).
