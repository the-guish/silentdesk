//! Syncs every connected service at startup, every two minutes, and when
//! the window comes back into focus. It works quietly: results reach the UI
//! as events, never as notifications (core principle 6).

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::{Mutex, Notify};
use tokio::time::sleep;

use super::{AppState, now_rfc3339};
use crate::error::{Error, Result};
use crate::model::TopicView;

const INTERVAL: Duration = Duration::from_secs(120);
/// Focus syncs wait at least this long after the last round started.
const MIN_GAP: Duration = Duration::from_secs(30);

#[derive(Default)]
pub struct AutoSync {
    wake: Notify,
    running: AtomicBool,
    started: Mutex<Option<Instant>>,
    /// RFC 3339, when the last round finished.
    finished: Mutex<Option<String>>,
}

/// Sent as `sync-finished` after each service, automatic or not.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SyncFinished {
    service: &'static str,
    /// `None` on success.
    error: Option<String>,
}

/// Sent as `topics-updated` after each service that synced.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct TopicsUpdated {
    at: String,
}

/// Sent as `sync-round` when a round starts and when it ends.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SyncRound {
    running: bool,
}

/// Runs for the life of the app.
pub async fn run(app: AppHandle) {
    let state = app.state::<AppState>();
    loop {
        *state.auto_sync.started.lock().await = Some(Instant::now());
        set_running(&app, &state, true);
        round(&app, &state).await;
        *state.auto_sync.finished.lock().await = Some(now_rfc3339());
        set_running(&app, &state, false);
        tokio::select! {
            _ = sleep(INTERVAL) => {}
            _ = state.auto_sync.wake.notified() => {}
        }
    }
}

fn set_running(app: &AppHandle, state: &AppState, running: bool) {
    state.auto_sync.running.store(running, Ordering::SeqCst);
    let _ = app.emit("sync-round", SyncRound { running });
}

/// Each connected service in turn. Gmail goes last: its first sync can take
/// minutes.
async fn round(app: &AppHandle, state: &AppState) {
    macro_rules! service {
        ($name:literal, $lock:ident, $sync:expr) => {
            if let Ok(_op) = state.$lock.try_lock() {
                report(app, $name, $sync.await);
            }
        };
    }
    service!("tasks", tasks_op, super::tasks::sync(state));
    service!("github", github_op, super::github::sync(state));
    service!("jira", jira_op, super::jira::sync(state));
    service!("slack", slack_op, super::slack::sync(state));
    service!("gmail", gmail_op, super::gmail::sync(app, state));
}

fn report(app: &AppHandle, service: &'static str, result: Result<Vec<TopicView>>) {
    let error = match result {
        Ok(_) => {
            let at = now_rfc3339();
            let _ = app.emit("topics-updated", TopicsUpdated { at });
            None
        }
        // Nothing to sync.
        Err(Error::NotConnected(_) | Error::NotConfigured { .. }) => return,
        Err(e) => Some(e.to_string()),
    };
    let _ = app.emit("sync-finished", SyncFinished { service, error });
}

/// Asks for a round now, unless one started less than `MIN_GAP` ago.
#[tauri::command]
pub async fn sync_soon(state: tauri::State<'_, AppState>) -> Result<()> {
    let recent = state
        .auto_sync
        .started
        .lock()
        .await
        .is_some_and(|t| t.elapsed() < MIN_GAP);
    if !recent {
        state.auto_sync.wake.notify_one();
    }
    Ok(())
}

/// Starts a round now, unless one is running.
#[tauri::command]
pub async fn refresh(state: tauri::State<'_, AppState>) -> Result<()> {
    if !state.auto_sync.running.load(Ordering::SeqCst) {
        state.auto_sync.wake.notify_one();
    }
    Ok(())
}

/// Whether a round is running now.
#[tauri::command]
pub async fn sync_running(state: tauri::State<'_, AppState>) -> Result<bool> {
    Ok(state.auto_sync.running.load(Ordering::SeqCst))
}

/// When the last automatic round finished, if one has.
#[tauri::command]
pub async fn last_synced(state: tauri::State<'_, AppState>) -> Result<Option<String>> {
    Ok(state.auto_sync.finished.lock().await.clone())
}
