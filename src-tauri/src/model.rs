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
    pub reason: crate::github::api::Reason,
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
pub struct GitHubAccount {
    pub endpoint: crate::github::api::Endpoint,
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

impl VaultData {
    /// Drops topics that no source item points to any more.
    pub fn prune_topics(&mut self) {
        let used: HashSet<&str> = self
            .gmail_messages
            .iter()
            .map(|m| m.topic_id.as_str())
            .chain(self.slack_messages.iter().map(|m| m.topic_id.as_str()))
            .chain(self.jira_issues.iter().map(|i| i.topic_id.as_str()))
            .chain(self.pull_requests.iter().map(|p| p.topic_id.as_str()))
            .chain(self.google_tasks.iter().map(|t| t.topic_id.as_str()))
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

    pub fn clear_jira(&mut self) {
        self.jira_account = None;
        self.jira_issues.clear();
        self.prune_topics();
    }

    pub fn clear_github(&mut self) {
        self.github_account = None;
        self.pull_requests.clear();
        self.prune_topics();
    }

    pub fn clear_tasks(&mut self) {
        self.tasks_account = None;
        self.google_tasks.clear();
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
        let mut jira_by_topic: HashMap<&str, Vec<JiraIssue>> = HashMap::new();
        for i in &self.jira_issues {
            jira_by_topic
                .entry(&i.topic_id)
                .or_default()
                .push(i.clone());
        }
        let mut pulls_by_topic: HashMap<&str, Vec<PullRequest>> = HashMap::new();
        for p in &self.pull_requests {
            pulls_by_topic
                .entry(&p.topic_id)
                .or_default()
                .push(p.clone());
        }
        let mut tasks_by_topic: HashMap<&str, Vec<GoogleTask>> = HashMap::new();
        for t in &self.google_tasks {
            tasks_by_topic
                .entry(&t.topic_id)
                .or_default()
                .push(t.clone());
        }
        let mut views: Vec<TopicView> = self
            .topics
            .iter()
            .map(|t| {
                let mut emails = emails_by_topic.remove(t.id.as_str()).unwrap_or_default();
                emails.sort_by(|a, b| b.date.cmp(&a.date));
                let mut slack_messages = slack_by_topic.remove(t.id.as_str()).unwrap_or_default();
                slack_messages.sort_by(|a, b| b.date.cmp(&a.date));
                let mut jira_issues = jira_by_topic.remove(t.id.as_str()).unwrap_or_default();
                jira_issues.sort_by(|a, b| b.date.cmp(&a.date));
                let mut pull_requests = pulls_by_topic.remove(t.id.as_str()).unwrap_or_default();
                pull_requests.sort_by(|a, b| b.date.cmp(&a.date));
                let mut google_tasks = tasks_by_topic.remove(t.id.as_str()).unwrap_or_default();
                google_tasks.sort_by(|a, b| b.date.cmp(&a.date));
                TopicView {
                    topic: t.clone(),
                    emails,
                    slack_messages,
                    jira_issues,
                    pull_requests,
                    google_tasks,
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
    let pull = view.pull_requests.first().map(|p| p.date.as_str());
    let task = view.google_tasks.first().map(|t| t.date.as_str());
    email
        .max(slack)
        .max(jira)
        .max(pull)
        .max(task)
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
    pub pull_requests: Vec<PullRequest>,
    pub google_tasks: Vec<GoogleTask>,
}
