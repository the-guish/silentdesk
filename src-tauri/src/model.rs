//! SilentDesk's own data model. It is deliberately small: work data stays in
//! the source systems, and SilentDesk keeps only what it needs to link items
//! together. See docs/specs/data-model.md.

use std::collections::{HashMap, HashSet};

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
/// queue. Bodies are never fetched or stored. Inbox syncs keep the subject
/// only, so `from` and `to` are empty for them.
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

/// A reference to one Slack direct message. The message text is not kept:
/// its first line becomes the topic title, and the permalink opens it in Slack.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SlackMessage {
    pub channel_id: String,
    pub ts: String,
    pub topic_id: String,
    pub direction: Direction,
    pub author: String,
    /// Who the conversation is with: the other person, or "Group DM".
    pub counterpart: String,
    pub permalink: String,
    /// RFC 3339, from the message timestamp.
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SlackAccount {
    pub user_id: String,
    pub user_name: String,
    pub team_id: String,
    pub team_name: String,
}

/// Everything SilentDesk stores locally. Encrypted at rest by `vault`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct VaultData {
    pub topics: Vec<Topic>,
    pub gmail_account: Option<GmailAccount>,
    pub gmail_messages: Vec<GmailMessage>,
    /// Where the next Gmail sync starts listing changes from. `None` until a
    /// full Inbox sync completes.
    pub gmail_history_id: Option<String>,
    pub slack_account: Option<SlackAccount>,
    pub slack_messages: Vec<SlackMessage>,
}

impl VaultData {
    /// Drops topics that no source item points to any more.
    pub fn prune_topics(&mut self) {
        let used: HashSet<&str> = self
            .gmail_messages
            .iter()
            .map(|m| m.topic_id.as_str())
            .chain(self.slack_messages.iter().map(|m| m.topic_id.as_str()))
            .collect();
        self.topics.retain(|t| used.contains(t.id.as_str()));
    }

    pub fn clear_gmail(&mut self) {
        self.gmail_account = None;
        self.gmail_messages.clear();
        self.gmail_history_id = None;
        self.prune_topics();
    }

    pub fn clear_slack(&mut self) {
        self.slack_account = None;
        self.slack_messages.clear();
        self.prune_topics();
    }

    /// Topics with their source items, most recent activity first.
    pub fn topic_views(&self) -> Vec<TopicView> {
        let mut emails_by_topic: HashMap<&str, Vec<GmailMessage>> = HashMap::new();
        for m in &self.gmail_messages {
            emails_by_topic
                .entry(&m.topic_id)
                .or_default()
                .push(m.clone());
        }
        let mut slack_by_topic: HashMap<&str, Vec<SlackMessage>> = HashMap::new();
        for m in &self.slack_messages {
            slack_by_topic
                .entry(&m.topic_id)
                .or_default()
                .push(m.clone());
        }
        let mut views: Vec<TopicView> = self
            .topics
            .iter()
            .map(|t| {
                let mut emails = emails_by_topic.remove(t.id.as_str()).unwrap_or_default();
                emails.sort_by(|a, b| b.date.cmp(&a.date));
                let mut slack_messages = slack_by_topic.remove(t.id.as_str()).unwrap_or_default();
                slack_messages.sort_by(|a, b| b.date.cmp(&a.date));
                TopicView {
                    topic: t.clone(),
                    emails,
                    slack_messages,
                }
            })
            .collect();
        views.sort_by(|a, b| latest(b).cmp(latest(a)));
        views
    }
}

fn latest(view: &TopicView) -> &str {
    let email = view.emails.first().map(|m| m.date.as_str());
    let slack = view.slack_messages.first().map(|m| m.date.as_str());
    email.max(slack).unwrap_or(view.topic.created_at.as_str())
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TopicView {
    #[serde(flatten)]
    pub topic: Topic,
    pub emails: Vec<GmailMessage>,
    pub slack_messages: Vec<SlackMessage>,
}
