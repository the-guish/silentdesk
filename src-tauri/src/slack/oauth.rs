//! Slack sign-in for a desktop (public) client: OAuth v2 with PKCE and a
//! `localhost` redirect. The Slack app must have PKCE enabled, so no client
//! secret exists. Only user scopes are requested; desktop redirects cannot
//! request bot scopes.

use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use url::Url;

use crate::error::{Error, Result};
use crate::oauth::{self, Loopback};

const AUTHORIZE_URL: &str = "https://slack.com/oauth/v2/authorize";
const ACCESS_URL: &str = "https://slack.com/api/oauth.v2.access";
const REVOKE_URL: &str = "https://slack.com/api/auth.revoke";

/// `search:read` finds recent direct messages; `users:read` turns user IDs
/// into names. Nothing is written to Slack.
pub const USER_SCOPES: &[&str] = &["search:read", "users:read"];

pub const DEFAULT_REDIRECT_PORT: u16 = 47615;
pub const CALLBACK_PATH: &str = "/slack/callback";
const PORT_VAR: &str = "SILENTDESK_SLACK_REDIRECT_PORT";

/// Refresh a little before the access token actually expires.
const EXPIRY_MARGIN_SECS: i64 = 60;

/// The Slack app the organization (or user) created. Read at runtime from
/// the environment, or baked in at build time.
#[derive(Clone)]
pub struct SlackClient {
    pub client_id: String,
    pub redirect_port: u16,
}

impl SlackClient {
    pub fn from_env() -> Option<Self> {
        let client_id = oauth::setting(
            "SILENTDESK_SLACK_CLIENT_ID",
            option_env!("SILENTDESK_SLACK_CLIENT_ID"),
        )?;
        let redirect_port = oauth::setting(PORT_VAR, option_env!("SILENTDESK_SLACK_REDIRECT_PORT"))
            .and_then(|p| p.trim().parse().ok())
            .unwrap_or(DEFAULT_REDIRECT_PORT);
        Some(Self {
            client_id,
            redirect_port,
        })
    }
}

/// What is kept in the OS credential store. Without token rotation Slack
/// issues a long-lived user token; with rotation, a 12-hour access token plus
/// a refresh token.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Credential {
    pub access_token: String,
    pub refresh_token: Option<String>,
    /// Unix seconds.
    pub expires_at: Option<i64>,
}

impl Credential {
    pub fn needs_refresh(&self, now: i64) -> bool {
        self.refresh_token.is_some()
            && self
                .expires_at
                .is_some_and(|at| now >= at - EXPIRY_MARGIN_SECS)
    }
}

pub fn now() -> i64 {
    OffsetDateTime::now_utc().unix_timestamp()
}

#[derive(Debug, Deserialize)]
struct AccessResponse {
    ok: bool,
    error: Option<String>,
    // Present on refresh responses.
    access_token: Option<String>,
    refresh_token: Option<String>,
    expires_in: Option<i64>,
    // Present on the initial exchange for user tokens.
    authed_user: Option<AuthedUser>,
}

#[derive(Debug, Deserialize)]
struct AuthedUser {
    access_token: Option<String>,
    refresh_token: Option<String>,
    expires_in: Option<i64>,
    #[serde(default)]
    scope: String,
}

impl AccessResponse {
    /// The user token, wherever this response carries it.
    fn credential(self, now: i64) -> Option<(Credential, String)> {
        let (access, refresh, expires_in, scope) = match self.authed_user {
            Some(u) if u.access_token.is_some() => {
                (u.access_token, u.refresh_token, u.expires_in, u.scope)
            }
            _ => (
                self.access_token,
                self.refresh_token,
                self.expires_in,
                String::new(),
            ),
        };
        Some((
            Credential {
                access_token: access?,
                refresh_token: refresh,
                expires_at: expires_in.map(|s| now + s),
            },
            scope,
        ))
    }
}

fn authorization_url(client_id: &str, redirect_uri: &str, challenge: &str, state: &str) -> String {
    let mut url = Url::parse(AUTHORIZE_URL).expect("valid constant URL");
    url.query_pairs_mut()
        .append_pair("client_id", client_id)
        .append_pair("user_scope", &USER_SCOPES.join(","))
        .append_pair("redirect_uri", redirect_uri)
        .append_pair("state", state)
        .append_pair("code_challenge", challenge)
        .append_pair("code_challenge_method", "S256");
    url.into()
}

/// Runs the full sign-in: opens the browser via `open_browser`, waits for
/// Slack to redirect back to the loopback listener, and exchanges the code.
pub async fn authorize(
    http: &reqwest::Client,
    client: &SlackClient,
    open_browser: impl FnOnce(&str) -> Result<()>,
) -> Result<Credential> {
    let loopback = Loopback::fixed(client.redirect_port, CALLBACK_PATH, PORT_VAR).await?;
    let redirect_uri = loopback.redirect_uri.clone();
    let pkce = oauth::pkce();
    let state = oauth::state();

    open_browser(&authorization_url(
        &client.client_id,
        &redirect_uri,
        &pkce.challenge,
        &state,
    ))?;
    let code = loopback.wait_for_code(&state).await?;

    let response = access(
        http,
        &[
            ("grant_type", "authorization_code"),
            ("client_id", &client.client_id),
            ("code", &code),
            ("code_verifier", &pkce.verifier),
            ("redirect_uri", &redirect_uri),
        ],
        client,
    )
    .await?;
    let (credential, scope) = response
        .credential(now())
        .ok_or_else(|| Error::Auth("Slack did not return a user token.".into()))?;

    let granted: Vec<&str> = scope.split(',').map(str::trim).collect();
    if !USER_SCOPES.iter().all(|s| granted.contains(s)) {
        return Err(Error::Auth("Slack access was not fully granted.".into()));
    }
    Ok(credential)
}

