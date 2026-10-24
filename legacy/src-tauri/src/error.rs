use serde::{Serialize, Serializer};

/// Errors returned to the frontend and to the Python backend. Messages must
/// never contain secrets (tokens, keys) or message contents.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// Raised by the Python backend, already worded for the user.
    #[error("{0}")]
    Backend(String),
    #[error("The SilentDesk backend is not running: {0}")]
    BackendDown(String),
    /// A store write raced another one; the writer reads again and retries.
    #[error("the local data changed since it was read")]
    Conflict,
    #[error("The backend sent data that does not match the schema: {0}")]
    Schema(String),
    #[error("The backend sent a request SilentDesk does not accept: {0}")]
    Refused(String),
    #[error("System keychain unavailable: {0}")]
    Keychain(String),
    #[error("Local vault error: {0}")]
    Vault(String),
    #[error("File error: {0}")]
    Io(#[from] std::io::Error),
}

impl Error {
    /// Sent to Python next to the message, so it can tell errors apart.
    pub fn kind(&self) -> &'static str {
        match self {
            Error::Conflict => "conflict",
            _ => "host",
        }
    }
}

impl Serialize for Error {
    fn serialize<S: Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;
