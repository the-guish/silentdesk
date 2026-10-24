//! The one command the frontend calls. Every call goes to the Python
//! backend; tokens and keys never cross this boundary, so the webview only
//! sees account status and topic data.

use serde_json::{Value, json};

use crate::backend::Backend;
use crate::error::{Error, Result};

/// Calls `method` (e.g. `jira.sync`, `topics.list`) on the backend with
/// `params` and returns its result.
#[tauri::command]
pub async fn call(
    backend: tauri::State<'_, Backend>,
    method: String,
    params: Option<Value>,
) -> Result<Value> {
    // Startup belongs to Rust.
    if method == "init" {
        return Err(Error::Refused("init".into()));
    }
    backend
        .call(&method, params.unwrap_or_else(|| json!({})))
        .await
}
