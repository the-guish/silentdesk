use serde::{Serialize, Serializer};

/// Errors returned to the frontend. Messages must never contain secrets
/// (tokens, keys) or message contents.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{service} is not set up. Set {var} in .env (see docs/setup/{doc}.md).")]
    NotConfigured {
        service: &'static str,
        var: &'static str,
        doc: &'static str,
    },
    #[error("{0} is not connected.")]
    NotConnected(&'static str),
    #[error("{0} access was revoked or has expired. Connect again.")]
    Reauthorize(&'static str),
    #[error("{0} needs new permissions. Disconnect, then connect again.")]
    MissingPermission(&'static str),
    #[error("That email is no longer in SilentDesk. Sync and try again.")]
    UnknownMessage,
    #[error("Write a reply before sending.")]
    EmptyReply,
    #[error("Sign-in timed out. Try again.")]
    AuthTimeout,
    #[error("Sign-in failed: {0}")]
    Auth(String),
    #[error("Network error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("{service} API error ({status}): {message}")]
    Api {
        service: &'static str,
        status: u16,
        message: String,
    },
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
