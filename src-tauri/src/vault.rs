//! Encrypted local store (core principle 1).
//!
//! The whole `VaultData` is serialized to JSON and sealed with
//! XChaCha20-Poly1305 under a random 256-bit key kept in the OS credential
//! store. File layout: `MAGIC (4) || nonce (24) || ciphertext+tag`. The magic
//! is bound as associated data, so a file from another format version fails
//! to open instead of being misread.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use chacha20poly1305::aead::{Aead, Generate, KeyInit, Payload};
use chacha20poly1305::{Key, XChaCha20Poly1305, XNonce};

use crate::error::{Error, Result};
use crate::model::VaultData;
use crate::secrets;

const MAGIC: &[u8; 4] = b"SDV1";
const NONCE_LEN: usize = 24;
const KEY_LEN: usize = 32;

pub struct Vault {
    path: PathBuf,
    cipher: XChaCha20Poly1305,
}

impl Vault {
    pub fn new(path: PathBuf, key: &[u8]) -> Result<Self> {
        let key = Key::try_from(key)
            .map_err(|_| Error::Vault("vault key has the wrong length".into()))?;
        Ok(Self {
            path,
            cipher: XChaCha20Poly1305::new(&key),
        })
    }

    /// Opens the vault at `path` with the key from the credential store,
    /// creating a key on first run. Refuses to create a new key when an
    /// encrypted file already exists, so data is never silently replaced.
    pub async fn open(path: PathBuf) -> Result<Self> {
        let key = match secrets::get(secrets::VAULT_KEY).await? {
            Some(key) => key,
            None if path.exists() => {
                return Err(Error::Vault(format!(
                    "the key for {} is missing from the system keychain, so it cannot be read. \
                     Delete that file to start over.",
                    path.display()
                )));
            }
            None => {
                let key = secrets::random_bytes::<KEY_LEN>().to_vec();
                secrets::set(secrets::VAULT_KEY, key.clone()).await?;
                key
            }
        };
        Self::new(path, &key)
    }

    pub fn load(&self) -> Result<VaultData> {
        let bytes = match fs::read(&self.path) {
            Ok(bytes) => bytes,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(VaultData::default()),
            Err(e) => return Err(e.into()),
        };
        let plaintext = self.decrypt(&bytes)?;
        serde_json::from_slice(&plaintext).map_err(|e| Error::Vault(e.to_string()))
    }

    pub fn save(&self, data: &VaultData) -> Result<()> {
        let plaintext = serde_json::to_vec(data).map_err(|e| Error::Vault(e.to_string()))?;
        write_atomic(&self.path, &self.encrypt(&plaintext)?)
    }

    fn encrypt(&self, plaintext: &[u8]) -> Result<Vec<u8>> {
        let nonce = XNonce::generate();
        let ciphertext = self
            .cipher
            .encrypt(
                &nonce,
                Payload {
                    msg: plaintext,
                    aad: MAGIC,
                },
            )
            .map_err(|_| Error::Vault("encryption failed".into()))?;
        let mut out = Vec::with_capacity(MAGIC.len() + NONCE_LEN + ciphertext.len());
        out.extend_from_slice(MAGIC);
        out.extend_from_slice(&nonce);
        out.extend_from_slice(&ciphertext);
        Ok(out)
    }

    fn decrypt(&self, bytes: &[u8]) -> Result<Vec<u8>> {
        let rest = bytes
            .strip_prefix(MAGIC.as_slice())
            .filter(|rest| rest.len() >= NONCE_LEN)
            .ok_or_else(|| Error::Vault("not a SilentDesk vault file".into()))?;
        let (nonce, ciphertext) = rest.split_at(NONCE_LEN);
        let nonce = XNonce::try_from(nonce).expect("nonce slice has the right length");
        self.cipher
            .decrypt(
                &nonce,
                Payload {
                    msg: ciphertext,
                    aad: MAGIC,
                },
            )
            .map_err(|_| {
                Error::Vault("the vault file is corrupted or was encrypted with another key".into())
            })
    }
}

/// Writes to a temporary file and renames it over the target, so a crash
/// never leaves a half-written vault. On Unix the file is readable by the
/// owner only.
fn write_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = path.with_extension("tmp");
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&tmp)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    drop(file);
    fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{GmailAccount, Topic};

    fn temp_path(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("silentdesk-test-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&dir).unwrap();
        dir.join(name)
    }

    fn sample() -> VaultData {
        VaultData {
            gmail_account: Some(GmailAccount {
                email: "me@example.com".into(),
            }),
            topics: vec![Topic {
                id: "t1".into(),
                title: "Quarterly report".into(),
                created_at: "2026-10-23T10:00:00Z".into(),
            }],
            gmail_messages: vec![],
        }
    }

    #[test]
    fn round_trip() {
        let path = temp_path("vault.bin");
        let vault = Vault::new(path.clone(), &[7u8; KEY_LEN]).unwrap();
        assert_eq!(vault.load().unwrap(), VaultData::default());
        vault.save(&sample()).unwrap();
        assert_eq!(vault.load().unwrap(), sample());
    }

    #[test]
    fn file_does_not_contain_plaintext() {
        let path = temp_path("vault.bin");
        let vault = Vault::new(path.clone(), &[7u8; KEY_LEN]).unwrap();
        vault.save(&sample()).unwrap();
        let raw = fs::read(&path).unwrap();
        let needle = b"Quarterly report";
        assert!(!raw.windows(needle.len()).any(|w| w == needle));
    }

    #[test]
    fn wrong_key_is_rejected() {
        let path = temp_path("vault.bin");
        Vault::new(path.clone(), &[7u8; KEY_LEN])
            .unwrap()
            .save(&sample())
            .unwrap();
        let other = Vault::new(path, &[8u8; KEY_LEN]).unwrap();
        assert!(matches!(other.load(), Err(Error::Vault(_))));
    }

    #[test]
    fn tampering_is_detected() {
        let path = temp_path("vault.bin");
        let vault = Vault::new(path.clone(), &[7u8; KEY_LEN]).unwrap();
        vault.save(&sample()).unwrap();
        let mut raw = fs::read(&path).unwrap();
        let last = raw.len() - 1;
        raw[last] ^= 1;
        fs::write(&path, raw).unwrap();
        assert!(matches!(vault.load(), Err(Error::Vault(_))));
    }

    #[cfg(unix)]
    #[test]
    fn file_is_owner_only() {
        use std::os::unix::fs::PermissionsExt;
        let path = temp_path("vault.bin");
        Vault::new(path.clone(), &[7u8; KEY_LEN])
            .unwrap()
            .save(&sample())
            .unwrap();
        let mode = fs::metadata(&path).unwrap().permissions().mode();
        assert_eq!(mode & 0o777, 0o600);
    }
}
