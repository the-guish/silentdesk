//! Builds the RFC 2822 message for a reply. The user types the body; nothing
//! is quoted from the original, so its body is never read.

use base64::Engine;
use base64::engine::general_purpose::STANDARD;

use crate::model::Direction;

/// The headers of the message being answered.
#[derive(Debug, Clone, PartialEq)]
pub struct Original {
    pub direction: Direction,
    pub from: String,
    pub to: String,
    pub reply_to: String,
    pub subject: String,
    /// The RFC 2822 `Message-ID`, not Gmail's ID.
    pub message_id: String,
    pub references: String,
}

/// Who gets the reply: the sender (or its `Reply-To`) for a received email,
/// and the original recipients for one the user sent.
pub fn recipient(original: &Original) -> &str {
    match original.direction {
        Direction::Outbound => &original.to,
        Direction::Inbound if !original.reply_to.trim().is_empty() => &original.reply_to,
        Direction::Inbound => &original.from,
    }
}

pub fn subject(original: &str) -> String {
    let trimmed = original.trim();
    let has_prefix = trimmed
        .get(..3)
        .is_some_and(|p| p.eq_ignore_ascii_case("re:"));
    match (trimmed.is_empty(), has_prefix) {
        (true, _) => "Re:".into(),
        (_, true) => trimmed.into(),
        _ => format!("Re: {trimmed}"),
    }
}

/// The full message, with CRLF line endings. Gmail fills in `From` and
/// `Date`.
pub fn build(original: &Original, body: &str) -> String {
    let mut headers = vec![
        ("To", clean(recipient(original))),
        ("Subject", encode_word(&clean(&subject(&original.subject)))),
    ];
    let message_id = clean(&original.message_id);
    if !message_id.is_empty() {
        let references = clean(&format!("{} {message_id}", original.references));
        headers.push(("In-Reply-To", message_id));
        headers.push(("References", references.trim().to_owned()));
    }
    headers.push(("MIME-Version", "1.0".into()));
    headers.push(("Content-Type", "text/plain; charset=UTF-8".into()));
    headers.push(("Content-Transfer-Encoding", "base64".into()));

    let mut out = String::new();
    for (name, value) in headers {
        out.push_str(&format!("{name}: {value}\r\n"));
    }
    out.push_str("\r\n");
    let normalized = body.replace("\r\n", "\n").replace('\n', "\r\n");
    let encoded = STANDARD.encode(normalized.as_bytes());
    for line in encoded.as_bytes().chunks(76) {
        out.push_str(std::str::from_utf8(line).expect("base64 is ASCII"));
        out.push_str("\r\n");
    }
    out
}

/// Header values must stay on one line, or they could inject headers.
fn clean(value: &str) -> String {
    value
        .split(['\r', '\n'])
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

/// RFC 2047 encoding for a header with non-ASCII text.
fn encode_word(value: &str) -> String {
    if value.is_ascii() {
        value.to_owned()
    } else {
        format!("=?UTF-8?B?{}?=", STANDARD.encode(value))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn original(direction: Direction, reply_to: &str) -> Original {
        Original {
            direction,
            from: "Ana <ana@example.com>".into(),
            to: "me@example.com, bo@example.com".into(),
            reply_to: reply_to.into(),
            subject: "Budget".into(),
            message_id: "<m1@example.com>".into(),
            references: "<m0@example.com>".into(),
        }
    }

    #[test]
    fn recipient_by_direction() {
        for (direction, reply_to, expected) in [
            (Direction::Inbound, "", "Ana <ana@example.com>"),
            (Direction::Inbound, "  ", "Ana <ana@example.com>"),
            (Direction::Inbound, "list@example.com", "list@example.com"),
            (Direction::Outbound, "", "me@example.com, bo@example.com"),
            (
                Direction::Outbound,
                "list@example.com",
                "me@example.com, bo@example.com",
            ),
        ] {
            assert_eq!(recipient(&original(direction, reply_to)), expected);
        }
    }

    #[test]
    fn subject_prefix() {
        for (input, expected) in [
            ("Budget", "Re: Budget"),
            ("  Budget ", "Re: Budget"),
            ("Re: Budget", "Re: Budget"),
            ("RE:Budget", "RE:Budget"),
            ("Ré", "Re: Ré"),
            ("", "Re:"),
        ] {
            assert_eq!(subject(input), expected, "{input:?}");
        }
    }

    #[test]
    fn clean_and_encode_headers() {
        for (input, expected) in [
            ("plain", "plain"),
            ("a\r\nBcc: x@evil.com", "a Bcc: x@evil.com"),
            ("a\n\nb", "a b"),
        ] {
            assert_eq!(clean(input), expected);
        }
        assert_eq!(encode_word("Re: hi"), "Re: hi");
        assert_eq!(encode_word("Re: ¿sí?"), "=?UTF-8?B?UmU6IMK/c8OtPw==?=");
    }

    #[test]
    fn builds_threaded_reply() {
        let raw = build(&original(Direction::Inbound, ""), "Thanks!\nAna");
        let (head, body) = raw.split_once("\r\n\r\n").unwrap();
        assert_eq!(
            head,
            "To: Ana <ana@example.com>\r\n\
             Subject: Re: Budget\r\n\
             In-Reply-To: <m1@example.com>\r\n\
             References: <m0@example.com> <m1@example.com>\r\n\
             MIME-Version: 1.0\r\n\
             Content-Type: text/plain; charset=UTF-8\r\n\
             Content-Transfer-Encoding: base64"
        );
        let decoded = STANDARD.decode(body.replace("\r\n", "")).unwrap();
        assert_eq!(decoded, b"Thanks!\r\nAna");
    }

    #[test]
    fn no_threading_headers_without_message_id() {
        let mut o = original(Direction::Inbound, "");
        o.message_id = String::new();
        let raw = build(&o, "x");
        assert!(!raw.contains("In-Reply-To"));
        assert!(!raw.contains("References"));
    }

    #[test]
    fn injected_recipient_stays_one_header() {
        let mut o = original(Direction::Inbound, "");
        o.from = "a@example.com\r\nBcc: x@evil.com".into();
        let raw = build(&o, "x");
        assert!(raw.starts_with("To: a@example.com Bcc: x@evil.com\r\nSubject:"));
    }
}
