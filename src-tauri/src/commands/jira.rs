use super::{AppState, ServiceStatus, now_rfc3339, try_op};
use crate::error::{Error, Result};
use crate::jira::{self, api};
use crate::model::{JiraAccount, TopicView, VaultData};
use crate::secrets::{self, JIRA_CREDENTIAL};

const SERVICE: &str = "Jira";

async fn load_credential() -> Result<Option<api::Credential>> {
    Ok(secrets::get(JIRA_CREDENTIAL)
        .await?
        .and_then(|bytes| serde_json::from_slice(&bytes).ok()))
}

async fn status(state: &AppState) -> Result<ServiceStatus> {
    let account = state
        .read()
        .await?
        .jira_account
        .map(|a| format!("{} · {}", a.user_name, site_label(&a.endpoint.site)));
    let connected = account.is_some() && load_credential().await?.is_some();
    Ok(ServiceStatus {
        // Jira needs no app registration: the user brings a token.
        configured: true,
        connected,
        account,
    })
}

fn site_label(site: &str) -> &str {
    site.trim_start_matches("https://")
}

#[tauri::command]
pub async fn jira_status(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    status(&state).await
}

/// Checks the token against the site and stores it in the OS keychain.
/// `email` is set for Jira Cloud and empty for a Data Center personal access
/// token. Switching to a different user or site drops the old account's
/// local data.
#[tauri::command]
pub async fn jira_connect(
    state: tauri::State<'_, AppState>,
    site: String,
    email: Option<String>,
    token: String,
) -> Result<ServiceStatus> {
    let _op = try_op(&state.jira_op, SERVICE)?;

    let site = api::normalize_site(&site)?;
    let token = token.trim().to_owned();
    if token.is_empty() {
        return Err(Error::Auth("enter an API token.".into()));
    }
    let credential = api::Credential {
        email: email.map(|e| e.trim().to_owned()).filter(|e| !e.is_empty()),
        token,
    };
    let (endpoint, me) = api::connect(&state.http, &site, &credential).await?;

    let bytes = serde_json::to_vec(&credential).map_err(|e| Error::Keychain(e.to_string()))?;
    secrets::set(JIRA_CREDENTIAL, bytes).await?;

    state
        .update(|data| {
            let same_account = data
                .jira_account
                .as_ref()
                .is_some_and(|a| a.user_id == me.id && a.endpoint.site == endpoint.site);
            if !same_account {
                data.clear_jira();
            }
            data.jira_account = Some(JiraAccount {
                endpoint,
                user_id: me.id,
                user_name: me.name,
            });
        })
        .await?;
    status(&state).await
}

/// Pulls the most recently updated open issues and maps each one to a
/// topic. Only runs when the user asks for it (core principle 6).
#[tauri::command]
pub async fn jira_sync(state: tauri::State<'_, AppState>) -> Result<Vec<TopicView>> {
    let _op = try_op(&state.jira_op, SERVICE)?;

    let account = state
        .read()
        .await?
        .jira_account
        .ok_or(Error::NotConnected(SERVICE))?;
    let credential = load_credential()
        .await?
        .ok_or(Error::NotConnected(SERVICE))?;
    let latest = match api::open_issues(
        &state.http,
        &credential,
        &account.endpoint,
        &account.user_id,
        jira::SYNC_COUNT,
    )
    .await
    {
        Err(Error::Reauthorize(service)) => {
            // Expired or revoked token. Forget it, keep the topics.
            secrets::delete(JIRA_CREDENTIAL).await?;
            return Err(Error::Reauthorize(service));
        }
        other => other?,
    };
    let now = now_rfc3339();

    state
        .update(|data| {
            jira::apply_sync(data, latest, &now);
            data.topic_views()
        })
        .await
}

/// Deletes the token and all local Jira data. API tokens cannot be revoked
/// through the API; the user revokes them in their Atlassian or Jira profile.
#[tauri::command]
pub async fn jira_disconnect(state: tauri::State<'_, AppState>) -> Result<ServiceStatus> {
    let _op = try_op(&state.jira_op, SERVICE)?;
    secrets::delete(JIRA_CREDENTIAL).await?;
    state.update(VaultData::clear_jira).await?;
    status(&state).await
}
