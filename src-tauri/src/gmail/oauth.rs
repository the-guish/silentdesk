//! Google sign-in: authorization code flow with PKCE and a loopback redirect
//! on any free port. Shared by every Google service; each one asks for its
//! own grant and keeps its own refresh token.

use serde::Deserialize;
use url::Url;

use crate::error::{Error, Result};
use crate::oauth::{self, Loopback};

const AUTH_URL: &str = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL: &str = "https://oauth2.googleapis.com/token";
const REVOKE_URL: &str = "https://oauth2.googleapis.com/revoke";

/// What one SilentDesk service asks Google for.
pub struct Grant {
    /// Named in errors, e.g. "Gmail access was not granted."
    pub service: &'static str,
    /// Requested at sign-in.
    pub scopes: &'static [&'static str],
    /// Must all be granted; the user can untick scopes on Google's consent
    /// screen.
    pub required: &'static [&'static str],
}

/// `gmail.modify` reads headers and moves messages to the trash; it cannot
/// delete them for good. `gmail.send` sends replies.
pub const GMAIL: Grant = Grant {
    service: "Gmail",
    scopes: &[
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ],
    required: &[
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ],
};

/// The OAuth client the organization registered in Google Cloud. Read at
/// runtime from the environment, or baked in at build time.
#[derive(Clone)]
pub struct OAuthClient {
    pub client_id: String,
    /// Google issues a secret for desktop clients but does not treat it as
    /// confidential; PKCE protects the flow.
    pub client_secret: Option<String>,
}

impl OAuthClient {
    pub fn from_env() -> Option<Self> {
        let client_id = oauth::setting(
            "SILENTDESK_GOOGLE_CLIENT_ID",
            option_env!("SILENTDESK_GOOGLE_CLIENT_ID"),
        )?;
        let client_secret = oauth::setting(
            "SILENTDESK_GOOGLE_CLIENT_SECRET",
            option_env!("SILENTDESK_GOOGLE_CLIENT_SECRET"),
        );
        Some(Self {
            client_id,
            client_secret,
        })
    }
}

pub struct Tokens {
    pub access_token: String,
    pub refresh_token: String,
}

#[derive(Deserialize)]
struct TokenResponse {
    access_token: String,
    refresh_token: Option<String>,
    #[serde(default)]
    scope: String,
}

#[derive(Deserialize)]
struct TokenError {
    error: String,
}

fn authorization_url(
    client: &OAuthClient,
    grant: &Grant,
    redirect_uri: &str,
    challenge: &str,
    state: &str,
) -> String {
    let mut url = Url::parse(AUTH_URL).expect("valid constant URL");
    url.query_pairs_mut()
        .append_pair("client_id", &client.client_id)
        .append_pair("redirect_uri", redirect_uri)
        .append_pair("response_type", "code")
        .append_pair("scope", &grant.scopes.join(" "))
        .append_pair("code_challenge", challenge)
        .append_pair("code_challenge_method", "S256")
        .append_pair("state", state)
        .append_pair("access_type", "offline")
        .append_pair("prompt", "consent");
    url.into()
}

/// Runs the full sign-in: opens the browser via `open_browser`, waits for
/// Google to redirect back to the loopback listener, and exchanges the code.
pub async fn authorize(
    http: &reqwest::Client,
    client: &OAuthClient,
    grant: &Grant,
    open_browser: impl FnOnce(&str) -> Result<()>,
) -> Result<Tokens> {
    let loopback = Loopback::any_port().await?;
    let redirect_uri = loopback.redirect_uri.clone();
    let pkce = oauth::pkce();
    let state = oauth::state();

    open_browser(&authorization_url(
        client,
        grant,
        &redirect_uri,
        &pkce.challenge,
        &state,
    ))?;
    let code = loopback.wait_for_code(&state).await?;

    let mut form = vec![
        ("grant_type", "authorization_code"),
        ("code", code.as_str()),
        ("code_verifier", pkce.verifier.as_str()),
        ("redirect_uri", redirect_uri.as_str()),
        ("client_id", client.client_id.as_str()),
    ];
    if let Some(secret) = &client.client_secret {
        form.push(("client_secret", secret));
    }
    let token = token_request(http, &form, grant.service).await?;

    let granted: Vec<&str> = token.scope.split_whitespace().collect();
    if !grant.required.iter().all(|s| granted.contains(s)) {
        return Err(Error::Auth(format!(
            "{} access was not granted.",
            grant.service
        )));
    }
    let refresh_token = token
        .refresh_token
        .ok_or_else(|| Error::Auth("Google did not return a refresh token.".into()))?;
    Ok(Tokens {
        access_token: token.access_token,
        refresh_token,
    })
}

/// Exchanges a refresh token for a short-lived access token.
pub async fn access_token(
    http: &reqwest::Client,
    client: &OAuthClient,
    grant: &Grant,
    refresh_token: &str,
) -> Result<String> {
    let mut form = vec![
        ("grant_type", "refresh_token"),
        ("refresh_token", refresh_token),
        ("client_id", client.client_id.as_str()),
    ];
    if let Some(secret) = &client.client_secret {
        form.push(("client_secret", secret));
    }
    Ok(token_request(http, &form, grant.service)
        .await?
        .access_token)
}

/// Asks Google to invalidate the grant. Best effort: the local token is
/// deleted either way.
pub async fn revoke(http: &reqwest::Client, refresh_token: &str) {
    let _ = http
        .post(REVOKE_URL)
        .form(&[("token", refresh_token)])
        .send()
        .await;
}

async fn token_request(
    http: &reqwest::Client,
    form: &[(&str, &str)],
    service: &'static str,
) -> Result<TokenResponse> {
    let response = http.post(TOKEN_URL).form(form).send().await?;
    if response.status().is_success() {
        return Ok(response.json().await?);
    }
    let status = response.status().as_u16();
    let error = response
        .json::<TokenError>()
        .await
        .map(|e| e.error)
        .unwrap_or_else(|_| "unknown_error".into());
    Err(match error.as_str() {
        "invalid_grant" => Error::Reauthorize(service),
        "invalid_client" | "unauthorized_client" => Error::Auth(
            "Google rejected the OAuth client. Check SILENTDESK_GOOGLE_CLIENT_ID and \
             SILENTDESK_GOOGLE_CLIENT_SECRET."
                .into(),
        ),
        _ => Error::Auth(format!("Google returned {error} ({status}).")),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authorization_url_has_required_parameters() {
        let client = OAuthClient {
            client_id: "abc.apps.googleusercontent.com".into(),
            client_secret: None,
        };
        let url = Url::parse(&authorization_url(
            &client,
            &GMAIL,
            "http://127.0.0.1:5000",
            "chal",
            "st",
        ))
        .unwrap();
        let q: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(q["client_id"], "abc.apps.googleusercontent.com");
        assert_eq!(q["redirect_uri"], "http://127.0.0.1:5000");
        assert_eq!(
            q["scope"],
            "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"
        );
        assert_eq!(q["code_challenge_method"], "S256");
        assert_eq!(q["state"], "st");
        assert_eq!(q["access_type"], "offline");
    }
}