/// Swaps the refresh token for a new access token. With token rotation,
/// Slack also returns a new refresh token, which replaces the old one.
pub async fn refresh(
    http: &reqwest::Client,
    client: &SlackClient,
    credential: &Credential,
) -> Result<Credential> {
    let refresh_token = credential
        .refresh_token
        .as_deref()
        .ok_or(Error::Reauthorize("Slack"))?;
    let response = access(
        http,
        &[
            ("grant_type", "refresh_token"),
            ("client_id", &client.client_id),
            ("refresh_token", refresh_token),
        ],
        client,
    )
    .await?;
    let (mut fresh, _) = response
        .credential(now())
        .ok_or(Error::Reauthorize("Slack"))?;
    if fresh.refresh_token.is_none() {
        fresh.refresh_token = credential.refresh_token.clone();
    }
    Ok(fresh)
}

/// Asks Slack to invalidate the token. Best effort: the local copy is
/// deleted either way.
pub async fn revoke(http: &reqwest::Client, access_token: &str) {
    let _ = http.post(REVOKE_URL).bearer_auth(access_token).send().await;
}

async fn access(
    http: &reqwest::Client,
    form: &[(&str, &str)],
    client: &SlackClient,
) -> Result<AccessResponse> {
    let response: AccessResponse = http
        .post(ACCESS_URL)
        .form(form)
        .send()
        .await?
        .json()
        .await?;
    if response.ok {
        return Ok(response);
    }
    let error = response.error.unwrap_or_else(|| "unknown_error".into());
    Err(match error.as_str() {
        "invalid_grant" | "invalid_refresh_token" | "token_expired" | "token_revoked" => {
            Error::Reauthorize("Slack")
        }
        "invalid_client_id" | "bad_client_secret" | "invalid_client" => Error::Auth(
            "Slack rejected the app. Check SILENTDESK_SLACK_CLIENT_ID, and that PKCE is \
             enabled for the Slack app."
                .into(),
        ),
        "invalid_code" | "code_already_used" => {
            Error::Auth("the sign-in code was invalid or expired. Try again.".into())
        }
        "bad_redirect_uri" => Error::Auth(format!(
            "the Slack app's redirect URL does not match. Add http://localhost:{}{} to it.",
            client.redirect_port, CALLBACK_PATH
        )),
        _ => Error::Auth(format!("Slack returned {error}.")),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authorization_url_requests_user_scopes_with_pkce() {
        let url = Url::parse(&authorization_url(
            "123.456",
            "http://localhost:47615/slack/callback",
            "chal",
            "st",
        ))
        .unwrap();
        let q: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(url.host_str(), Some("slack.com"));
        assert_eq!(q["client_id"], "123.456");
        assert_eq!(q["user_scope"], "search:read,users:read");
        assert!(
            !q.contains_key("scope"),
            "no bot scopes on a desktop redirect"
        );
        assert!(!q.contains_key("client_secret"));
        assert_eq!(q["redirect_uri"], "http://localhost:47615/slack/callback");
        assert_eq!(q["code_challenge_method"], "S256");
        assert_eq!(q["state"], "st");
    }

    #[test]
    fn reads_user_token_from_initial_exchange() {
        let r: AccessResponse = serde_json::from_str(
            r#"{"ok":true,"app_id":"A1","team":{"id":"T1","name":"Acme"},
                "authed_user":{"id":"U1","scope":"search:read,users:read",
                  "access_token":"xoxp-1","token_type":"user"}}"#,
        )
        .unwrap();
        let (c, scope) = r.credential(1000).unwrap();
        assert_eq!(c.access_token, "xoxp-1");
        assert_eq!(c.refresh_token, None);
        assert_eq!(c.expires_at, None);
        assert_eq!(scope, "search:read,users:read");
        assert!(!c.needs_refresh(i64::MAX));
    }

    #[test]
    fn reads_rotating_tokens() {
        let r: AccessResponse = serde_json::from_str(
            r#"{"ok":true,"authed_user":{"id":"U1","scope":"search:read,users:read",
                "access_token":"xoxe.xoxp-1","refresh_token":"xoxe-1-r","expires_in":43200}}"#,
        )
        .unwrap();
        let (c, _) = r.credential(1000).unwrap();
        assert_eq!(c.expires_at, Some(44200));
        assert!(!c.needs_refresh(1000));
        assert!(c.needs_refresh(44200 - 30));

        let refreshed: AccessResponse = serde_json::from_str(
            r#"{"ok":true,"access_token":"xoxe.xoxp-2","refresh_token":"xoxe-1-r2",
                "expires_in":43200,"token_type":"user"}"#,
        )
        .unwrap();
        let (c, _) = refreshed.credential(2000).unwrap();
        assert_eq!(c.access_token, "xoxe.xoxp-2");
        assert_eq!(c.refresh_token.as_deref(), Some("xoxe-1-r2"));
    }

    #[test]
    fn credential_round_trips_as_json() {
        let c = Credential {
            access_token: "a".into(),
            refresh_token: Some("r".into()),
            expires_at: Some(5),
        };
        let json = serde_json::to_vec(&c).unwrap();
        assert_eq!(serde_json::from_slice::<Credential>(&json).unwrap(), c);
    }
}
