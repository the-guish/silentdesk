use tauri::AppHandle;

use super::{AppState, ServiceStatus, now_rfc3339, open_browser};
use crate::error::{Error, Result};
use crate::gmail::oauth;
use crate::model::{TasksAccount, TopicView, VaultData};
use crate::secrets::{self, GOOGLE_TASKS_REFRESH_TOKEN};
use crate::tasks::{self, api};

const SERVICE: &str = "Google Tasks";

impl AppState {
    /// Google Tasks signs in with the same Google OAuth client as Gmail, but
    /// with its own read-only grant and refresh token.
    fn google_for_tasks(&self) -> Result<&oauth::OAuthClient> {
        self.google.as_ref().ok_or(Error::NotConfigured {
            service: SERVICE,
            var: "SILENTDESK_GOOGLE_CLIENT_ID",
            doc: "google-tasks",
        })
    }
}

async fn refresh_token() -> Result<Option<String>> {
    Ok(secrets::get(GOOGLE_TASKS_REFRESH_TOKEN)
        .await?
        .and_then(|bytes| String::from_utf8(bytes).ok()))
}

async fn status(state: &AppState) -> Result<ServiceStatus> {
    let account = state.read().await?.tasks_account.map(|a| a.email);
    let connected = account.is_some() && refresh_token().await?.is_some();
    Ok(ServiceStatus {
        configured: state.google.is_some(),
        connected,
        account,
    })
}

#[tauri::command]
pub async fn tasks_status(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    status(&state).await
}

/// Signs in through the system browser for read-only access to Google
/// Tasks, and stores the refresh token in the OS keychain. Switching to a
/// different account drops the old account's local data.
#[tauri::command]
pub async fn tasks_connect(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<ServiceStatus> {
    let client = state.google_for_tasks()?;
    let _op = state.tasks_op.lock().await;

    let tokens = oauth::authorize(&state.http, client, &api::GRANT, open_browser(&app)).await?;
    let email = api::email(&state.http, &tokens.access_token).await?;

    if let Some(old) = refresh_token().await?
        && old != tokens.refresh_token
    {
        oauth::revoke(&state.http, &old).await;
    }
    secrets::set(
        GOOGLE_TASKS_REFRESH_TOKEN,
        tokens.refresh_token.into_bytes(),
    )
    .await?;

    state
        .update(|data| {
            let same_account = data
                .tasks_account
                .as_ref()
                .is_some_and(|a| a.email == email);
            if !same_account {
                data.clear_tasks();
            }
            data.tasks_account = Some(TasksAccount { email });
        })
        .await?;
    status(&state).await
}

/// Pulls every open task and maps each one to a topic.
pub(super) async fn sync(state: &AppState) -> Result<Vec<TopicView>> {
    let client = state.google_for_tasks()?;

    if state.read().await?.tasks_account.is_none() {
        return Err(Error::NotConnected(SERVICE));
    }
    let refresh = refresh_token().await?.ok_or(Error::NotConnected(SERVICE))?;
    let access = match oauth::access_token(&state.http, client, &api::GRANT, &refresh).await {
        Err(Error::Reauthorize(service)) => {
            // The grant is dead. Forget it, keep the topics.
            secrets::delete(GOOGLE_TASKS_REFRESH_TOKEN).await?;
            return Err(Error::Reauthorize(service));
        }
        other => other?,
    };
    let latest = api::open_tasks(&state.http, &access).await?;
    let now = now_rfc3339();

    state
        .update(|data| {
            tasks::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

#[tauri::command]
pub async fn tasks_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let _op = state.tasks_op.lock().await;
    sync(&state).await
}

/// Revokes the grant at Google, deletes the token and all local task data.
#[tauri::command]
pub async fn tasks_disconnect(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    let _op = state.tasks_op.lock().await;
    if let Some(token) = refresh_token().await? {
        oauth::revoke(&state.http, &token).await;
    }
    secrets::delete(GOOGLE_TASKS_REFRESH_TOKEN).await?;
    state.update(VaultData::clear_tasks).await?;
    status(&state).await
}
