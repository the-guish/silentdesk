//! Tauri commands called by the frontend. Tokens and keys never cross this
//! boundary: the webview only sees account status and topic data.

use std::path::PathBuf;
use std::time::Duration;

use serde::Serialize;
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;
use tokio::sync::{Mutex, OnceCell};

use crate::error::{Error, Result};
use crate::gmail::{self, api, oauth};
use crate::model::{GmailAccount, TopicView, VaultData};
use crate::secrets::{self, GMAIL_REFRESH_TOKEN};
use crate::vault::Vault;

pub struct AppState {
    http: reqwest::Client,
    oauth: Option<oauth::OAuthClient>,
    vault_path: PathBuf,
    vault: OnceCell<Vault>,
    /// Serializes load-modify-save cycles on the vault file.
    data_lock: Mutex<()>,
    /// One Gmail operation (connect, sync, disconnect) at a time.
    gmail_op: Mutex<()>,
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
            oauth: oauth::OAuthClient::from_env(),
            vault_path,
            vault: OnceCell::new(),
            data_lock: Mutex::new(()),
            gmail_op: Mutex::new(()),
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

    fn oauth_client(&self) -> Result<&oauth::OAuthClient> {
        self.oauth.as_ref().ok_or(Error::NotConfigured)
    }

    fn gmail_op(&self) -> Result<tokio::sync::MutexGuard<'_, ()>> {
        self.gmail_op.try_lock().map_err(|_| Error::Busy)
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GmailStatus {
    /// An OAuth client ID is available.
    configured: bool,
    /// A refresh token is stored and an account is known.
    connected: bool,
    email: Option<String>,
}

async fn refresh_token() -> Result<Option<String>> {
    Ok(secrets::get(GMAIL_REFRESH_TOKEN)
        .await?
        .and_then(|bytes| String::from_utf8(bytes).ok()))
}

async fn current_status(state: &AppState) -> Result<GmailStatus> {
    let email = state.read().await?.gmail_account.map(|a| a.email);
    let connected = email.is_some() && refresh_token().await?.is_some();
    Ok(GmailStatus {
        configured: state.oauth.is_some(),
        connected,
        email,
    })
}

#[tauri::command]
pub async fn gmail_status(state: tauri::State<'_, AppState>) -> Result<GmailStatus> {
    current_status(&state).await
}

/// Signs in through the system browser and stores the refresh token in the
/// OS keychain. Switching to a different account drops the old account's
/// local data.
#[tauri::command]
pub async fn gmail_connect(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<GmailStatus> {
    let client = state.oauth_client()?;
    let _op = state.gmail_op()?;

    let tokens = oauth::authorize(&state.http, client, |url| {
        app.opener()
            .open_url(url, None::<&str>)
            .map_err(|_| Error::Auth("could not open your web browser.".into()))
    })
    .await?;
    let email = api::profile_email(&state.http, &tokens.access_token).await?;

    if let Some(old) = refresh_token().await?
        && old != tokens.refresh_token
    {
        oauth::revoke(&state.http, &old).await;
    }
    secrets::set(GMAIL_REFRESH_TOKEN, tokens.refresh_token.into_bytes()).await?;

    state
        .update(|data| {
            let same_account = data
                .gmail_account
                .as_ref()
                .is_some_and(|a| a.email == email);
            if !same_account {
                data.clear_gmail();
            }
            data.gmail_account = Some(GmailAccount { email });
        })
        .await?;
    current_status(&state).await
}

/// Pulls the most recent messages and maps each one to a topic. Only runs
/// when the user asks for it (core principle 6).
#[tauri::command]
pub async fn gmail_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let client = state.oauth_client()?;
    let _op = state.gmail_op()?;

    if state.read().await?.gmail_account.is_none() {
        return Err(Error::NotConnected);
    }
    let refresh = refresh_token().await?.ok_or(Error::NotConnected)?;
    let access = match oauth::access_token(&state.http, client, &refresh).await {
        Err(Error::Reauthorize) => {
            // The grant is dead. Forget it, but keep local topics so that
            // reconnecting the same account picks up where it left off.
            secrets::delete(GMAIL_REFRESH_TOKEN).await?;
            return Err(Error::Reauthorize);
        }
        other => other?,
    };
    let latest = api::recent_messages(&state.http, &access, gmail::SYNC_COUNT).await?;
    let now = OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_default();

    state
        .update(|data| {
            gmail::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

/// Revokes the grant at Google, deletes the token and all local Gmail data.
#[tauri::command]
pub async fn gmail_disconnect(state: tauri::State<'_, AppState>) -> Result<GmailStatus> {
    let _op = state.gmail_op()?;
    if let Some(token) = refresh_token().await? {
        oauth::revoke(&state.http, &token).await;
    }
    secrets::delete(GMAIL_REFRESH_TOKEN).await?;
    state.update(VaultData::clear_gmail).await?;
    current_status(&state).await
}

#[tauri::command]
pub async fn list_topics(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    Ok(state.read().await?.topic_views())
}
