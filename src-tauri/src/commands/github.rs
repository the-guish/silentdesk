use super::{AppState, ServiceStatus, now_rfc3339};
use crate::error::{Error, Result};
use crate::github::{self, api};
use crate::model::{GitHubAccount, TopicView, VaultData};
use crate::secrets::{self, GITHUB_TOKEN};

const SERVICE: &str = "GitHub";

async fn load_token() -> Result<Option<String>> {
    Ok(secrets::get(GITHUB_TOKEN)
        .await?
        .and_then(|bytes| String::from_utf8(bytes).ok()))
}

async fn status(state: &AppState) -> Result<ServiceStatus> {
    let account = state
        .read()
        .await?
        .github_account
        .map(|a| format!("{} · {}", a.login, a.endpoint.host()));
    let connected = account.is_some() && load_token().await?.is_some();
    Ok(ServiceStatus {
        // GitHub needs no app registration: the user brings a token.
        configured: true,
        connected,
        account,
    })
}

#[tauri::command]
pub async fn github_status(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    status(&state).await
}

/// Checks the token and stores it in the OS keychain. `server` is empty for
/// github.com, or a GitHub Enterprise Server host. Switching to a different
/// user or server drops the old account's local data.
#[tauri::command]
pub async fn github_connect(
    state: tauri::State<'_, AppState>,
    server: Option<String>,
    token: String,
) -> Result<ServiceStatus> {
    let _op = state.github_op.lock().await;

    let endpoint = api::Endpoint::for_server(server.as_deref())?;
    let token = token.trim().to_owned();
    if token.is_empty() {
        return Err(Error::Auth("enter a personal access token.".into()));
    }
    let me = api::connect(&state.http, &endpoint, &token).await?;
    secrets::set(GITHUB_TOKEN, token.into_bytes()).await?;

    state
        .update(|data| {
            let same_account = data
                .github_account
                .as_ref()
                .is_some_and(|a| a.login == me.login && a.endpoint == endpoint);
            if !same_account {
                data.clear_github();
            }
            data.github_account = Some(GitHubAccount {
                endpoint,
                login: me.login,
                name: me.name,
            });
        })
        .await?;
    status(&state).await
}

/// Pulls the open pull requests that involve the user and maps each one to
/// a topic.
pub(super) async fn sync(state: &AppState) -> Result<Vec<TopicView>> {
    let account = state
        .read()
        .await?
        .github_account
        .ok_or(Error::NotConnected(SERVICE))?;
    let token = load_token().await?.ok_or(Error::NotConnected(SERVICE))?;
    let latest = match api::open_pull_requests(&state.http, &account.endpoint, &token).await {
        Err(Error::Reauthorize(service)) => {
            // Expired or revoked token. Forget it, keep the topics.
            secrets::delete(GITHUB_TOKEN).await?;
            return Err(Error::Reauthorize(service));
        }
        other => other?,
    };
    let now = now_rfc3339();

    state
        .update(|data| {
            github::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

#[tauri::command]
pub async fn github_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let _op = state.github_op.lock().await;
    sync(&state).await
}

/// Deletes the token and all local GitHub data. The user revokes the token
/// itself in their GitHub settings.
#[tauri::command]
pub async fn github_disconnect(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    let _op = state.github_op.lock().await;
    secrets::delete(GITHUB_TOKEN).await?;
    state.update(VaultData::clear_github).await?;
    status(&state).await
}
