use tauri::AppHandle;

use super::{AppState, ServiceStatus, now_rfc3339, open_browser, try_op};
use crate::error::{Error, Result};
use crate::gmail::{self, api, oauth};
use crate::model::{GmailAccount, TopicView, VaultData};
use crate::secrets::{self, GMAIL_REFRESH_TOKEN};

const SERVICE: &str = "Gmail";

impl AppState {
    fn google(&self) -> Result<&oauth::OAuthClient> {
        self.google.as_ref().ok_or(Error::NotConfigured {
            service: SERVICE,
            var: "SILENTDESK_GOOGLE_CLIENT_ID",
            doc: "gmail",
        })
    }
}

async fn refresh_token() -> Result<Option<String>> {
    Ok(secrets::get(GMAIL_REFRESH_TOKEN)
        .await?
        .and_then(|bytes| String::from_utf8(bytes).ok()))
}

async fn status(state: &AppState) -> Result<ServiceStatus> {
    let account = state.read().await?.gmail_account.map(|a| a.email);
    let connected = account.is_some() && refresh_token().await?.is_some();
    Ok(ServiceStatus {
        configured: state.google.is_some(),
        connected,
        account,
    })
}

#[tauri::command]
pub async fn gmail_status(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    status(&state).await
}

/// Signs in through the system browser and stores the refresh token in the
/// OS keychain. Switching to a different account drops the old account's
/// local data.
#[tauri::command]
pub async fn gmail_connect(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<ServiceStatus> {
    let client = state.google()?;
    let _op = try_op(&state.gmail_op, SERVICE)?;

    let tokens = oauth::authorize(&state.http, client, open_browser(&app)).await?;
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
    status(&state).await
}

/// Pulls the most recent messages and maps each one to a topic. Only runs
/// when the user asks for it (core principle 6).
#[tauri::command]
pub async fn gmail_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let client = state.google()?;
    let _op = try_op(&state.gmail_op, SERVICE)?;

    if state.read().await?.gmail_account.is_none() {
        return Err(Error::NotConnected(SERVICE));
    }
    let refresh = refresh_token().await?.ok_or(Error::NotConnected(SERVICE))?;
    let access = match oauth::access_token(&state.http, client, &refresh).await {
        Err(Error::Reauthorize(service)) => {
            // The grant is dead. Forget it, but keep local topics so that
            // reconnecting the same account picks up where it left off.
            secrets::delete(GMAIL_REFRESH_TOKEN).await?;
            return Err(Error::Reauthorize(service));
        }
        other => other?,
    };
    let latest = api::recent_messages(&state.http, &access, gmail::SYNC_COUNT).await?;
    let now = now_rfc3339();

    state
        .update(|data| {
            gmail::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

/// Revokes the grant at Google, deletes the token and all local Gmail data.
#[tauri::command]
pub async fn gmail_disconnect(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    let _op = try_op(&state.gmail_op, SERVICE)?;
    if let Some(token) = refresh_token().await? {
        oauth::revoke(&state.http, &token).await;
    }
    secrets::delete(GMAIL_REFRESH_TOKEN).await?;
    state.update(VaultData::clear_gmail).await?;
    status(&state).await
}
