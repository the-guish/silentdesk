//! The few Slack Web API calls SilentDesk makes, all read-only.

use std::collections::HashMap;

use serde::Deserialize;
use serde::de::DeserializeOwned;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;

use crate::error::{Error, Result};
use crate::model::Direction;

const BASE: &str = "https://slack.com/api";

/// Longest topic title taken from a message, in characters.
pub const PREVIEW_CHARS: usize = 120;

/// Search queries that together cover direct messages sent to and by the
/// user. Results are filtered to direct and group-direct conversations
/// afterwards, so a broader match is harmless.
fn queries(me: &str) -> [String; 2] {
    ["to:me".to_owned(), format!("from:<@{me}>")]
}

#[derive(Debug, Clone, PartialEq)]
pub struct Identity {
    pub user_id: String,
    pub user_name: String,
    pub team_id: String,
    pub team_name: String,
}

/// One direct message, as SilentDesk needs it.
#[derive(Debug, Clone, PartialEq)]
pub struct MessageMeta {
    pub channel_id: String,
    pub ts: String,
    pub direction: Direction,
    pub author: String,
    /// Who the conversation is with: the other person, or "Group DM".
    pub counterpart: String,
    /// The start of the message as plain text, used as the topic title.
    pub preview: String,
    pub permalink: String,
    pub date: String,
}

#[derive(Deserialize)]
struct Envelope {
    ok: bool,
    error: Option<String>,
}

#[derive(Deserialize)]
struct AuthTest {
    user_id: String,
    user: String,
    team_id: String,
    team: String,
}

#[derive(Deserialize)]
struct SearchResponse {
    messages: SearchMessages,
}

#[derive(Deserialize)]
struct SearchMessages {
    #[serde(default)]
    matches: Vec<Match>,
}

#[derive(Debug, Deserialize)]
struct Match {
    #[serde(rename = "type", default)]
    kind: String,
    channel: MatchChannel,
    user: Option<String>,
    username: Option<String>,
    #[serde(default)]
    text: String,
    ts: String,
    #[serde(default)]
    permalink: String,
}

#[derive(Debug, Deserialize)]
struct MatchChannel {
    id: String,
    /// For a 1:1 DM, the other user's ID.
    #[serde(default)]
    name: String,
    #[serde(default)]
    is_im: bool,
    #[serde(default)]
    is_mpim: bool,
}

impl Match {
    fn is_im(&self) -> bool {
        self.kind == "im" || self.channel.is_im
    }

    fn is_direct(&self) -> bool {
        self.is_im() || self.channel.is_mpim
    }
}

#[derive(Deserialize)]
struct UserInfo {
    user: User,
}

#[derive(Deserialize)]
struct User {
    name: String,
    #[serde(default)]
    real_name: String,
    #[serde(default)]
    profile: Profile,
}

#[derive(Deserialize, Default)]
struct Profile {
    #[serde(default)]
    display_name: String,
    #[serde(default)]
    real_name: String,
}

impl User {
    fn label(self) -> String {
        [
            self.profile.display_name,
            self.profile.real_name,
            self.real_name,
            self.name,
        ]
        .into_iter()
        .find(|s| !s.trim().is_empty())
        .unwrap_or_default()
    }
}

async fn call<T: DeserializeOwned>(
    http: &reqwest::Client,
    token: &str,
    method: &str,
    query: &[(&str, &str)],
) -> Result<T> {
    let response = http
        .get(format!("{BASE}/{method}"))
        .bearer_auth(token)
        .query(query)
        .send()
        .await?;
    let status = response.status();
    if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
        let wait = response
            .headers()
            .get("retry-after")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("a few");
        return Err(Error::Api {
            service: "Slack",
            status: 429,
            message: format!("rate limited, try again in {wait} seconds"),
        });
    }
    let body: serde_json::Value = response.json().await?;
    let envelope: Envelope = serde_json::from_value(body.clone()).map_err(|e| Error::Api {
        service: "Slack",
        status: status.as_u16(),
        message: e.to_string(),
    })?;
    if !envelope.ok {
        let error = envelope.error.unwrap_or_else(|| "unknown_error".into());
        return Err(match error.as_str() {
            "invalid_auth" | "not_authed" | "token_revoked" | "token_expired"
            | "account_inactive" => Error::Reauthorize("Slack"),
            _ => Error::Api {
                service: "Slack",
                status: status.as_u16(),
                message: error,
            },
        });
    }
    serde_json::from_value(body).map_err(|e| Error::Api {
        service: "Slack",
        status: status.as_u16(),
        message: e.to_string(),
    })
}

