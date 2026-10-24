//! Tauri commands called by the frontend. Tokens and keys never cross this
//! boundary: the webview only sees account status and topic data.

pub mod github;
pub mod gmail;
pub mod jira;
pub mod slack;
pub mod tasks;

use std::path::PathBuf;
use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;
use tokio::sync::{Mutex, MutexGuard, OnceCell};

use crate::error::{Error, Result};
use crate::model::{TopicView, VaultData};
use crate::vault::Vault;

pub struct AppState {
    http: reqwest::Client,
    google: Option<crate::gmail::oauth::OAuthClient>,
    slack: Option<crate::slack::oauth::SlackClient>,
    vault_path: PathBuf,
    vault: OnceCell<Vault>,
    /// Serializes load-modify-save cycles on the vault file.
    data_lock: Mutex<()>,
    /// One operation (connect, sync, disconnect) per service at a time.
    gmail_op: Mutex<()>,
    slack_op: Mutex<()>,
    jira_op: Mutex<()>,
    github_op: Mutex<()>,
    tasks_op: Mutex<()>,
}

impl AppState {
    pub fn new(vault_path: PathBuf) -> Result<Self> {
        let http = reqwest::Client::builder()
            .user_agent(concat!("SilentDesk/", env!("CARGO_PKG_VERSION")))
            .https_only(true)
            .timeout(Duration::from_secs(30))
            .build()?;
        Ok(Self {
            http,
            google: crate::gmail::oauth::OAuthClient::from_env(),
            slack: crate::slack::oauth::SlackClient::from_env(),
            vault_path,
            vault: OnceCell::new(),
            data_lock: Mutex::new(()),
            gmail_op: Mutex::new(()),
            slack_op: Mutex::new(()),
            jira_op: Mutex::new(()),
            github_op: Mutex::new(()),
            tasks_op: Mutex::new(()),
        })
    }

    async fn vault(&self) -> Result<&Vault> {
        self.vault
            .get_or_try_init(|| Vault::open(self.vault_path.clone()))
            .await
    }

    async fn read(&self) -> Result<VaultData> {
        let vault = self.vault().await?;
        let _guard = self.data_lock.lock().await;
        vault.load()
    }

    async fn update<T>(&self, f: impl FnOnce(&mut VaultData) -> T) -> Result<T> {
        let vault = self.vault().await?;
        let _guard = self.data_lock.lock().await;
        let mut data = vault.load()?;
        let out = f(&mut data);
        vault.save(&data)?;
        Ok(out)
    }
}

fn try_op<'a>(lock: &'a Mutex<()>, service: &'static str) -> Result<MutexGuard<'a, ()>> {
    lock.try_lock().map_err(|_| Error::Busy(service))
}

fn open_browser(app: &AppHandle) -> impl FnOnce(&str) -> Result<()> + '_ {
    |url| {
        app.opener()
            .open_url(url, None::<&str>)
            .map_err(|_| Error::Auth("could not open your web browser.".into()))
    }
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_default()
}

/// What the UI needs to know about one connected service.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServiceStatus {
    /// The app has the client ID it needs to sign in.
    configured: bool,
    /// A token is stored and an account is known.
    connected: bool,
    /// The account as shown to the user.
    account: Option<String>,
}

#[tauri::command]
pub async fn list_topics(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    Ok(state.read().await?.topic_views())
}
