//! SilentDesk's own data model. It is deliberately small: work data stays in
//! the source systems, and SilentDesk keeps only what it needs to link items
//! together. See docs/specs/data-model.md.

use serde::{Deserialize, Serialize};

/// A unit of work the user can act on. Source items (emails today; Slack
/// messages and Jira issues later) each belong to exactly one topic.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Topic {
    pub id: String,
    pub title: String,
    /// RFC 3339.
    pub created_at: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Direction {
    Inbound,
    Outbound,
}

/// A reference to one Gmail message, plus the headers needed to show it in a
/// queue. Bodies are never fetched or stored.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GmailMessage {
    pub message_id: String,
    pub thread_id: String,
    pub topic_id: String,
    pub direction: Direction,
    pub from: String,
    pub to: String,
    pub subject: String,
    /// RFC 3339, from Gmail's internal date.
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GmailAccount {
    pub email: String,
}

/// Everything SilentDesk stores locally. Encrypted at rest by `vault`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct VaultData {
    pub gmail_account: Option<GmailAccount>,
    pub topics: Vec<Topic>,
    pub gmail_messages: Vec<GmailMessage>,
}

impl VaultData {
    /// Drops topics that no source item points to any more.
    pub fn prune_topics(&mut self) {
        let messages = &self.gmail_messages;
        self.topics
            .retain(|t| messages.iter().any(|m| m.topic_id == t.id));
    }

    pub fn clear_gmail(&mut self) {
        self.gmail_account = None;
        self.gmail_messages.clear();
        self.prune_topics();
    }

    /// Topics with their source items, newest first.
    pub fn topic_views(&self) -> Vec<TopicView> {
        let mut views: Vec<TopicView> = self
            .topics
            .iter()
            .map(|t| {
                let mut emails: Vec<GmailMessage> = self
                    .gmail_messages
                    .iter()
                    .filter(|m| m.topic_id == t.id)
                    .cloned()
                    .collect();
                emails.sort_by(|a, b| b.date.cmp(&a.date));
                TopicView {
                    topic: t.clone(),
                    emails,
                }
            })
            .collect();
        views.sort_by(|a, b| latest(b).cmp(latest(a)));
        views
    }
}

fn latest(view: &TopicView) -> &str {
    view.emails
        .first()
        .map_or(view.topic.created_at.as_str(), |m| m.date.as_str())
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TopicView {
    #[serde(flatten)]
    pub topic: Topic,
    pub emails: Vec<GmailMessage>,
}