pub async fn identity(http: &reqwest::Client, token: &str) -> Result<Identity> {
    let a: AuthTest = call(http, token, "auth.test", &[]).await?;
    Ok(Identity {
        user_id: a.user_id,
        user_name: a.user,
        team_id: a.team_id,
        team_name: a.team,
    })
}

/// The `count` most recent direct messages (1:1 and group), sent or
/// received, newest first.
pub async fn recent_direct_messages(
    http: &reqwest::Client,
    token: &str,
    me: &str,
    count: usize,
) -> Result<Vec<MessageMeta>> {
    let page = (count * 3).min(100).to_string();
    let mut matches = Vec::new();
    for query in queries(me) {
        let r: SearchResponse = call(
            http,
            token,
            "search.messages",
            &[
                ("query", query.as_str()),
                ("sort", "timestamp"),
                ("sort_dir", "desc"),
                ("count", page.as_str()),
            ],
        )
        .await?;
        matches.extend(r.messages.matches);
    }
    let matches = select_recent(matches, count);

    let mut names = Names::default();
    let mut out = Vec::with_capacity(matches.len());
    for m in matches {
        out.push(to_meta(http, token, me, m, &mut names).await);
    }
    Ok(out)
}

/// Keeps direct messages only, drops duplicates, newest first.
fn select_recent(mut matches: Vec<Match>, count: usize) -> Vec<Match> {
    let mut seen = std::collections::HashSet::new();
    matches.retain(|m| m.is_direct() && seen.insert((m.channel.id.clone(), m.ts.clone())));
    matches.sort_by(|a, b| ts_value(&b.ts).total_cmp(&ts_value(&a.ts)));
    matches.truncate(count);
    matches
}

fn ts_value(ts: &str) -> f64 {
    ts.parse().unwrap_or(0.0)
}

/// Resolves user IDs to display names, once per ID per sync.
#[derive(Default)]
struct Names(HashMap<String, String>);

impl Names {
    async fn get(&mut self, http: &reqwest::Client, token: &str, id: &str) -> String {
        if let Some(name) = self.0.get(id) {
            return name.clone();
        }
        let name = call::<UserInfo>(http, token, "users.info", &[("user", id)])
            .await
            .map(|u| u.user.label())
            .ok()
            .filter(|n| !n.is_empty())
            .unwrap_or_else(|| "someone".into());
        self.0.insert(id.to_owned(), name.clone());
        name
    }
}

async fn to_meta(
    http: &reqwest::Client,
    token: &str,
    me: &str,
    m: Match,
    names: &mut Names,
) -> MessageMeta {
    let outbound = m.user.as_deref() == Some(me);
    let author = match (&m.user, &m.username) {
        (Some(id), _) => names.get(http, token, id).await,
        (None, Some(name)) => name.clone(),
        (None, None) => "someone".into(),
    };
    let counterpart = if !m.is_im() {
        "Group DM".to_owned()
    } else if outbound {
        names.get(http, token, &m.channel.name).await
    } else {
        author.clone()
    };

    let mut mentioned = HashMap::new();
    for id in mention_ids(&m.text) {
        let name = names.get(http, token, &id).await;
        mentioned.insert(id, name);
    }
    MessageMeta {
        direction: if outbound {
            Direction::Outbound
        } else {
            Direction::Inbound
        },
        author,
        counterpart,
        preview: preview(&plain_text(&m.text, &mentioned), PREVIEW_CHARS),
        date: ts_to_rfc3339(&m.ts),
        channel_id: m.channel.id,
        ts: m.ts,
        permalink: m.permalink,
    }
}

fn ts_to_rfc3339(ts: &str) -> String {
    let secs = ts
        .split('.')
        .next()
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    OffsetDateTime::from_unix_timestamp(secs)
        .ok()
        .and_then(|d| d.format(&Rfc3339).ok())
        .unwrap_or_default()
}

/// User IDs mentioned as `<@U123>` or `<@U123|name>`.
fn mention_ids(text: &str) -> Vec<String> {
    let mut ids: Vec<String> = text
        .split("<@")
        .skip(1)
        .filter_map(|rest| rest.split(['>', '|']).next())
        .map(str::to_owned)
        .collect();
    ids.sort();
    ids.dedup();
    ids
}

