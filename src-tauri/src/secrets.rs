//! Secrets live in the operating system's credential store: Keychain on
//! macOS, Credential Manager on Windows, Secret Service on Linux. They are
//! never written to disk by SilentDesk.

use crate::error::{Error, Result};
use keyring::{Entry, Error as KeyringError};

const SERVICE: &str = "com.silentdesk.app";

pub const VAULT_KEY: &str = "vault-key";
pub const GMAIL_REFRESH_TOKEN: &str = "gmail-refresh-token";
pub const SLACK_CREDENTIAL: &str = "slack-credential";
pub const JIRA_CREDENTIAL: &str = "jira-credential";

fn entry(name: &str) -> Result<Entry> {
    Entry::new(SERVICE, name).map_err(|e| Error::Keychain(e.to_string()))
}

/// Calls into the credential store can block (D-Bus, unlock prompts), so
/// they run on the blocking thread pool.
async fn blocking<T: Send + 'static>(f: impl FnOnce() -> Result<T> + Send + 'static) -> Result<T> {
    tokio::task::spawn_blocking(f)
        .await
        .map_err(|e| Error::Keychain(e.to_string()))?
}

pub async fn get(name: &'static str) -> Result<Option<Vec<u8>>> {
    blocking(move || match entry(name)?.get_secret() {
        Ok(secret) => Ok(Some(secret)),
        Err(KeyringError::NoEntry) => Ok(None),
        Err(e) => Err(Error::Keychain(e.to_string())),
    })
    .await
}

pub async fn set(name: &'static str, secret: Vec<u8>) -> Result<()> {
    blocking(move || {
        entry(name)?
            .set_secret(&secret)
            .map_err(|e| Error::Keychain(e.to_string()))
    })
    .await
}

pub async fn delete(name: &'static str) -> Result<()> {
    blocking(move || match entry(name)?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(e) => Err(Error::Keychain(e.to_string())),
    })
    .await
}

pub fn random_bytes<const N: usize>() -> [u8; N] {
    let mut buf = [0u8; N];
    getrandom::fill(&mut buf).expect("operating system random number generator failed");
    buf
}
