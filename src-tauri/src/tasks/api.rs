//! Google Tasks REST calls, read-only.

use serde::Deserialize;
use serde::de::DeserializeOwned;
use url::Url;

use crate::error::{Error, Result};
use crate::gmail::oauth::Grant;

const BASE: &str = "https://tasks.googleapis.com/tasks/v1";
const USERINFO: &str = "https://openidconnect.googleapis.com/v1/userinfo";
const SERVICE: &str = "Google Tasks";

/// Read-only access to task lists and tasks. `openid email` only names the
/// account in Settings.
pub const GRANT: Grant = Grant {
    service: SERVICE,
    scopes: &[
        "https://www.googleapis.com/auth/tasks.readonly",
        "openid",
        "email",
    ],
    required: &["https://www.googleapis.com/auth/tasks.readonly"],
};

/// Stop paging after this many pages (100 items each), per list.
const MAX_PAGES: usize = 20;

#[derive(Debug, Clone, PartialEq)]
pub struct TaskMeta {
    pub task_id: String,
    pub list_id: String,
    pub list_title: String,
    pub title: String,
    /// `YYYY-MM-DD`; Google keeps the day only.
    pub due: Option<String>,
    /// Where the task came from, when Google says: Gmail, Docs or Chat.
    pub origin: Option<String>,
    pub url: String,
    /// RFC 3339, when the task was last updated.
    pub date: String,
}

