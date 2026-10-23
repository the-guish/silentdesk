use serde::{Serialize, Serializer};

/// Errors returned to the frontend. Messages must never contain secrets
/// (tokens, keys) or message contents.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("Gmail is not set up. Set SILENTDESK_GOOGLE_CLIENT_ID (see docs/setup/gmail.md).")]
    NotConfigured,
    #[error("Gmail is not connected.")]
    NotConnected,
    #[error("Gmail access was revoked or has expired. Connect again.")]
    Reauthorize,
    #[error("Another Gmail operation is already running.")]
    Busy,
    #[error("Sign-in timed out. Try again.")]
    AuthTimeout,
    #[error("Sign-in failed: {0}")]
    Auth(String),
    #[error("Network error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("Gmail API error ({status}): {message}")]
    Api { status: u16, message: String },
    #[error("System keychain unavailable: {0}")]
    Keychain(String),
    #[error("Local vault error: {0}")]
    Vault(String),
    #[error("File error: {0}")]
    Io(#[from] std::io::Error),
}

impl Serialize for Error {
    fn serialize<S: Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;
