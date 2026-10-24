//! What the Python backend may ask of Rust: read and write the local data,
//! save and delete its tokens, open the browser for sign-in, and send events
//! to the UI. Anything else is refused.

use serde::Deserialize;
use serde::de::DeserializeOwned;
use serde_json::{Value, json};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_opener::OpenerExt;

use crate::error::{Error, Result};
use crate::secrets::{self, backend_secret};
use crate::store::Store;

/// Events the backend may send to the UI.
const UI_EVENTS: [&str; 4] = [
    "gmail-sync-progress",
    "sync-finished",
    "sync-round",
    "topics-updated",
];

#[derive(Deserialize)]
struct Write {
    revision: u64,
    data: Value,
}

#[derive(Deserialize)]
struct SetSecret {
    name: String,
    value: String,
}

#[derive(Deserialize)]
struct DeleteSecret {
    name: String,
}

#[derive(Deserialize)]
struct OpenUrl {
    url: String,
}

#[derive(Deserialize)]
struct Emit {
    event: String,
    #[serde(default)]
    payload: Value,
}

fn parse<T: DeserializeOwned>(method: &str, params: Value) -> Result<T> {
    serde_json::from_value(params).map_err(|e| Error::Refused(format!("{method}: {e}")))
}

fn secret_name(name: &str) -> Result<&'static str> {
    backend_secret(name).ok_or_else(|| Error::Refused(format!("unknown secret {name:?}")))
}

pub async fn handle(app: &AppHandle, method: &str, params: Value) -> Result<Value> {
    match method {
        "store.read" => {
            let (revision, data) = app.state::<Store>().read().await?;
            Ok(json!({"revision": revision, "data": data}))
        }
        "store.write" => {
            let Write { revision, data } = parse(method, params)?;
            let revision = app.state::<Store>().write(revision, data).await?;
            Ok(json!({"revision": revision}))
        }
        "secrets.set" => {
            let SetSecret { name, value } = parse(method, params)?;
            secrets::set(secret_name(&name)?, value.into_bytes()).await?;
            Ok(Value::Null)
        }
        "secrets.delete" => {
            let DeleteSecret { name } = parse(method, params)?;
            secrets::delete(secret_name(&name)?).await?;
            Ok(Value::Null)
        }
        "browser.open" => {
            let OpenUrl { url } = parse(method, params)?;
            // Sign-in pages only.
            if !url.starts_with("https://") {
                return Err(Error::Refused("only https pages can be opened".into()));
            }
            app.opener()
                .open_url(url, None::<&str>)
                .map_err(|e| Error::Refused(format!("could not open the browser: {e}")))?;
            Ok(Value::Null)
        }
        _ => Err(Error::Refused(format!("unknown method {method:?}"))),
    }
}

pub fn notify(app: &AppHandle, method: &str, params: Value) {
    let result = match method {
        "emit" => parse::<Emit>(method, params).and_then(|Emit { event, payload }| {
            if !UI_EVENTS.contains(&event.as_str()) {
                return Err(Error::Refused(format!("unknown event {event:?}")));
            }
            let _ = app.emit(&event, payload);
            Ok(())
        }),
        _ => Err(Error::Refused(format!("unknown notification {method:?}"))),
    };
    if let Err(e) = result {
        eprintln!("silentdesk: {e}");
    }
}
