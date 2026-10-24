use serde::Serialize;
use tauri::{AppHandle, Emitter};

use super::{AppState, ServiceStatus, now_rfc3339, open_browser, try_op};
use crate::error::{Error, Result};
use crate::gmail::{self, api, oauth};
use crate::model::{GmailAccount, GmailMessage, TopicView, VaultData};
use crate::secrets::{self, GMAIL_REFRESH_TOKEN};

const SERVICE: &str = "Gmail";

/// Messages read between two saves of the vault, so that an interrupted
/// first sync resumes where it stopped. Each batch also gets a fresh access
/// token, which expires after an hour.
const SAVE_EVERY: usize = 500;
/// Progress events are sent every this many messages.
const PROGRESS_EVERY: usize = 25;

/// Sent to the webview as `gmail-sync-progress` while a sync reads messages.
#[derive(Clone, Serialize)]
struct SyncProgress {
    done: usize,
    total: usize,
}

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

/// A fresh access token for the connected account.
async fn access_token(state: &AppState) -> Result<String> {
    let client = state.google()?;
    if state.read().await?.gmail_account.is_none() {
        return Err(Error::NotConnected(SERVICE));
    }
    let refresh = refresh_token().await?.ok_or(Error::NotConnected(SERVICE))?;
    match oauth::access_token(&state.http, client, &oauth::GMAIL, &refresh).await {
        Err(Error::Reauthorize(service)) => {
            // The grant is dead. Forget it, but keep local topics so that
            // reconnecting the same account picks up where it left off.
            secrets::delete(GMAIL_REFRESH_TOKEN).await?;
            Err(Error::Reauthorize(service))
        }
        other => other,
    }
}

/// SilentDesk acts only on emails it has synced.
async fn known_message(state: &AppState, message_id: &str) -> Result<GmailMessage> {
    state
        .read()
        .await?
        .gmail_messages
        .into_iter()
        .find(|m| m.message_id == message_id)
        .ok_or(Error::UnknownMessage)
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

    let tokens = oauth::authorize(&state.http, client, &oauth::GMAIL, open_browser(&app)).await?;
    let email = api::profile(&state.http, &tokens.access_token)
        .await?
        .email_address;

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

/// Pulls the subject of every Inbox message SilentDesk does not have yet,
/// each as a topic of its own. The first sync lists the whole Inbox; later
/// ones list only what entered it since. Messages stay after they leave the
/// Inbox. Only runs when the user asks for it (core principle 6).
#[tauri::command]
pub async fn gmail_sync(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<Vec<TopicView>> {
    state.google()?;
    let _op = try_op(&state.gmail_op, SERVICE)?;
    let access = access_token(&state).await?;
    let data = state.read().await?;

    let changes = match &data.gmail_history_id {
        Some(start) => api::inbox_changes(&state.http, &access, start).await?,
        None => None,
    };
    let (ids, history_id) = match changes {
        Some(changes) => changes,
        None => {
            // Take the marker first, so changes made while listing are
            // picked up next time.
            let history_id = api::profile(&state.http, &access).await?.history_id;
            (api::inbox_ids(&state.http, &access).await?, history_id)
        }
    };
    let ids = gmail::new_ids(&data, ids);
    drop(data);

    let total = ids.len();
    let report = |done: usize| {
        let _ = app.emit("gmail-sync-progress", SyncProgress { done, total });
    };
    report(0);
    for (batch, chunk) in ids.chunks(SAVE_EVERY).enumerate() {
        let access = access_token(&state).await?;
        let offset = batch * SAVE_EVERY;
        let messages = api::subjects(&state.http, &access, chunk, |n| {
            if n % PROGRESS_EVERY == 0 {
                report(offset + n);
            }
        })
        .await?;
        let now = now_rfc3339();
        state
            .update(|data| gmail::add_messages(data, messages, &now))
            .await?;
        report(offset + chunk.len());
    }

    state
        .update(|data| {
            data.gmail_history_id = Some(history_id);
            data.topic_views()
        })
        .await
}

/// Moves an email to the Gmail trash and drops it, with its topic, from
/// SilentDesk.
#[tauri::command]
pub async fn gmail_trash(
    state: tauri::State<'_, AppState>,
    message_id: String,
) -> Result<Vec<TopicView>> {
    let _op = try_op(&state.gmail_op, SERVICE)?;
    known_message(&state, &message_id).await?;
    let access = access_token(&state).await?;
    api::trash(&state.http, &access, &message_id).await?;
    state
        .update(|data| {
            gmail::remove_message(data, &message_id);
            data.topic_views()
        })
        .await
}

/// Sends `body`, typed by the user, as a reply in the email's thread. It
/// appears in SilentDesk at the next sync.
#[tauri::command]
pub async fn gmail_reply(
    state: tauri::State<'_, AppState>,
    message_id: String,
    body: String,
) -> Result<()> {
    if body.trim().is_empty() {
        return Err(Error::EmptyReply);
    }
    let _op = try_op(&state.gmail_op, SERVICE)?;
    let message = known_message(&state, &message_id).await?;
    let access = access_token(&state).await?;
    let original = api::original(&state.http, &access, &message_id).await?;
    let raw = gmail::reply::build(&original, &body);
    api::send(&state.http, &access, &message.thread_id, &raw).await
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
