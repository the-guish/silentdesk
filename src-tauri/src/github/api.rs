//! GitHub REST calls, read-only. Works with github.com and GitHub Enterprise
//! Server, using a personal access token (fine-grained or classic).

use std::collections::HashMap;

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use url::Url;

use crate::error::{Error, Result};
use crate::model::Direction;

const API_VERSION: &str = "2022-11-28";
/// Most open pull requests kept per query. Search pages hold up to 100.
const PER_QUERY: &str = "50";

/// Why a pull request is in the user's queue.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum Reason {
    ReviewRequested,
    Assigned,
    Authored,
}

impl Reason {
    fn direction(self) -> Direction {
        match self {
            Reason::Authored => Direction::Outbound,
            Reason::ReviewRequested | Reason::Assigned => Direction::Inbound,
        }
    }
}

/// Open pull requests that ask something of the user, then the user's own.
/// Each query must name `is:pr`; GitHub's search rejects queries without a
/// type. `review-requested` includes requests made to the user's teams.
const QUERIES: [(&str, Reason); 3] = [
    (
        "is:pr is:open archived:false review-requested:@me",
        Reason::ReviewRequested,
    ),
    (
        "is:pr is:open archived:false assignee:@me",
        Reason::Assigned,
    ),
    ("is:pr is:open archived:false author:@me", Reason::Authored),
];

/// Where to call the API and where people browse, decided at connect time.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Endpoint {
    /// `https://api.github.com` or `https://<host>/api/v3`.
    pub api_base: String,
    /// `https://github.com` or `https://<host>`.
    pub web_base: String,
}

impl Endpoint {
    /// No server means github.com. Otherwise a GitHub Enterprise Server
    /// host such as `github.acme.com`; plain `http` is refused.
    pub fn for_server(server: Option<&str>) -> Result<Self> {
        let server = server.map(str::trim).filter(|s| !s.is_empty());
        let Some(server) = server else {
            return Ok(Self {
                api_base: "https://api.github.com".into(),
                web_base: "https://github.com".into(),
            });
        };
        let with_scheme = if server.contains("://") {
            server.to_owned()
        } else {
            format!("https://{server}")
        };
        let invalid = || Error::Auth("the GitHub server address is not valid.".into());
        let url = Url::parse(&with_scheme).map_err(|_| invalid())?;
        if url.scheme() != "https" {
            return Err(Error::Auth("the GitHub server must use https://.".into()));
        }
        let host = url.host_str().ok_or_else(invalid)?;
        if host == "github.com" || host == "api.github.com" {
            return Self::for_server(None);
        }
        let port = url.port().map(|p| format!(":{p}")).unwrap_or_default();
        let web_base = format!("https://{host}{port}");
        Ok(Self {
            api_base: format!("{web_base}/api/v3"),
            web_base,
        })
    }