#[derive(Deserialize)]
struct UserInfo {
    email: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Page<T> {
    #[serde(default = "Vec::new")]
    items: Vec<T>,
    next_page_token: Option<String>,
}

#[derive(Deserialize)]
struct RawList {
    id: String,
    #[serde(default)]
    title: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RawTask {
    id: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    status: String,
    due: Option<String>,
    #[serde(default)]
    updated: String,
    web_view_link: Option<String>,
    #[serde(default)]
    links: Vec<RawLink>,
    assignment_info: Option<RawAssignment>,
    #[serde(default)]
    deleted: bool,
}

#[derive(Debug, Deserialize)]
struct RawLink {
    #[serde(rename = "type", default)]
    kind: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RawAssignment {
    surface_type: Option<String>,
}

#[derive(Deserialize, Default)]
struct ErrorBody {
    error: Option<ErrorDetail>,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
}

async fn get<T: DeserializeOwned>(
    http: &reqwest::Client,
    token: &str,
    url: Url,
    query: &[(&str, &str)],
) -> Result<T> {
    let response = http.get(url).bearer_auth(token).query(query).send().await?;
    let status = response.status();
    if status.is_success() {
        return Ok(response.json().await?);
    }
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(Error::Reauthorize(SERVICE));
    }
    let body: ErrorBody = response.json().await.unwrap_or_default();
    Err(Error::Api {
        service: SERVICE,
        status: status.as_u16(),
        message: body
            .error
            .map(|e| e.message)
            .unwrap_or_else(|| status.canonical_reason().unwrap_or("unknown error").into()),
    })
}

/// `BASE` plus path segments, each percent-encoded.
fn endpoint(segments: &[&str]) -> Url {
    let mut url = Url::parse(BASE).expect("valid constant URL");
    url.path_segments_mut()
        .expect("base URL has a path")
        .extend(segments);
    url
}

/// Every page of a list endpoint, up to `MAX_PAGES`.
async fn all<T: DeserializeOwned>(
    http: &reqwest::Client,
    token: &str,
    url: Url,
    query: &[(&str, &str)],
) -> Result<Vec<T>> {
    let mut items = Vec::new();
    let mut page_token: Option<String> = None;
    for _ in 0..MAX_PAGES {
        let mut q = query.to_vec();
        if let Some(t) = &page_token {
            q.push(("pageToken", t));
        }
        let page: Page<T> = get(http, token, url.clone(), &q).await?;
        items.extend(page.items);
        page_token = page.next_page_token;
        if page_token.is_none() {
            break;
        }
    }
    Ok(items)
}

pub async fn email(http: &reqwest::Client, token: &str) -> Result<String> {
    let url = Url::parse(USERINFO).expect("valid constant URL");
    let info: UserInfo = get(http, token, url, &[]).await?;
    Ok(info.email)
}

/// Every open task in every list, including tasks assigned to the user from
/// Docs or Chat, most recently updated first.
pub async fn open_tasks(http: &reqwest::Client, token: &str) -> Result<Vec<TaskMeta>> {
    let lists: Vec<RawList> = all(
        http,
        token,
        endpoint(&["users", "@me", "lists"]),
        &[("maxResults", "100")],
    )
    .await?;
    let mut out = Vec::new();
    for list in lists {
        let tasks: Vec<RawTask> = all(
            http,
            token,
            endpoint(&["lists", &list.id, "tasks"]),
            &[
                ("maxResults", "100"),
                ("showCompleted", "false"),
                ("showHidden", "false"),
                ("showDeleted", "false"),
                ("showAssigned", "true"),
            ],
        )
        .await?;
        out.extend(
            tasks
                .into_iter()
                .filter_map(|t| to_meta(t, &list.id, &list.title)),
        );
    }
    out.sort_by(|a, b| b.date.cmp(&a.date));
    Ok(out)
}

fn to_meta(task: RawTask, list_id: &str, list_title: &str) -> Option<TaskMeta> {
    if task.deleted || task.status == "completed" {
        return None;
    }
    let origin = task
        .assignment_info
        .and_then(|a| a.surface_type)
        .and_then(|s| match s.as_str() {
            "DOCUMENT" => Some("Docs"),
            "SPACE" => Some("Chat"),
            "GMAIL" => Some("Gmail"),
            _ => None,
        })
        .or_else(|| {
            task.links.iter().find_map(|l| match l.kind.as_str() {
                "email" => Some("Gmail"),
                "chat_message" => Some("Chat"),
                _ => None,
            })
        })
        .map(str::to_owned);
    Some(TaskMeta {
        title: task.title.trim().to_owned(),
        due: task
            .due
            .and_then(|d| d.get(..10).map(str::to_owned))
            .filter(|d| d.len() == 10),
        url: task
            .web_view_link
            .unwrap_or_else(|| "https://tasks.google.com/".into()),
        date: task.updated,
        task_id: task.id,
        list_id: list_id.to_owned(),
        list_title: list_title.to_owned(),
        origin,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn task(json: &str) -> RawTask {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn parses_an_open_task() {
        let meta = to_meta(
            task(
                r#"{"id":"t1","title":" Draft Q4 plan ","status":"needsAction",
                    "due":"2026-10-30T00:00:00.000Z","updated":"2026-10-24T09:00:00.000Z",
                    "webViewLink":"https://tasks.google.com/task/t1",
                    "links":[{"type":"email","description":"Budget","link":"https://mail.google.com/x"}]}"#,
            ),
            "L1",
            "My Tasks",
        )
        .unwrap();
        assert_eq!(meta.title, "Draft Q4 plan");
        assert_eq!(meta.due.as_deref(), Some("2026-10-30"));
        assert_eq!(meta.origin.as_deref(), Some("Gmail"));
        assert_eq!(meta.list_title, "My Tasks");
        assert_eq!(meta.url, "https://tasks.google.com/task/t1");
    }

    #[test]
    fn assignment_wins_over_links_and_missing_fields_are_fine() {
        let meta = to_meta(
            task(
                r#"{"id":"t2","status":"needsAction","updated":"u",
                    "assignmentInfo":{"surfaceType":"DOCUMENT","linkToTask":"x"},
                    "links":[{"type":"email"}]}"#,
            ),
            "L1",
            "Work",
        )
        .unwrap();
        assert_eq!(meta.origin.as_deref(), Some("Docs"));
        assert_eq!(meta.due, None);
        assert_eq!(meta.title, "");
    }

    #[test]
    fn skips_completed_and_deleted() {
        assert!(to_meta(task(r#"{"id":"a","status":"completed"}"#), "L", "l").is_none());
        assert!(
            to_meta(
                task(r#"{"id":"b","status":"needsAction","deleted":true}"#),
                "L",
                "l"
            )
            .is_none()
        );
    }

    #[test]
    fn list_ids_are_encoded_in_paths() {
        assert_eq!(
            endpoint(&["lists", "a/b?c", "tasks"]).as_str(),
            "https://tasks.googleapis.com/tasks/v1/lists/a%2Fb%3Fc/tasks"
        );
        assert_eq!(
            endpoint(&["users", "@me", "lists"]).as_str(),
            "https://tasks.googleapis.com/tasks/v1/users/@me/lists"
        );
    }

    #[test]
    fn pages_parse_without_items() {
        let page: Page<RawList> = serde_json::from_str(r#"{"kind":"tasks#taskLists"}"#).unwrap();
        assert!(page.items.is_empty());
        assert!(page.next_page_token.is_none());
    }
}
