pub mod api;

use crate::model::{PullRequest, Topic, VaultData};
use api::PullMeta;

/// Replaces the stored pull requests with `latest`. A pull request that was
/// already stored keeps its topic; a new one gets a new topic of its own,
/// titled with its title. Topics left without any source item are removed.
pub fn apply_sync(data: &mut VaultData, latest: Vec<PullMeta>, now: &str) {
    let mut pulls = Vec::with_capacity(latest.len());
    for meta in latest {
        let existing = data.pull_requests.iter().find(|p| p.pr_id == meta.pr_id);
        let topic_id = match existing {
            Some(p) => p.topic_id.clone(),
            None => {
                let topic = Topic {
                    id: uuid::Uuid::new_v4().to_string(),
                    title: if meta.title.is_empty() {
                        format!("{}#{}", meta.repo, meta.number)
                    } else {
                        meta.title.clone()
                    },
                    created_at: now.to_owned(),
                };
                let id = topic.id.clone();
                data.topics.push(topic);
                id
            }
        };
        pulls.push(PullRequest {
            pr_id: meta.pr_id,
            repo: meta.repo,
            number: meta.number,
            topic_id,
            reason: meta.reason,
            direction: meta.direction,
            draft: meta.draft,
            author: meta.author,
            url: meta.url,
            date: meta.date,
        });
    }
    data.pull_requests = pulls;
    data.prune_topics();
}

#[cfg(test)]
mod tests {
    use super::api::Reason;
    use super::*;
    use crate::model::Direction;

    fn meta(id: u64, title: &str) -> PullMeta {
        PullMeta {
            pr_id: id,
            repo: "acme/web".into(),
            number: id,
            title: title.into(),
            reason: Reason::ReviewRequested,
            direction: Direction::Inbound,
            draft: false,
            author: "ana".into(),
            url: format!("https://github.com/acme/web/pull/{id}"),
            date: "2026-10-23T10:00:00Z".into(),
        }
    }

    #[test]
    fn each_pull_request_gets_its_own_topic() {
        let mut data = VaultData::default();
        apply_sync(&mut data, vec![meta(1, "Add retries"), meta(2, "")], "now");
        let titles: Vec<_> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["Add retries", "acme/web#2"]);
    }

    #[test]
    fn resync_keeps_topics_and_drops_closed_pull_requests() {
        let mut data = VaultData::default();
        apply_sync(&mut data, vec![meta(1, "A"), meta(2, "B")], "now");
        let topic_of_b = data.pull_requests[1].topic_id.clone();
        apply_sync(&mut data, vec![meta(2, "B"), meta(3, "C")], "later");
        assert_eq!(data.pull_requests[0].topic_id, topic_of_b);
        assert_eq!(data.topics.len(), 2);
        assert!(data.topics.iter().all(|t| t.title != "A"));

        data.clear_github();
        assert!(data.topics.is_empty());
    }
}
