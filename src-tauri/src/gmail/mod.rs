pub mod api;
pub mod oauth;

use crate::model::{GmailMessage, Topic, VaultData};
use api::MessageMeta;

/// How many recent messages a sync keeps.
pub const SYNC_COUNT: usize = 10;

/// Replaces the stored Gmail messages with `latest`. A message that was
/// already stored keeps its topic; a new message gets a new topic of its own
/// (no grouping yet). Topics left without messages are removed.
pub fn apply_sync(data: &mut VaultData, latest: Vec<MessageMeta>, now: &str) {
    let mut messages = Vec::with_capacity(latest.len());
    for meta in latest {
        let topic_id = match data
            .gmail_messages
            .iter()
            .find(|m| m.message_id == meta.message_id)
        {
            Some(existing) => existing.topic_id.clone(),
            None => {
                let topic = Topic {
                    id: uuid::Uuid::new_v4().to_string(),
                    title: if meta.subject.is_empty() {
                        "(no subject)".into()
                    } else {
                        meta.subject.clone()
                    },
                    created_at: now.to_owned(),
                };
                let id = topic.id.clone();
                data.topics.push(topic);
                id
            }
        };
        messages.push(GmailMessage {
            message_id: meta.message_id,
            thread_id: meta.thread_id,
            topic_id,
            direction: meta.direction,
            from: meta.from,
            to: meta.to,
            subject: meta.subject,
            date: meta.date,
        });
    }
    data.gmail_messages = messages;
    data.prune_topics();
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Direction;

    fn meta(id: &str, subject: &str, date: &str) -> MessageMeta {
        MessageMeta {
            message_id: id.into(),
            thread_id: format!("t-{id}"),
            direction: Direction::Inbound,
            from: "a@example.com".into(),
            to: "me@example.com".into(),
            subject: subject.into(),
            date: date.into(),
        }
    }

    #[test]
    fn each_email_gets_its_own_topic() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![
                meta("1", "Budget", "2026-10-23T10:00:00Z"),
                meta("2", "", "2026-10-22T10:00:00Z"),
            ],
            "now",
        );
        assert_eq!(data.topics.len(), 2);
        assert_eq!(data.gmail_messages.len(), 2);
        assert_ne!(
            data.gmail_messages[0].topic_id,
            data.gmail_messages[1].topic_id
        );
        let views = data.topic_views();
        assert_eq!(views[0].topic.title, "Budget");
        assert_eq!(views[1].topic.title, "(no subject)");
    }

    #[test]
    fn resync_keeps_topics_and_drops_old_ones() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("1", "A", "d1"), meta("2", "B", "d2")],
            "now",
        );
        let topic_of_2 = data.gmail_messages[1].topic_id.clone();

        apply_sync(
            &mut data,
            vec![meta("3", "C", "d3"), meta("2", "B", "d2")],
            "later",
        );
        assert_eq!(data.gmail_messages.len(), 2);
        assert_eq!(data.gmail_messages[1].topic_id, topic_of_2);
        assert_eq!(data.topics.len(), 2);
        assert!(data.topics.iter().all(|t| t.title != "A"));
    }

    #[test]
    fn clear_gmail_removes_everything() {
        let mut data = VaultData::default();
        apply_sync(&mut data, vec![meta("1", "A", "d1")], "now");
        data.clear_gmail();
        assert!(data.topics.is_empty());
        assert!(data.gmail_messages.is_empty());
    }
}
