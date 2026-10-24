pub mod api;

use crate::model::{GoogleTask, Topic, VaultData};
use api::TaskMeta;

/// Replaces the stored tasks with `latest`. A task that was already stored
/// keeps its topic, and the topic follows the task's current title; a new
/// task gets a new topic of its own. Topics left without any source item
/// are removed.
pub fn apply_sync(data: &mut VaultData, latest: Vec<TaskMeta>, now: &str) {
    let mut tasks = Vec::with_capacity(latest.len());
    for meta in latest {
        let title = if meta.title.is_empty() {
            "(untitled task)".to_owned()
        } else {
            meta.title.clone()
        };
        let existing = data.google_tasks.iter().find(|t| t.task_id == meta.task_id);
        let topic_id = match existing {
            Some(t) => {
                let id = t.topic_id.clone();
                if let Some(topic) = data.topics.iter_mut().find(|topic| topic.id == id) {
                    topic.title = title;
                }
                id
            }
            None => {
                let topic = Topic {
                    id: uuid::Uuid::new_v4().to_string(),
                    title,
                    created_at: now.to_owned(),
                };
                let id = topic.id.clone();
                data.topics.push(topic);
                id
            }
        };
        tasks.push(GoogleTask {
            task_id: meta.task_id,
            list_id: meta.list_id,
            list_title: meta.list_title,
            topic_id,
            due: meta.due,
            origin: meta.origin,
            url: meta.url,
            date: meta.date,
        });
    }
    data.google_tasks = tasks;
    data.prune_topics();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meta(id: &str, title: &str) -> TaskMeta {
        TaskMeta {
            task_id: id.into(),
            list_id: "L1".into(),
            list_title: "My Tasks".into(),
            title: title.into(),
            due: None,
            origin: None,
            url: "https://tasks.google.com/".into(),
            date: "2026-10-24T09:00:00Z".into(),
        }
    }

    #[test]
    fn each_task_gets_its_own_topic() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("1", "Draft plan"), meta("2", "")],
            "now",
        );
        let titles: Vec<_> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["Draft plan", "(untitled task)"]);
    }

    #[test]
    fn resync_follows_renames_and_drops_finished_tasks() {
        let mut data = VaultData::default();
        apply_sync(&mut data, vec![meta("1", "A"), meta("2", "B")], "now");
        let topic_of_b = data.google_tasks[1].topic_id.clone();

        apply_sync(
            &mut data,
            vec![meta("2", "B, renamed"), meta("3", "C")],
            "later",
        );
        assert_eq!(data.google_tasks[0].topic_id, topic_of_b);
        let titles: Vec<_> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["B, renamed", "C"]);

        data.clear_tasks();
        assert!(data.topics.is_empty());
    }
}
