//! SilentDesk's own data model. It is deliberately small: work data stays in
//! the source systems, and SilentDesk keeps only what it needs to link items
//! together. See docs/specs/data-model.md.
//!
//! These are the schemas the Python backend writes against: `store` rejects
//! any write that does not match them exactly. The Python mirror lives in
//! `backend/silentdesk/core/model.py`; change both together.

use serde::{Deserialize, Serialize};

/// A unit of work the user can act on. Source items each belong to exactly
/// one topic.
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum Flavor {
    Cloud,
    DataCenter,
}

/// Where and how to call the Jira API, decided once at connect time.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JiraEndpoint {
    /// The site people browse, e.g. `https://acme.atlassian.net`.
    pub site: String,
    /// The site itself, or the Atlassian gateway for scoped Cloud tokens.
    pub api_base: String,
    pub flavor: Flavor,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JiraAccount {
    pub endpoint: JiraEndpoint,
    pub user_id: String,
    pub user_name: String,
}

/// Why a pull request is in the user's queue.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum Reason {
    ReviewRequested,
    Assigned,
    Authored,
}

/// A reference to one GitHub pull request. The description, diff and
/// comments are not kept: the title becomes the topic title, and the URL
/// opens the pull request.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PullRequest {
    pub pr_id: u64,
    /// `owner/name`.
    pub repo: String,
    pub number: u64,
    pub topic_id: String,
    pub reason: Reason,
    /// Inbound when the user's review or work is asked for; outbound when
    /// the user opened it.
    pub direction: Direction,
    pub draft: bool,
    pub author: String,
    pub url: String,
    /// RFC 3339, when the pull request was last updated.
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GitHubEndpoint {
    /// `https://api.github.com` or `https://<host>/api/v3`.
    pub api_base: String,
    /// `https://github.com` or `https://<host>`.
    pub web_base: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GitHubAccount {
    pub endpoint: GitHubEndpoint,
    pub login: String,
    pub name: String,
}

/// A reference to one open Google Task. Notes are not kept: the title
/// becomes the topic title, and the URL opens the task in Google Tasks.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GoogleTask {
    pub task_id: String,
    pub list_id: String,
    pub list_title: String,
    pub topic_id: String,
    /// `YYYY-MM-DD`; Google keeps the day only.
    pub due: Option<String>,
    /// Gmail, Docs or Chat, when the task came from one of them.
    pub origin: Option<String>,
    pub url: String,
    /// RFC 3339, when the task was last updated.
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TasksAccount {
    pub email: String,
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
    pub jira_account: Option<JiraAccount>,
    pub jira_issues: Vec<JiraIssue>,
    pub github_account: Option<GitHubAccount>,
    pub pull_requests: Vec<PullRequest>,
    pub tasks_account: Option<TasksAccount>,
    pub google_tasks: Vec<GoogleTask>,
}
