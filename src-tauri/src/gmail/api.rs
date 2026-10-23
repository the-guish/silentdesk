//! The few Gmail API calls SilentDesk makes. All of them work with the
//! `gmail.metadata` scope.

use serde::Deserialize;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;

use crate::error::{Error, Result};
use crate::model::Direction;

const BASE: &str = "https://gmail.googleapis.com/gmail/v1/users/me";

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
struct Profile {
    email_address: String,
}

#[derive(Deserialize)]
struct MessageList {
    #[serde(default)]
    messages: Vec<MessageId>,
}

#[derive(Deserialize)]
struct MessageId {
    id: String,
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
    let response = http.get(url).bearer_auth(token).query(query).send().await?;
    let status = response.status();
    if status.is_success() {
        return Ok(response.json().await?);
    }
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(Error::Reauthorize("Gmail"));
    }
    let message = response
        .json::<ApiErrorBody>()
        .await
        .map(|b| b.error.message)
        .unwrap_or_else(|_| status.canonical_reason().unwrap_or("unknown error").into());
    Err(Error::Api {
        service: "Gmail",
        status: status.as_u16(),
        message,
    })
}

pub async fn profile_email(http: &reqwest::Client, token: &str) -> Result<String> {
    let profile: Profile = get(http, token, &format!("{BASE}/profile"), &[]).await?;
    Ok(profile.email_address)
}

/// The `count` most recent sent or received messages, newest first. Drafts
/// and chat messages are skipped.
pub async fn recent_messages(
    http: &reqwest::Client,
    token: &str,
    count: usize,
) -> Result<Vec<MessageMeta>> {
    // Ask for a few extra so skipped drafts don't leave the list short.
    let page_size = (count * 2).to_string();
    let list: MessageList = get(
        http,
        token,
        &format!("{BASE}/messages"),
        &[("maxResults", page_size.as_str())],
    )
    .await?;

    let mut out = Vec::with_capacity(count);
    for MessageId { id } in list.messages {
        if out.len() == count {
            break;
        }
        if !is_gmail_id(&id) {
            continue;
        }
        let raw: RawMessage = get(
            http,
            token,
            &format!("{BASE}/messages/{id}"),
            &[
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "To"),
                ("metadataHeaders", "Subject"),
            ],
        )
        .await?;
        if let Some(meta) = to_meta(raw) {
            out.push(meta);
        }
    }
    Ok(out)
}

/// Gmail IDs are hex strings. Checking keeps anything unexpected out of URLs.
fn is_gmail_id(id: &str) -> bool {
    !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric())
}

fn to_meta(raw: RawMessage) -> Option<MessageMeta> {
    let has = |label: &str| raw.label_ids.iter().any(|l| l == label);
    if has("DRAFT") || has("CHAT") {
        return None;
    }
    let headers = raw.payload.map(|p| p.headers).unwrap_or_default();
    let header = |name: &str| {
        headers
            .iter()
            .find(|h| h.name.eq_ignore_ascii_case(name))
            .map(|h| h.value.trim().to_owned())
            .unwrap_or_default()
    };
    let date = raw
        .internal_date
        .and_then(|ms| ms.parse::<i128>().ok())
        .and_then(|ms| OffsetDateTime::from_unix_timestamp_nanos(ms * 1_000_000).ok())
        .and_then(|d| d.format(&Rfc3339).ok())?;
    Some(MessageMeta {
        direction: if has("SENT") {
            Direction::Outbound
        } else {
            Direction::Inbound
        },
        from: header("From"),
        to: header("To"),
        subject: header("Subject"),
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
    fn rejects_unexpected_ids() {
        assert!(is_gmail_id("18c1a2b3"));
        assert!(!is_gmail_id("../profile"));
        assert!(!is_gmail_id(""));
    }
}
