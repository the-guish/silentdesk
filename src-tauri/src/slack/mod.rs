pub mod api;
pub mod oauth;

use crate::model::{SlackMessage, Topic, VaultData};
use api::MessageMeta;

/// How many recent direct messages a sync keeps.
pub const SYNC_COUNT: usize = 10;

/// Replaces the stored Slack messages with `latest`. A message that was
/// already stored keeps its topic; a new message gets a new topic of its own
/// (no grouping yet). Topics left without any source item are removed.
pub fn apply_sync(data: &mut VaultData, latest: Vec<MessageMeta>, now: &str) {
    let mut messages = Vec::with_capacity(latest.len());
    for meta in latest {
        let existing = data
            .slack_messages
            .iter()
            .find(|m| m.channel_id == meta.channel_id && m.ts == meta.ts);
        let topic_id = match existing {
            Some(m) => m.topic_id.clone(),
            None => {
                let topic = Topic {
                    id: uuid::Uuid::new_v4().to_string(),
                    title: if meta.preview.is_empty() {
                        "(empty message)".into()
                    } else {
                        meta.preview.clone()
                    },
                    created_at: now.to_owned(),
                };
                let id = topic.id.clone();
                data.topics.push(topic);
                id
            }
        };
        messages.push(SlackMessage {
            channel_id: meta.channel_id,
            ts: meta.ts,
            topic_id,
            direction: meta.direction,
            author: meta.author,
            counterpart: meta.counterpart,
            permalink: meta.permalink,
            date: meta.date,
        });
    }
    data.slack_messages = messages;
    data.prune_topics();
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Direction;

    fn meta(channel: &str, ts: &str, preview: &str) -> MessageMeta {
        MessageMeta {
            channel_id: channel.into(),
            ts: ts.into(),
            direction: Direction::Inbound,
            author: "Ana".into(),
            counterpart: "Ana".into(),
            preview: preview.into(),
            permalink: "https://acme.slack.com/archives/D1/p1".into(),
            date: "2026-10-23T10:00:00Z".into(),
        }
    }

    #[test]
    fn each_message_gets_its_own_topic() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("D1", "1.0", "Can you review?"), meta("D1", "2.0", "")],
            "now",
        );
        assert_eq!(data.topics.len(), 2);
        let titles: Vec<_> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["Can you review?", "(empty message)"]);
    }

    #[test]
    fn resync_keeps_topics_and_drops_old_ones() {
        let mut data = VaultData::default();
        apply_sync(
            &mut data,
            vec![meta("D1", "1.0", "A"), meta("D2", "2.0", "B")],
            "now",
        );
        let topic_of_b = data.slack_messages[1].topic_id.clone();
        apply_sync(
            &mut data,
            vec![meta("D3", "3.0", "C"), meta("D2", "2.0", "B")],
            "later",
        );
        assert_eq!(data.slack_messages[1].topic_id, topic_of_b);
        assert_eq!(data.topics.len(), 2);
        assert!(data.topics.iter().all(|t| t.title != "A"));
    }

    #[test]
    fn slack_sync_leaves_gmail_topics_alone() {
        let mut data = VaultData::default();
        crate::gmail::apply_sync(
            &mut data,
            vec![crate::gmail::api::MessageMeta {
                message_id: "m1".into(),
                thread_id: "t1".into(),
                direction: Direction::Inbound,
                from: "a@example.com".into(),
                to: "me@example.com".into(),
                subject: "Budget".into(),
                date: "2026-10-22T10:00:00Z".into(),
            }],
            "now",
        );
        apply_sync(&mut data, vec![meta("D1", "1.0", "Hi")], "now");
        assert_eq!(data.topics.len(), 2);

        crate::gmail::apply_sync(&mut data, vec![], "later");
        assert_eq!(data.topics.len(), 1);
        assert_eq!(data.topics[0].title, "Hi");

        data.clear_slack();
        assert!(data.topics.is_empty());
    }
}