/// Turns Slack's message markup into plain text: `<@U1>` → `@Name`,
/// `<#C1|general>` → `#general`, `<https://x|label>` → `label`,
/// `<!here>` → `@here`, and HTML entities back to characters.
fn plain_text(text: &str, names: &HashMap<String, String>) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(start) = rest.find('<') {
        out.push_str(&rest[..start]);
        let after = &rest[start + 1..];
        let Some(end) = after.find('>') else {
            out.push_str(&rest[start..]);
            rest = "";
            break;
        };
        let inner = &after[..end];
        let (target, label) = match inner.split_once('|') {
            Some((t, l)) => (t, Some(l)),
            None => (inner, None),
        };
        if let Some(id) = target.strip_prefix('@') {
            let name = names
                .get(id)
                .map(String::as_str)
                .or(label)
                .unwrap_or("someone");
            out.push('@');
            out.push_str(name);
        } else if let Some(id) = target.strip_prefix('#') {
            out.push('#');
            out.push_str(label.unwrap_or(id));
        } else if let Some(special) = target.strip_prefix('!') {
            out.push('@');
            out.push_str(label.unwrap_or(special.split('^').next().unwrap_or(special)));
        } else {
            out.push_str(label.unwrap_or(target));
        }
        rest = &after[end + 1..];
    }
    out.push_str(rest);
    out.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
}

/// Collapses whitespace and cuts at `max` characters on a word boundary.
fn preview(text: &str, max: usize) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if collapsed.chars().count() <= max {
        return collapsed;
    }
    let cut: String = collapsed.chars().take(max).collect();
    let cut = cut.rsplit_once(' ').map_or(cut.as_str(), |(head, _)| head);
    format!("{}…", cut.trim_end())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(json: &str) -> Match {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn keeps_only_direct_messages_newest_first_without_duplicates() {
        let matches = vec![
            m(
                r#"{"type":"message","channel":{"id":"C1","name":"general"},"user":"U1","text":"x","ts":"300.0"}"#,
            ),
            m(
                r#"{"type":"im","channel":{"id":"D1","name":"U2"},"user":"U2","text":"a","ts":"100.0"}"#,
            ),
            m(
                r#"{"type":"message","channel":{"id":"G1","name":"mpdm-a--b-1","is_mpim":true},"user":"U3","text":"b","ts":"200.0"}"#,
            ),
            m(
                r#"{"type":"im","channel":{"id":"D1","name":"U2"},"user":"U2","text":"a","ts":"100.0"}"#,
            ),
            m(
                r#"{"type":"im","channel":{"id":"D2","name":"U4","is_im":true},"user":"ME","text":"c","ts":"50.5"}"#,
            ),
        ];
        let picked = select_recent(matches, 10);
        let ids: Vec<_> = picked
            .iter()
            .map(|m| (m.channel.id.as_str(), m.ts.as_str()))
            .collect();
        assert_eq!(ids, [("G1", "200.0"), ("D1", "100.0"), ("D2", "50.5")]);
        assert_eq!(select_recent(picked, 2).len(), 2);
    }

    #[test]
    fn converts_markup_to_plain_text() {
        let names = HashMap::from([("U1".to_owned(), "Ana".to_owned())]);
        let text = "Hey <@U1>, see <#C9|deploys> and <https://x.example/a?b=1&amp;c=2|the doc> \
                    or <https://y.example>. <!here> &lt;3 <@U7|bo>";
        assert_eq!(
            plain_text(text, &names),
            "Hey @Ana, see #deploys and the doc or https://y.example. @here <3 @bo"
        );
        assert_eq!(plain_text("broken <tag", &names), "broken <tag");
    }

    #[test]
    fn finds_mentions() {
        assert_eq!(mention_ids("<@U2> and <@U1|ana> and <@U2>"), ["U1", "U2"]);
        assert!(mention_ids("no mentions").is_empty());
    }

    #[test]
    fn previews_are_short_and_single_line() {
        assert_eq!(preview("  one\n\ntwo  ", 120), "one two");
        assert_eq!(preview("alpha beta gamma", 12), "alpha beta…");
        assert_eq!(preview("ñandú ñandú", 7), "ñandú…");
    }

    #[test]
    fn converts_timestamps() {
        assert_eq!(ts_to_rfc3339("1761213600.000200"), "2025-10-23T10:00:00Z");
    }

    #[test]
    fn queries_cover_both_directions() {
        assert_eq!(queries("U9"), ["to:me".to_owned(), "from:<@U9>".to_owned()]);
    }
}
