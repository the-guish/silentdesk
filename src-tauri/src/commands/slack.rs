use tauri::AppHandle;

use super::{AppState, ServiceStatus, now_rfc3339, open_browser, try_op};
use crate::error::{Error, Result};
use crate::model::{SlackAccount, TopicView, VaultData};
use crate::secrets::{self, SLACK_CREDENTIAL};
use crate::slack::{self, api, oauth};

const SERVICE: &str = "Slack";

impl AppState {
    fn slack(&self) -> Result<&oauth::SlackClient> {
        self.slack.as_ref().ok_or(Error::NotConfigured {
            service: SERVICE,
            var: "SILENTDESK_SLACK_CLIENT_ID",
            doc: "slack",
        })
    }
}

async fn load_credential() -> Result<Option<oauth::Credential>> {
    Ok(secrets::get(SLACK_CREDENTIAL)
        .await?
        .and_then(|bytes| serde_json::from_slice(&bytes).ok()))
}

async fn store_credential(credential: &oauth::Credential) -> Result<()> {
    let bytes = serde_json::to_vec(credential).map_err(|e| Error::Keychain(e.to_string()))?;
    secrets::set(SLACK_CREDENTIAL, bytes).await
}

fn account_label(a: &SlackAccount) -> String {
    format!("{} · {}", a.user_name, a.team_name)
}

async fn status(state: &AppState) -> Result<ServiceStatus> {
    let account = state.read().await?.slack_account.map(|a| account_label(&a));
    let connected = account.is_some() && load_credential().await?.is_some();
    Ok(ServiceStatus {
        configured: state.slack.is_some(),
        connected,
        account,
    })
}

/// A credential that is valid now, refreshed and re-stored if it had expired.
/// A dead grant is forgotten so the UI offers to connect again.
async fn fresh_credential(
    state: &AppState,
    client: &oauth::SlackClient,
) -> Result<oauth::Credential> {
    let credential = load_credential()
        .await?
        .ok_or(Error::NotConnected(SERVICE))?;
    if !credential.needs_refresh(oauth::now()) {
        return Ok(credential);
    }
    match oauth::refresh(&state.http, client, &credential).await {
        Ok(fresh) => {
            store_credential(&fresh).await?;
            Ok(fresh)
        }
        Err(Error::Reauthorize(service)) => {
            secrets::delete(SLACK_CREDENTIAL).await?;
            Err(Error::Reauthorize(service))
        }
        Err(e) => Err(e),
    }
}

#[tauri::command]
pub async fn slack_status(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    status(&state).await
}

/// Signs in through the system browser and stores the token in the OS
/// keychain. Switching to a different user or workspace drops the old
/// account's local data.
#[tauri::command]
pub async fn slack_connect(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<ServiceStatus> {
    let client = state.slack()?;
    let _op = try_op(&state.slack_op, SERVICE)?;

    let credential = oauth::authorize(&state.http, client, open_browser(&app)).await?;
    let me = api::identity(&state.http, &credential.access_token).await?;

    if let Some(old) = load_credential().await?
        && old.access_token != credential.access_token
    {
        oauth::revoke(&state.http, &old.access_token).await;
    }
    store_credential(&credential).await?;

    state
        .update(|data| {
            let same_account = data
                .slack_account
                .as_ref()
                .is_some_and(|a| a.user_id == me.user_id && a.team_id == me.team_id);
            if !same_account {
                data.clear_slack();
            }
            data.slack_account = Some(SlackAccount {
                user_id: me.user_id,
                user_name: me.user_name,
                team_id: me.team_id,
                team_name: me.team_name,
            });
        })
        .await?;
    status(&state).await
}

/// Pulls the most recent direct messages and maps each one to a topic. Only
/// runs when the user asks for it (core principle 6).
#[tauri::command]
pub async fn slack_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let client = state.slack()?;
    let _op = try_op(&state.slack_op, SERVICE)?;

    let account = state
        .read()
        .await?
        .slack_account
        .ok_or(Error::NotConnected(SERVICE))?;
    let credential = fresh_credential(&state, client).await?;
    let latest = match api::recent_direct_messages(
        &state.http,
        &credential.access_token,
        &account.user_id,
        slack::SYNC_COUNT,
    )
    .await
    {
        Err(Error::Reauthorize(service)) => {
            secrets::delete(SLACK_CREDENTIAL).await?;
            return Err(Error::Reauthorize(service));
        }
        other => other?,
    };
    let now = now_rfc3339();

    state
        .update(|data| {
            slack::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

/// Revokes the token at Slack, deletes it and all local Slack data.
#[tauri::command]
pub async fn slack_disconnect(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    let _op = try_op(&state.slack_op, SERVICE)?;
    if let Some(mut credential) = load_credential().await? {
        // An expired access token cannot revoke itself; renew it first.
        if credential.needs_refresh(oauth::now())
            && let Some(client) = state.slack.as_ref()
            && let Ok(fresh) = oauth::refresh(&state.http, client, &credential).await
        {
            credential = fresh;
        }
        oauth::revoke(&state.http, &credential.access_token).await;
    }
    secrets::delete(SLACK_CREDENTIAL).await?;
    state.update(VaultData::clear_slack).await?;
    status(&state).await
}
