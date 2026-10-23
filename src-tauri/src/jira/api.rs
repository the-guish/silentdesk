//! Jira REST calls, read-only. Works with Jira Cloud (account email plus API
//! token, scoped or not) and Jira Data Center (personal access token).

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use time::format_description::well_known::Rfc3339;
use time::macros::format_description;
use time::{OffsetDateTime, PrimitiveDateTime, UtcOffset};
use url::Url;

use crate::error::{Error, Result};
use crate::model::Direction;

const GATEWAY: &str = "https://api.atlassian.com/ex/jira";

/// Open issues assigned to or reported by the user, most recently updated
/// first.
const JQL: &str = "(assignee = currentUser() OR reporter = currentUser()) \
                   AND statusCategory != Done ORDER BY updated DESC";
const FIELDS: &str = "summary,status,assignee,reporter,updated,project";

/// What is kept in the OS credential store. With an email it is a Jira
/// Cloud API token (HTTP Basic); without, a Data Center personal access
/// token (Bearer).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Credential {
    pub email: Option<String>,
    pub token: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum Flavor {
    Cloud,
    DataCenter,
}

/// Where and how to call the API, decided once at connect time.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Endpoint {
    /// The site people browse, e.g. `https://acme.atlassian.net`.
    pub site: String,
    /// The site itself, or the Atlassian gateway for scoped Cloud tokens.
    pub api_base: String,
    pub flavor: Flavor,
}

