pub mod api;
pub mod oauth;
pub mod reply;

use std::collections::HashSet;

use crate::model::{GmailMessage, Topic, VaultData};
use api::MessageMeta;

/// Adds the messages SilentDesk does not have yet, each with a topic of its
/// own (no grouping yet). Stored messages and their topics stay as they are.
pub fn add_messages(data: &mut VaultData, messages: Vec<MessageMeta>, now: &str) {
    let mut known: HashSet<String> = data
        .gmail_messages
        .iter()
        .map(|m| m.message_id.clone())
        .collect();
    for meta in messages {
        if !known.insert(meta.message_id.clone()) {
            continue;
        }
        let topic = Topic {
            id: uuid::Uuid::new_v4().to_string(),
            title: if meta.subject.is_empty() {
                "(no subject)".into()
            } else {
                meta.subject.clone()
            },
            created_at: now.to_owned(),
        };
        data.gmail_messages.push(GmailMessage {
            message_id: meta.message_id,
            thread_id: meta.thread_id,
            topic_id: topic.id.clone(),
            direction: meta.direction,
            from: meta.from,
            to: meta.to,
            subject: meta.subject,
            date: meta.date,
        });
        data.topics.push(topic);
    }
}

/// The IDs in `ids` that are not stored yet, in order and without repeats.
pub fn new_ids(data: &VaultData, ids: Vec<String>) -> Vec<String> {
    let mut seen: HashSet<String> = data
        .gmail_messages
        .iter()
        .map(|m| m.message_id.clone())
        .collect();
    ids.into_iter()
        .filter(|id| seen.insert(id.clone()))
        .collect()
}

/// Forgets one message, and its topic if nothing else is in it.
pub fn remove_message(data: &mut VaultData, message_id: &str) {
    data.gmail_messages.retain(|m| m.message_id != message_id);
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
            from: String::new(),
            to: String::new(),
            subject: subject.into(),
            date: date.into(),
        }
    }

    #[test]
    fn each_email_gets_its_own_topic() {
        let mut data = VaultData::default();
        add_messages(
            &mut data,
            vec![
                meta("1", "Budget", "2026-10-23T10:00:00Z"),
                meta("2", "", "2026-10-22T10:00:00Z"),
            ],
            "now",
        );
        assert_eq!(data.topics.len(), 2);
        assert_ne!(
            data.gmail_messages[0].topic_id,
            data.gmail_messages[1].topic_id
        );
        let views = data.topic_views();
        assert_eq!(views[0].topic.title, "Budget");
        assert_eq!(views[1].topic.title, "(no subject)");
    }

    #[test]
    fn later_syncs_keep_what_is_stored() {
        let mut data = VaultData::default();
        add_messages(
            &mut data,
            vec![meta("1", "A", "d1"), meta("2", "B", "d2")],
            "now",
        );
        let topic_of_2 = data.gmail_messages[1].topic_id.clone();

        add_messages(
            &mut data,
            vec![
                meta("3", "C", "d3"),
                meta("2", "B2", "d2"),
                meta("3", "C", "d3"),
            ],
            "later",
        );
        assert_eq!(data.gmail_messages.len(), 3);
        assert_eq!(data.gmail_messages[1].topic_id, topic_of_2);
        assert_eq!(data.gmail_messages[1].subject, "B");
        let titles: Vec<&str> = data.topics.iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, ["A", "B", "C"]);
    }

    #[test]
    fn new_ids_skips_stored_and_repeated() {
        let mut data = VaultData::default();
        add_messages(&mut data, vec![meta("1", "A", "d1")], "now");
        for (ids, expected) in [
            (vec![], vec![]),
            (vec!["1"], vec![]),
            (vec!["2", "1", "3"], vec!["2", "3"]),
            (vec!["2", "2"], vec!["2"]),
        ] {
            let ids = ids.into_iter().map(String::from).collect();
            assert_eq!(new_ids(&data, ids), expected);
        }
    }

    #[test]
    fn remove_message_drops_its_topic_only() {
        let mut data = VaultData::default();
        add_messages(
            &mut data,
            vec![meta("1", "A", "d1"), meta("2", "B", "d2")],
            "now",
        );
        remove_message(&mut data, "1");
        remove_message(&mut data, "unknown");
        assert_eq!(data.gmail_messages.len(), 1);
        assert_eq!(data.gmail_messages[0].message_id, "2");
        assert_eq!(data.topics.len(), 1);
        assert_eq!(data.topics[0].title, "B");
    }

    #[test]
    fn clear_gmail_removes_everything() {
        let mut data = VaultData::default();
        add_messages(&mut data, vec![meta("1", "A", "d1")], "now");
        data.gmail_history_id = Some("42".into());
        data.clear_gmail();
        assert!(data.topics.is_empty());
        assert!(data.gmail_messages.is_empty());
        assert_eq!(data.gmail_history_id, None);
    }
}
