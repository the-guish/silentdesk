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

/// A reference to one Jira issue. The description and comments are not
/// kept: the summary becomes the topic title, and the URL opens the issue.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JiraIssue {
    pub issue_id: String,
    pub key: String,
    pub topic_id: String,
    /// Inbound when assigned to the user, outbound when the user reported it
    /// and someone else (or no one) has it.
    pub direction: Direction,
    pub status: String,
    pub project: String,
    pub assignee: String,
    pub reporter: String,
    pub url: String,
    /// RFC 3339, when the issue was last updated.
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JiraAccount {
    pub endpoint: crate::jira::api::Endpoint,
    pub user_id: String,
    pub user_name: String,
}

/// Everything SilentDesk stores locally. Encrypted at rest by `vault`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct VaultData {
    pub topics: Vec<Topic>,
    pub gmail_account: Option<GmailAccount>,
    pub gmail_messages: Vec<GmailMessage>,
    pub slack_account: Option<SlackAccount>,
    pub slack_messages: Vec<SlackMessage>,
    pub jira_account: Option<JiraAccount>,
    pub jira_issues: Vec<JiraIssue>,
}

impl VaultData {
    /// Drops topics that no source item points to any more.
    pub fn prune_topics(&mut self) {
        let (gmail, slack, jira) = (
            &self.gmail_messages,
            &self.slack_messages,
            &self.jira_issues,
        );
        self.topics.retain(|t| {
            gmail.iter().any(|m| m.topic_id == t.id)
                || slack.iter().any(|m| m.topic_id == t.id)
                || jira.iter().any(|i| i.topic_id == t.id)
        });
    }

    pub fn clear_gmail(&mut self) {
        self.gmail_account = None;
        self.gmail_messages.clear();
        self.prune_topics();
    }

    pub fn clear_slack(&mut self) {
        self.slack_account = None;
        self.slack_messages.clear();
        self.prune_topics();
    }

    pub fn clear_jira(&mut self) {
        self.jira_account = None;
        self.jira_issues.clear();
        self.prune_topics();
    }

    /// Topics with their source items, most recent activity first.
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
                let mut slack_messages: Vec<SlackMessage> = self
                    .slack_messages
                    .iter()
                    .filter(|m| m.topic_id == t.id)
                    .cloned()
                    .collect();
                slack_messages.sort_by(|a, b| b.date.cmp(&a.date));
                let mut jira_issues: Vec<JiraIssue> = self
                    .jira_issues
                    .iter()
                    .filter(|i| i.topic_id == t.id)
                    .cloned()
                    .collect();
                jira_issues.sort_by(|a, b| b.date.cmp(&a.date));
                TopicView {
                    topic: t.clone(),
                    emails,
                    slack_messages,
                    jira_issues,
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
    let jira = view.jira_issues.first().map(|i| i.date.as_str());
    email
        .max(slack)
        .max(jira)
        .unwrap_or(view.topic.created_at.as_str())
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TopicView {
    #[serde(flatten)]
    pub topic: Topic,
    pub emails: Vec<GmailMessage>,
    pub slack_messages: Vec<SlackMessage>,
    pub jira_issues: Vec<JiraIssue>,
}