impl Endpoint {
    fn url(&self, path: &str) -> String {
        let version = match self.flavor {
            Flavor::Cloud => "3",
            Flavor::DataCenter => "2",
        };
        format!("{}/rest/api/{version}/{path}", self.api_base)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Me {
    /// Cloud account ID, or the Data Center user key.
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct IssueMeta {
    pub issue_id: String,
    pub key: String,
    pub summary: String,
    pub direction: Direction,
    pub status: String,
    pub project: String,
    pub assignee: String,
    pub reporter: String,
    pub url: String,
    pub date: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct RawUser {
    account_id: Option<String>,
    key: Option<String>,
    name: Option<String>,
    #[serde(default)]
    display_name: String,
}

impl RawUser {
    fn id(&self) -> Option<&str> {
        self.account_id
            .as_deref()
            .or(self.key.as_deref())
            .or(self.name.as_deref())
    }
}

#[derive(Deserialize)]
struct SearchResponse {
    #[serde(default)]
    issues: Vec<RawIssue>,
}

#[derive(Deserialize)]
struct RawIssue {
    id: String,
    key: String,
    fields: RawFields,
}

#[derive(Deserialize)]
struct RawFields {
    #[serde(default)]
    summary: String,
    status: Option<Named>,
    project: Option<RawProject>,
    assignee: Option<RawUser>,
    reporter: Option<RawUser>,
    updated: Option<String>,
}

#[derive(Deserialize)]
struct Named {
    name: String,
}

#[derive(Deserialize)]
struct RawProject {
    key: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct TenantInfo {
    cloud_id: String,
}

#[derive(Deserialize, Default)]
#[serde(rename_all = "camelCase")]
struct ErrorBody {
    #[serde(default)]
    error_messages: Vec<String>,
    message: Option<String>,
}

/// Accepts `acme.atlassian.net`, `https://acme.atlassian.net/` or a Data
/// Center URL with a context path, and returns it as `https://host[/path]`.
/// Plain `http` is refused: tokens never travel unencrypted.
pub fn normalize_site(input: &str) -> Result<String> {
    let input = input.trim();
    let with_scheme = if input.contains("://") {
        input.to_owned()
    } else {
        format!("https://{input}")
    };
    let url = Url::parse(&with_scheme)
        .map_err(|_| Error::Auth("the Jira site address is not valid.".into()))?;
    if url.scheme() != "https" {
        return Err(Error::Auth("the Jira site must use https://.".into()));
    }
    let host = url
        .host_str()
        .ok_or_else(|| Error::Auth("the Jira site address is not valid.".into()))?;
    let port = url.port().map(|p| format!(":{p}")).unwrap_or_default();
    let path = url.path().trim_end_matches('/');
    Ok(format!("https://{host}{port}{path}"))
}

fn is_cloud_site(site: &str) -> bool {
    Url::parse(site)
        .ok()
        .and_then(|u| u.host_str().map(|h| h.ends_with(".atlassian.net")))
        .unwrap_or(false)
}

async fn get<T: DeserializeOwned>(
    http: &reqwest::Client,
    credential: &Credential,
    url: &str,
    query: &[(&str, &str)],
) -> Result<T> {
    let request = http
        .get(url)
        .query(query)
        .header("Accept", "application/json");
    let request = match &credential.email {
        Some(email) => request.basic_auth(email, Some(&credential.token)),
        None => request.bearer_auth(&credential.token),
    };
    let response = request.send().await?;
    let status = response.status();
    if status.is_success() {
        return Ok(response.json().await?);
    }
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(Error::Reauthorize("Jira"));
    }
    let body: ErrorBody = response.json().await.unwrap_or_default();
    let message = body
        .error_messages
        .into_iter()
        .next()
        .or(body.message)
        .unwrap_or_else(|| status.canonical_reason().unwrap_or("unknown error").into());
    Err(Error::Api {
        service: "Jira",
        status: status.as_u16(),
        message,
    })
}

async fn myself(
    http: &reqwest::Client,
    credential: &Credential,
    endpoint: &Endpoint,
) -> Result<Me> {
    let user: RawUser = get(http, credential, &endpoint.url("myself"), &[]).await?;
    let id = user
        .id()
        .ok_or_else(|| Error::Auth("Jira did not identify the user.".into()))?
        .to_owned();
    Ok(Me {
        id,
        name: user.display_name,
    })
}

/// Finds a working endpoint for this credential and identifies the user.
/// Cloud tokens are tried against the site first; a scoped token is only
/// accepted by the Atlassian gateway, so on 401 the site's cloud ID is
/// looked up and the gateway is tried.
pub async fn connect(
    http: &reqwest::Client,
    site: &str,
    credential: &Credential,
) -> Result<(Endpoint, Me)> {
    let flavor = if credential.email.is_some() {
        Flavor::Cloud
    } else {
        Flavor::DataCenter
    };
    let direct = Endpoint {
        site: site.to_owned(),
        api_base: site.to_owned(),
        flavor,
    };
    let rejected =
        || Error::Auth("Jira rejected the token. Check the site, email and API token.".into());
    match myself(http, credential, &direct).await {
        Ok(me) => return Ok((direct, me)),
        Err(Error::Reauthorize(_)) if flavor == Flavor::Cloud && is_cloud_site(site) => {}
        Err(Error::Reauthorize(_)) => return Err(rejected()),
        Err(Error::Api { status: 404, .. }) => {
            return Err(Error::Auth(format!(
                "no Jira was found at {site}. Check the site address."
            )));
        }
        Err(e) => return Err(e),
    }

    let tenant: TenantInfo = http
        .get(format!("{site}/_edge/tenant_info"))
        .send()
        .await?
        .json()
        .await
        .map_err(|_| rejected())?;
    let gateway = Endpoint {
        site: site.to_owned(),
        api_base: format!("{GATEWAY}/{}", tenant.cloud_id),
        flavor,
    };
    match myself(http, credential, &gateway).await {
        Ok(me) => Ok((gateway, me)),
        Err(Error::Reauthorize(_)) => Err(rejected()),
        Err(e) => Err(e),
    }
}

/// The `count` most recently updated open issues assigned to or reported by
/// the user.
pub async fn open_issues(
    http: &reqwest::Client,
    credential: &Credential,
    endpoint: &Endpoint,
    me: &str,
    count: usize,
) -> Result<Vec<IssueMeta>> {
    // Jira Cloud replaced /search with /search/jql; Data Center keeps /search.
    let path = match endpoint.flavor {
        Flavor::Cloud => "search/jql",
        Flavor::DataCenter => "search",
    };
    let max = count.to_string();
    let response: SearchResponse = get(
        http,
        credential,
        &endpoint.url(path),
        &[("jql", JQL), ("maxResults", &max), ("fields", FIELDS)],
    )
    .await?;
    Ok(response
        .issues
        .into_iter()
        .take(count)
        .map(|issue| to_meta(issue, me, &endpoint.site))
        .collect())
}

fn to_meta(issue: RawIssue, me: &str, site: &str) -> IssueMeta {
    let f = issue.fields;
    let assigned_to_me = f.assignee.as_ref().and_then(RawUser::id) == Some(me);
    let name = |u: Option<RawUser>| u.map(|u| u.display_name).unwrap_or_default();
    IssueMeta {
        url: format!("{site}/browse/{}", issue.key),
        direction: if assigned_to_me {
            Direction::Inbound
        } else {
            Direction::Outbound
        },
        status: f.status.map(|s| s.name).unwrap_or_default(),
        project: f.project.map(|p| p.key).unwrap_or_default(),
        assignee: name(f.assignee),
        reporter: name(f.reporter),
        date: f.updated.as_deref().map(to_rfc3339).unwrap_or_default(),
        summary: f.summary.trim().to_owned(),
        issue_id: issue.id,
        key: issue.key,
    }
}

/// Jira dates look like `2026-10-23T10:00:00.000+0200`. Returns UTC RFC 3339.
fn to_rfc3339(jira: &str) -> String {
    let format = format_description!(
        "[year]-[month]-[day]T[hour]:[minute]:[second].[subsecond][offset_hour sign:mandatory][offset_minute]"
    );
    OffsetDateTime::parse(jira, format)
        .or_else(|_| OffsetDateTime::parse(jira, &Rfc3339))
        .or_else(|_| {
            PrimitiveDateTime::parse(jira, format).map(|d| d.assume_offset(UtcOffset::UTC))
        })
        .ok()
        .and_then(|d| d.to_offset(UtcOffset::UTC).format(&Rfc3339).ok())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn issue(json: &str) -> RawIssue {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn normalizes_sites() {
        assert_eq!(
            normalize_site("acme.atlassian.net").unwrap(),
            "https://acme.atlassian.net"
        );
        assert_eq!(
            normalize_site(" https://acme.atlassian.net/ ").unwrap(),
            "https://acme.atlassian.net"
        );
        assert_eq!(
            normalize_site("https://jira.corp.example:8443/jira/").unwrap(),
            "https://jira.corp.example:8443/jira"
        );
        assert!(normalize_site("http://jira.corp.example").is_err());
        assert!(normalize_site("https://").is_err());
    }

    #[test]
    fn recognizes_cloud_sites() {
        assert!(is_cloud_site("https://acme.atlassian.net"));
        assert!(!is_cloud_site("https://jira.corp.example"));
    }

    #[test]
    fn builds_versioned_urls() {
        let cloud = Endpoint {
            site: "https://acme.atlassian.net".into(),
            api_base: format!("{GATEWAY}/abc"),
            flavor: Flavor::Cloud,
        };
        assert_eq!(
            cloud.url("search/jql"),
            "https://api.atlassian.com/ex/jira/abc/rest/api/3/search/jql"
        );
        let dc = Endpoint {
            site: "https://jira.corp.example/jira".into(),
            api_base: "https://jira.corp.example/jira".into(),
            flavor: Flavor::DataCenter,
        };
        assert_eq!(
            dc.url("myself"),
            "https://jira.corp.example/jira/rest/api/2/myself"
        );
    }

    #[test]
    fn parses_cloud_issue_assigned_to_me() {
        let meta = to_meta(
            issue(
                r#"{"id":"10001","key":"PAY-42","fields":{
                    "summary":" Refund fails for EUR ","status":{"name":"In Progress"},
                    "project":{"key":"PAY"},
                    "assignee":{"accountId":"me-1","displayName":"Luis Castro"},
                    "reporter":{"accountId":"ana-2","displayName":"Ana Ruiz"},
                    "updated":"2026-10-23T12:00:00.000+0200"}}"#,
            ),
            "me-1",
            "https://acme.atlassian.net",
        );
        assert_eq!(meta.direction, Direction::Inbound);
        assert_eq!(meta.summary, "Refund fails for EUR");
        assert_eq!(meta.status, "In Progress");
        assert_eq!(meta.reporter, "Ana Ruiz");
        assert_eq!(meta.url, "https://acme.atlassian.net/browse/PAY-42");
        assert_eq!(meta.date, "2026-10-23T10:00:00Z");
    }

    #[test]
    fn parses_data_center_issue_reported_by_me_and_unassigned() {
        let meta = to_meta(
            issue(
                r#"{"id":"2","key":"OPS-7","fields":{"summary":"Rotate certs",
                    "status":{"name":"Open"},"assignee":null,
                    "reporter":{"key":"JIRAUSER10","name":"luis","displayName":"Luis"},
                    "updated":"2026-10-22T08:30:00.000+0000"}}"#,
            ),
            "JIRAUSER10",
            "https://jira.corp.example",
        );
        assert_eq!(meta.direction, Direction::Outbound);
        assert_eq!(meta.assignee, "");
        assert_eq!(meta.project, "");
        assert_eq!(meta.date, "2026-10-22T08:30:00Z");
    }

    #[test]
    fn credential_round_trips_as_json() {
        let c = Credential {
            email: Some("me@example.com".into()),
            token: "t".into(),
        };
        let json = serde_json::to_vec(&c).unwrap();
        assert_eq!(serde_json::from_slice::<Credential>(&json).unwrap(), c);
    }
}
