//! The local data, as the Python backend sees it: one document, read and
//! written whole. Rust owns it. Every write is checked against the schemas
//! in `model` and against the revision it was read at, so a writer that
//! read stale data must read again instead of overwriting newer changes.

use std::path::PathBuf;

use serde_json::Value;
use tokio::sync::{Mutex, OnceCell};

use crate::error::{Error, Result};
use crate::model::VaultData;
use crate::vault::Vault;

pub struct Store {
    path: PathBuf,
    vault: OnceCell<Vault>,
    /// Counts successful writes since the app started. Also serializes
    /// load-modify-save cycles on the vault file.
    revision: Mutex<u64>,
}

impl Store {
    pub fn new(path: PathBuf) -> Self {
        Self {
            path,
            vault: OnceCell::new(),
            revision: Mutex::new(0),
        }
    }

    #[cfg(test)]
    fn with_vault(vault: Vault) -> Self {
        Self {
            path: PathBuf::new(),
            vault: OnceCell::new_with(Some(vault)),
            revision: Mutex::new(0),
        }
    }

    async fn vault(&self) -> Result<&Vault> {
        self.vault
            .get_or_try_init(|| Vault::open(self.path.clone()))
            .await
    }

    pub async fn read(&self) -> Result<(u64, VaultData)> {
        let vault = self.vault().await?;
        let revision = self.revision.lock().await;
        Ok((*revision, vault.load()?))
    }

    /// Saves `data` if nothing was written since `revision`, and returns the
    /// new revision. `data` must match `VaultData` exactly: no unknown or
    /// missing fields, no wrong types.
    pub async fn write(&self, revision: u64, data: Value) -> Result<u64> {
        let typed = check_schema(data)?;
        let vault = self.vault().await?;
        let mut current = self.revision.lock().await;
        if *current != revision {
            return Err(Error::Conflict);
        }
        vault.save(&typed)?;
        *current += 1;
        Ok(*current)
    }
}

/// Parses `data` as `VaultData` and checks that nothing was lost or added
/// on the way: serde alone would ignore unknown fields and fill in missing
/// ones.
fn check_schema(data: Value) -> Result<VaultData> {
    let typed: VaultData =
        serde_json::from_value(data.clone()).map_err(|e| Error::Schema(e.to_string()))?;
    let again = serde_json::to_value(&typed).map_err(|e| Error::Schema(e.to_string()))?;
    match first_difference(&data, &again, "data") {
        None => Ok(typed),
        Some(path) => Err(Error::Schema(format!(
            "{path} is missing, unknown or malformed"
        ))),
    }
}

/// The path of the first place where `a` and `b` differ.
fn first_difference(a: &Value, b: &Value, path: &str) -> Option<String> {
    match (a, b) {
        (Value::Object(a), Value::Object(b)) => {
            let keys = a.keys().chain(b.keys().filter(|k| !a.contains_key(*k)));
            for key in keys {
                let here = format!("{path}.{key}");
                match (a.get(key), b.get(key)) {
                    (Some(x), Some(y)) => {
                        if let Some(diff) = first_difference(x, y, &here) {
                            return Some(diff);
                        }
                    }
                    _ => return Some(here),
                }
            }
            None
        }
        (Value::Array(a), Value::Array(b)) => {
            if a.len() != b.len() {
                return Some(path.to_owned());
            }
            a.iter()
                .zip(b)
                .enumerate()
                .find_map(|(i, (x, y))| first_difference(x, y, &format!("{path}[{i}]")))
        }
        _ => (a != b).then(|| path.to_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn store() -> (Store, PathBuf) {
        let id = u64::from_le_bytes(crate::secrets::random_bytes::<8>());
        let path = std::env::temp_dir().join(format!("silentdesk-store-{id}.bin"));
        let vault = Vault::new(path.clone(), &[7u8; 32]).unwrap();
        (Store::with_vault(vault), path)
    }

    fn full() -> Value {
        serde_json::to_value(VaultData::default()).unwrap()
    }

    #[tokio::test]
    async fn write_then_read() {
        let (store, path) = store();
        let mut data = full();
        data["topics"] =
            json!([{"id": "t", "title": "Hello", "createdAt": "2026-01-01T00:00:00Z"}]);
        assert_eq!(store.write(0, data).await.unwrap(), 1);
        let (revision, read) = store.read().await.unwrap();
        assert_eq!(revision, 1);
        assert_eq!(read.topics[0].title, "Hello");
        let _ = std::fs::remove_file(path);
    }

    #[tokio::test]
    async fn stale_revision_is_a_conflict() {
        let (store, path) = store();
        store.write(0, full()).await.unwrap();
        assert!(matches!(store.write(0, full()).await, Err(Error::Conflict)));
        let _ = std::fs::remove_file(path);
    }

    #[tokio::test]
    async fn unknown_missing_and_mistyped_fields_are_refused() {
        let (store, _) = store();

        let mut unknown = full();
        unknown["passwords"] = json!([]);
        let err = store.write(0, unknown).await.unwrap_err().to_string();
        assert!(err.contains("data.passwords"), "{err}");

        let mut missing = full();
        missing.as_object_mut().unwrap().remove("gmailHistoryId");
        let err = store.write(0, missing).await.unwrap_err().to_string();
        assert!(err.contains("data.gmailHistoryId"), "{err}");

        let mut nested = full();
        nested["topics"] = json!([{"id": "t", "title": "x", "createdAt": "d", "extra": 1}]);
        let err = store.write(0, nested).await.unwrap_err().to_string();
        assert!(err.contains("data.topics[0].extra"), "{err}");

        let mut mistyped = full();
        mistyped["topics"] = json!("not a list");
        assert!(matches!(
            store.write(0, mistyped).await,
            Err(Error::Schema(_))
        ));
    }
}