    pub fn host(&self) -> &str {
        self.web_base.trim_start_matches("https://")
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Me {
    pub login: String,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PullMeta {
    pub pr_id: u64,
    pub repo: String,
    pub number: u64,
    pub title: String,
    pub reason: Reason,
    pub direction: Direction,
    pub draft: bool,
    pub author: String,
    pub url: String,
    pub date: String,
}

#[derive(Deserialize)]
struct RawUser {
    login: String,
    name: Option<String>,
}

#[derive(Deserialize)]
struct SearchResponse {
    #[serde(default)]
    items: Vec<RawItem>,
}

#[derive(Debug, Deserialize)]
struct RawItem {
    id: u64,
    number: u64,
    #[serde(default)]
    title: String,
    html_url: String,
    repository_url: String,
    user: Option<RawLogin>,
    #[serde(default)]
    draft: bool,
    #[serde(default)]
    updated_at: String,
}

#[derive(Debug, Deserialize)]
struct RawLogin {
    login: String,
}

#[derive(Deserialize, Default)]
struct ErrorBody {
    message: Option<String>,
}

async fn get<T: DeserializeOwned>(
    http: &reqwest::Client,
    token: &str,
    url: &str,
    query: &[(&str, &str)],
) -> Result<T> {
    let response = http
        .get(url)
        .query(query)
        .bearer_auth(token)
        .header("Accept", "application/vnd.github+json")
        .header("X-GitHub-Api-Version", API_VERSION)
        .send()
        .await?;
    let status = response.status();
    if status.is_success() {
        return Ok(response.json().await?);
    }
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(Error::Reauthorize("GitHub"));
    }
    let body: ErrorBody = response.json().await.unwrap_or_default();
    Err(Error::Api {
        service: "GitHub",
        status: status.as_u16(),
        message: body
            .message
            .unwrap_or_else(|| status.canonical_reason().unwrap_or("unknown error").into()),
    })
}

/// Checks the token and identifies the user.
pub async fn connect(http: &reqwest::Client, endpoint: &Endpoint, token: &str) -> Result<Me> {
    match get::<RawUser>(http, token, &format!("{}/user", endpoint.api_base), &[]).await {
        Ok(user) => Ok(Me {
            name: user
                .name
                .filter(|n| !n.trim().is_empty())
                .unwrap_or_else(|| user.login.clone()),
            login: user.login,
        }),
        Err(Error::Reauthorize(_)) => Err(Error::Auth(
            "GitHub rejected the token. Check it, and its expiry.".into(),
        )),
        Err(Error::Api { status: 404, .. }) => Err(Error::Auth(format!(
            "no GitHub API was found at {}. Check the server address.",
            endpoint.host()
        ))),
        Err(e) => Err(e),
    }
}

/// Open pull requests that request the user's review, are assigned to the
/// user, or were opened by the user, most recently updated first.
pub async fn open_pull_requests(
    http: &reqwest::Client,
    endpoint: &Endpoint,
    token: &str,
) -> Result<Vec<PullMeta>> {
    let url = format!("{}/search/issues", endpoint.api_base);
    let mut found = Vec::new();
    for (query, reason) in QUERIES {
        let response: SearchResponse = get(
            http,
            token,
            &url,
            &[
                ("q", query),
                ("sort", "updated"),
                ("order", "desc"),
                ("per_page", PER_QUERY),
            ],
        )
        .await?;
        found.extend(response.items.into_iter().map(|item| (item, reason)));
    }
    Ok(merge(found))
}

/// One entry per pull request. When a pull request matches several queries,
/// the first reason wins: a review request outranks an assignment, which
/// outranks authorship.
fn merge(found: Vec<(RawItem, Reason)>) -> Vec<PullMeta> {
    let mut by_id: HashMap<u64, PullMeta> = HashMap::new();
    for (item, reason) in found {
        by_id
            .entry(item.id)
            .or_insert_with(|| to_meta(item, reason));
    }
    let mut pulls: Vec<PullMeta> = by_id.into_values().collect();
    pulls.sort_by(|a, b| b.date.cmp(&a.date).then(a.pr_id.cmp(&b.pr_id)));
    pulls
}

fn to_meta(item: RawItem, reason: Reason) -> PullMeta {
    PullMeta {
        repo: repo_name(&item.repository_url),
        reason,
        direction: reason.direction(),
        author: item.user.map(|u| u.login).unwrap_or_default(),
        title: item.title.trim().to_owned(),
        pr_id: item.id,
        number: item.number,
        draft: item.draft,
        url: item.html_url,
        date: item.updated_at,
    }
}

/// `https://api.github.com/repos/acme/web` → `acme/web`.
fn repo_name(repository_url: &str) -> String {
    repository_url
        .split("/repos/")
        .nth(1)
        .unwrap_or(repository_url)
        .to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn item(json: &str) -> RawItem {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn endpoints_for_github_com_and_enterprise() {
        let dotcom = Endpoint::for_server(None).unwrap();
        assert_eq!(dotcom.api_base, "https://api.github.com");
        assert_eq!(Endpoint::for_server(Some("  ")).unwrap(), dotcom);
        assert_eq!(
            Endpoint::for_server(Some("https://github.com/")).unwrap(),
            dotcom
        );

        let ghes = Endpoint::for_server(Some("github.acme.com/")).unwrap();
        assert_eq!(ghes.api_base, "https://github.acme.com/api/v3");
        assert_eq!(ghes.web_base, "https://github.acme.com");
        assert_eq!(ghes.host(), "github.acme.com");

        assert!(Endpoint::for_server(Some("http://github.acme.com")).is_err());
    }

    #[test]
    fn every_query_names_pull_requests() {
        assert!(QUERIES.iter().all(|(q, _)| q.starts_with("is:pr ")));
    }

    #[test]
    fn parses_search_items() {
        let meta = to_meta(
            item(
                r#"{"id":11,"number":42,"title":" Add retries ","draft":true,
                    "html_url":"https://github.com/acme/web/pull/42",
                    "repository_url":"https://api.github.com/repos/acme/web",
                    "user":{"login":"ana"},"updated_at":"2026-10-23T10:00:00Z",
                    "pull_request":{"url":"x"}}"#,
            ),
            Reason::ReviewRequested,
        );
        assert_eq!(meta.repo, "acme/web");
        assert_eq!(meta.title, "Add retries");
        assert_eq!(meta.direction, Direction::Inbound);
        assert!(meta.draft);
        assert_eq!(meta.author, "ana");
    }

    #[test]
    fn merges_duplicates_keeping_the_strongest_reason() {
        let raw = |id: u64, date: &str| {
            item(&format!(
                r#"{{"id":{id},"number":{id},"title":"t","html_url":"u",
                    "repository_url":"https://ghe.acme.com/api/v3/repos/acme/api",
                    "updated_at":"{date}"}}"#
            ))
        };
        let pulls = merge(vec![
            (raw(1, "2026-10-20T00:00:00Z"), Reason::ReviewRequested),
            (raw(2, "2026-10-22T00:00:00Z"), Reason::Assigned),
            (raw(1, "2026-10-20T00:00:00Z"), Reason::Assigned),
            (raw(3, "2026-10-21T00:00:00Z"), Reason::Authored),
        ]);
        let got: Vec<_> = pulls.iter().map(|p| (p.pr_id, p.reason)).collect();
        assert_eq!(
            got,
            [
                (2, Reason::Assigned),
                (3, Reason::Authored),
                (1, Reason::ReviewRequested)
            ]
        );
        assert_eq!(pulls[1].direction, Direction::Outbound);
        assert_eq!(pulls[0].repo, "acme/api");
    }
}
