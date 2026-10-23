pub mod api;

use crate::model::{JiraIssue, Topic, VaultData};
use api::IssueMeta;

/// How many open issues a sync keeps.
pub const SYNC_COUNT: usize = 10;

/// Replaces the stored Jira issues with `latest`. An issue that was already
/// stored keeps its topic; a new issue gets a new topic of its own, titled
/// with its summary. Topics left without any source item are removed.
pub fn apply_sync(data: &mut VaultData, latest: Vec<IssueMeta>, now: &str) {
    let mut issues = Vec::with_capacity(latest.len());
    for meta in latest {
        let existing = data
            .jira_issues
            .iter()
            .find(|i| i.issue_id == meta.issue_id);
        let topic_id = match existing {
            Some(i) => i.topic_id.clone(),
            None => {
                let topic = Topic {
                    id: uuid::Uuid::new_v4().to_string(),
                    title: if meta.summary.is_empty() {
                        meta.key.clone()
                    } else {
                        meta.summary.clone()
                    },
                    created_at: now.to_owned(),
                };
                let id = topic.id.clone();
                data.topics.push(topic);
                id
            }
        };
        issues.push(JiraIssue {
            issue_id: meta.issue_id,
            key: meta.key,
            topic_id,
            direction: meta.direction,
            status: meta.status,
            project: meta.project,
            assignee: meta.assignee,
            reporter: meta.reporter,
            url: meta.url,
            date: meta.date,
        });
    }
    data.jira_issues = issues;
    data.prune_topics();
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Direction;

    fn meta(id: &str, key: &str, summary: &str) -> IssueMeta {
        IssueMeta {
            issue_id: id.into(),
            key: key.into(),
            summary: summary.into(),
            direction: Direction::Inbound,
            status: "Open".into(),
            project: "PAY".into(),
            assignee: "Luis".into(),
            reporter: "Ana".into(),
            url: format!("https://acme.atlassian.net/browse/{key}"),
            date: "2026-10-23T10:00:00Z".into(),
        }
    }

    #[test]
    fn each_issue_gets_its_own_topic() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("1", "PAY-1", "Refunds"), meta("2", "PAY-2", "")],
            "now",
        );
        let titles: Vec<_> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["Refunds", "PAY-2"]);
    }

    #[test]
    fn resync_keeps_topics_and_drops_closed_issues() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("1", "PAY-1", "A"), meta("2", "PAY-2", "B")],
            "now",
        );
        let topic_of_b = data.jira_issues[1].topic_id.clone();
        apply_sync(
            &mut data,
            vec![meta("2", "PAY-2", "B"), meta("3", "PAY-3", "C")],
            "later",
        );
        assert_eq!(data.jira_issues[0].topic_id, topic_of_b);
        assert_eq!(data.topics.len(), 2);
        assert!(data.topics.iter().all(|t| t.title != "A"));

        data.clear_jira();
        assert!(data.topics.is_empty());
    }
}
