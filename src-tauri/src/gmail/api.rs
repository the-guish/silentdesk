//! The few Gmail API calls SilentDesk makes. Reads ask for headers only;
//! message bodies are never fetched.

use std::collections::HashSet;
use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE;
use serde::Deserialize;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;
use tokio::task::JoinSet;
use tokio::time::{MissedTickBehavior, interval, sleep};

use crate::error::{Error, Result};
use crate::gmail::reply::Original;
use crate::model::Direction;

const BASE: &str = "https://gmail.googleapis.com/gmail/v1/users/me";

/// Google allows 15,000 quota units per user per minute, and reading one
/// message costs 5: 50 messages a second. Staying at 40 leaves room for
/// other calls.
const READ_PACE: Duration = Duration::from_millis(25);
const MAX_IN_FLIGHT: usize = 20;
/// Waits after a rate-limit or server error: 1, 2, 4, 8 and 16 seconds.
const RETRIES: u32 = 5;

/// Headers and labels for one message, as SilentDesk needs them.
#[derive(Debug, Clone, PartialEq)]
pub struct MessageMeta {
    pub message_id: String,
    pub thread_id: String,
    pub direction: Direction,
    pub from: String,
    pub to: String,
    pub subject: String,
    pub date: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Profile {
    pub email_address: String,
    /// Marks the mailbox's current state; changes after it can be listed.
    pub history_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct MessageList {
    #[serde(default)]
    messages: Vec<MessageId>,
    next_page_token: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct MessageId {
    id: String,
    #[serde(default)]
    label_ids: Vec<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct HistoryList {
    #[serde(default)]
    history: Vec<HistoryRecord>,
    next_page_token: Option<String>,
    history_id: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct HistoryRecord {
    #[serde(default)]
    messages_added: Vec<HistoryMessage>,
    #[serde(default)]
    labels_added: Vec<HistoryMessage>,
}

#[derive(Deserialize)]
struct HistoryMessage {
    message: MessageId,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct RawMessage {
    id: String,
    thread_id: String,
    #[serde(default)]
    label_ids: Vec<String>,
    internal_date: Option<String>,
    payload: Option<RawPayload>,
}

#[derive(Deserialize)]
struct RawPayload {
    #[serde(default)]
    headers: Vec<RawHeader>,
}

#[derive(Deserialize)]
struct RawHeader {
    name: String,
    value: String,
}

#[derive(Deserialize)]
struct ApiErrorBody {
    error: ApiError,
}

#[derive(Deserialize)]
struct ApiError {
    message: String,
}

async fn get<T: serde::de::DeserializeOwned>(
    http: &reqwest::Client,
    token: &str,
    url: &str,
    query: &[(&str, &str)],
) -> Result<T> {
    let response = send_request(|| http.get(url).bearer_auth(token).query(query)).await?;
    Ok(response.json().await?)
}

async fn post(
    http: &reqwest::Client,
    token: &str,
    url: &str,
    body: &serde_json::Value,
) -> Result<()> {
    send_request(|| http.post(url).bearer_auth(token).json(body)).await?;
    Ok(())
}

/// Sends the request, and sends it again after rate-limit and server errors.
async fn send_request(request: impl Fn() -> reqwest::RequestBuilder) -> Result<reqwest::Response> {
    let mut attempt = 0;
    loop {
        let response = request().send().await?;
        if response.status().is_success() {
            return Ok(response);
        }
        let error = api_error(response).await;
        if attempt < RETRIES && is_transient(&error) {
            sleep(Duration::from_secs(1 << attempt)).await;
            attempt += 1;
            continue;
        }
        return Err(error);
    }
}

fn is_transient(error: &Error) -> bool {
    match error {
        Error::Api {
            status, message, ..
        } => {
            matches!(status, 429 | 500 | 502 | 503 | 504)
                || (*status == 403 && message.to_lowercase().contains("rate limit"))
        }
        _ => false,
    }
}

fn is_not_found(error: &Error) -> bool {
    matches!(error, Error::Api { status: 404, .. })
}

async fn api_error(response: reqwest::Response) -> Error {
    let status = response.status();
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Error::Reauthorize("Gmail");
    }
    let message = response
        .json::<ApiErrorBody>()
        .await
        .map(|b| b.error.message)
        .unwrap_or_else(|_| status.canonical_reason().unwrap_or("unknown error").into());
    // Accounts connected before trash and reply existed lack the scopes.
    if status == reqwest::StatusCode::FORBIDDEN
        && message.contains("insufficient authentication scopes")
    {
        return Error::MissingPermission("Gmail");
    }
    Error::Api {
        service: "Gmail",
        status: status.as_u16(),
        message,
    }
}

pub async fn profile(http: &reqwest::Client, token: &str) -> Result<Profile> {
    get(http, token, &format!("{BASE}/profile"), &[]).await
}

/// The IDs of every message in the Inbox, newest first.
pub async fn inbox_ids(http: &reqwest::Client, token: &str) -> Result<Vec<String>> {
    let mut ids = Vec::new();
    let mut page: Option<String> = None;
    loop {
        let mut query = vec![("labelIds", "INBOX"), ("maxResults", "500")];
        if let Some(next) = &page {
            query.push(("pageToken", next));
        }
        let list: MessageList = get(http, token, &format!("{BASE}/messages"), &query).await?;
        ids.extend(list.messages.into_iter().map(|m| m.id));
        match list.next_page_token {
            Some(next) => page = Some(next),
            None => return Ok(ids),
        }
    }
}

/// Messages that entered the Inbox since `start`, and the history ID to
/// start from next time. `None` when Gmail no longer keeps history that old
/// (about a week); a full listing is needed then.
pub async fn inbox_changes(
    http: &reqwest::Client,
    token: &str,
    start: &str,
) -> Result<Option<(Vec<String>, String)>> {
    let mut history = Vec::new();
    let mut page: Option<String> = None;
    loop {
        let mut query = vec![
            ("startHistoryId", start),
            ("labelId", "INBOX"),
            ("historyTypes", "messageAdded"),
            ("historyTypes", "labelAdded"),
        ];
        if let Some(next) = &page {
            query.push(("pageToken", next));
        }
        let list: HistoryList = match get(http, token, &format!("{BASE}/history"), &query).await {
            Err(e) if is_not_found(&e) => return Ok(None),
            other => other?,
        };
        history.extend(list.history);
        match list.next_page_token {
            Some(next) => page = Some(next),
            None => return Ok(Some((inbox_additions(&history), list.history_id))),
        }
    }
}

fn inbox_additions(history: &[HistoryRecord]) -> Vec<String> {
    let mut seen = HashSet::new();
    history
        .iter()
        .flat_map(|r| r.messages_added.iter().chain(&r.labels_added))
        .map(|h| &h.message)
        .filter(|m| m.label_ids.iter().any(|l| l == "INBOX"))
        .filter(|m| seen.insert(m.id.as_str()))
        .map(|m| m.id.clone())
        .collect()
}

/// Subject, labels and date of each message in `ids`, read in parallel at the
/// pace Google allows. Drafts, chats and messages deleted in the meantime are
/// left out. `progress` gets the number of messages read so far.
pub async fn subjects(
    http: &reqwest::Client,
    token: &str,
    ids: &[String],
    mut progress: impl FnMut(usize),
) -> Result<Vec<MessageMeta>> {
    let mut pace = interval(READ_PACE);
    pace.set_missed_tick_behavior(MissedTickBehavior::Delay);
    let mut pending = ids.iter().filter(|id| is_gmail_id(id));
    let mut tasks = JoinSet::new();
    let mut out = Vec::with_capacity(ids.len());
    let mut done = 0;
    loop {
        while tasks.len() < MAX_IN_FLIGHT {
            let Some(id) = pending.next() else { break };
            pace.tick().await;
            let (http, token) = (http.clone(), token.to_owned());
            let url = format!("{BASE}/messages/{id}");
            tasks.spawn(async move {
                let query = [("format", "metadata"), ("metadataHeaders", "Subject")];
                match get::<RawMessage>(&http, &token, &url, &query).await {
                    Ok(raw) => Ok(to_meta(raw)),
                    Err(e) if is_not_found(&e) => Ok(None),
                    Err(e) => Err(e),
                }
            });
        }
        let Some(joined) = tasks.join_next().await else {
            return Ok(out);
        };
        out.extend(joined.map_err(|e| Error::Io(std::io::Error::other(e)))??);
        done += 1;
        progress(done);
    }
}

/// Moves a message to the trash. Gmail deletes it for good after 30 days.
/// A message that no longer exists counts as trashed.
pub async fn trash(http: &reqwest::Client, token: &str, id: &str) -> Result<()> {
    if !is_gmail_id(id) {
        return Err(Error::UnknownMessage);
    }
    let url = format!("{BASE}/messages/{id}/trash");
    match post(http, token, &url, &serde_json::json!({})).await {
        Err(e) if is_not_found(&e) => Ok(()),
        other => other,
    }
}

/// The headers a reply to message `id` needs.
pub async fn original(http: &reqwest::Client, token: &str, id: &str) -> Result<Original> {
    if !is_gmail_id(id) {
        return Err(Error::UnknownMessage);
    }
    let raw: RawMessage = get(
        http,
        token,
        &format!("{BASE}/messages/{id}"),
        &[
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Reply-To"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Message-ID"),
            ("metadataHeaders", "References"),
        ],
    )
    .await?;
    Ok(to_original(raw))
}

/// Sends `message` (RFC 2822) in the thread `thread_id`.
pub async fn send(
    http: &reqwest::Client,
    token: &str,
    thread_id: &str,
    message: &str,
) -> Result<()> {
    post(
        http,
        token,
        &format!("{BASE}/messages/send"),
        &serde_json::json!({
            "raw": URL_SAFE.encode(message.as_bytes()),
            "threadId": thread_id,
        }),
    )
    .await
}

/// Gmail IDs are hex strings. Checking keeps anything unexpected out of URLs.
fn is_gmail_id(id: &str) -> bool {
    !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric())
}

fn header(raw: &RawMessage, name: &str) -> String {
    raw.payload
        .iter()
        .flat_map(|p| &p.headers)
        .find(|h| h.name.eq_ignore_ascii_case(name))
        .map(|h| h.value.trim().to_owned())
        .unwrap_or_default()
}

fn direction(raw: &RawMessage) -> Direction {
    if raw.label_ids.iter().any(|l| l == "SENT") {
        Direction::Outbound
    } else {
        Direction::Inbound
    }
}

fn to_original(raw: RawMessage) -> Original {
    Original {
        direction: direction(&raw),
        from: header(&raw, "From"),
        to: header(&raw, "To"),
        reply_to: header(&raw, "Reply-To"),
        subject: header(&raw, "Subject"),
        message_id: header(&raw, "Message-ID"),
        references: header(&raw, "References"),
    }
}

fn to_meta(raw: RawMessage) -> Option<MessageMeta> {
    let has = |label: &str| raw.label_ids.iter().any(|l| l == label);
    if has("DRAFT") || has("CHAT") {
        return None;
    }
    let date = raw
        .internal_date
        .as_deref()
        .and_then(|ms| ms.parse::<i128>().ok())
        .and_then(|ms| OffsetDateTime::from_unix_timestamp_nanos(ms * 1_000_000).ok())
        .and_then(|d| d.format(&Rfc3339).ok())?;
    Some(MessageMeta {
        direction: direction(&raw),
        from: header(&raw, "From"),
        to: header(&raw, "To"),
        subject: header(&raw, "Subject"),
        date,
        message_id: raw.id,
        thread_id: raw.thread_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn raw(json: &str) -> RawMessage {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn parses_inbound_message() {
        let meta = to_meta(raw(r#"{
            "id": "18c1", "threadId": "18c0", "labelIds": ["INBOX", "UNREAD"],
            "internalDate": "1761213600000",
            "payload": { "headers": [
                {"name": "From", "value": "Ana Ruiz <ana@example.com>"},
                {"name": "To", "value": "me@example.com"},
                {"name": "subject", "value": " Q4 budget "}
            ]}
        }"#))
        .unwrap();
        assert_eq!(meta.direction, Direction::Inbound);
        assert_eq!(meta.from, "Ana Ruiz <ana@example.com>");
        assert_eq!(meta.subject, "Q4 budget");
        assert_eq!(meta.date, "2025-10-23T10:00:00Z");
        assert_eq!(meta.thread_id, "18c0");
    }

    #[test]
    fn sent_label_means_outbound() {
        let meta = to_meta(raw(
            r#"{"id":"a","threadId":"b","labelIds":["SENT"],"internalDate":"0"}"#,
        ))
        .unwrap();
        assert_eq!(meta.direction, Direction::Outbound);
        assert_eq!(meta.subject, "");
    }

    #[test]
    fn skips_drafts_and_chats() {
        assert!(
            to_meta(raw(
                r#"{"id":"a","threadId":"b","labelIds":["DRAFT"],"internalDate":"0"}"#
            ))
            .is_none()
        );
        assert!(
            to_meta(raw(
                r#"{"id":"a","threadId":"b","labelIds":["CHAT"],"internalDate":"0"}"#
            ))
            .is_none()
        );
    }

    #[test]
    fn reads_reply_headers() {
        let o = to_original(raw(r#"{
            "id": "18c1", "threadId": "18c0", "labelIds": ["INBOX"],
            "payload": { "headers": [
                {"name": "From", "value": "Ana <ana@example.com>"},
                {"name": "Reply-To", "value": "list@example.com"},
                {"name": "Message-Id", "value": "<m1@example.com>"},
                {"name": "References", "value": "<m0@example.com>"}
            ]}
        }"#));
        assert_eq!(o.direction, Direction::Inbound);
        assert_eq!(o.reply_to, "list@example.com");
        assert_eq!(o.message_id, "<m1@example.com>");
        assert_eq!(o.references, "<m0@example.com>");
        assert_eq!(o.subject, "");
    }

    #[test]
    fn inbox_additions_keep_inbox_messages_once() {
        let list: HistoryList = serde_json::from_str(
            r#"{"historyId": "9", "history": [
                {"messagesAdded": [
                    {"message": {"id": "a", "labelIds": ["INBOX", "UNREAD"]}},
                    {"message": {"id": "sent", "labelIds": ["SENT"]}}
                ]},
                {"labelsAdded": [
                    {"message": {"id": "b", "labelIds": ["INBOX"]}, "labelIds": ["INBOX"]},
                    {"message": {"id": "starred", "labelIds": ["STARRED"]}, "labelIds": ["STARRED"]}
                ]},
                {"messagesAdded": [{"message": {"id": "a", "labelIds": ["INBOX"]}}]},
                {}
            ]}"#,
        )
        .unwrap();
        assert_eq!(inbox_additions(&list.history), ["a", "b"]);
    }

    #[test]
    fn transient_errors() {
        let api = |status, message: &str| Error::Api {
            service: "Gmail",
            status,
            message: message.into(),
        };
        for (error, expected) in [
            (api(429, "Too many requests"), true),
            (api(503, "Backend error"), true),
            (api(403, "User-rate limit exceeded"), true),
            (api(403, "Rate Limit Exceeded"), true),
            (api(403, "Forbidden"), false),
            (api(404, "Not Found"), false),
            (api(400, "Invalid"), false),
            (Error::Reauthorize("Gmail"), false),
        ] {
            assert_eq!(is_transient(&error), expected, "{error}");
        }
    }

    #[test]
    fn rejects_unexpected_ids() {
        assert!(is_gmail_id("18c1a2b3"));
        assert!(!is_gmail_id("../profile"));
        assert!(!is_gmail_id(""));
    }
}
