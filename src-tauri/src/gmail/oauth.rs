//! Google OAuth 2.0 for desktop apps: authorization code flow with PKCE and a
//! loopback redirect (RFC 8252). The browser does the sign-in, so SilentDesk
//! never sees the user's password, and SSO or MFA work as usual.

use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;
use url::Url;

use crate::error::{Error, Result};
use crate::secrets::random_bytes;

const AUTH_URL: &str = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL: &str = "https://oauth2.googleapis.com/token";
const REVOKE_URL: &str = "https://oauth2.googleapis.com/revoke";

/// Read-only access to message headers and labels. No bodies, no attachments,
/// no sending.
pub const GMAIL_SCOPE: &str = "https://www.googleapis.com/auth/gmail.metadata";

const SIGN_IN_TIMEOUT: Duration = Duration::from_secs(180);
const MAX_REQUEST_BYTES: usize = 8 * 1024;
const READ_TIMEOUT: Duration = Duration::from_secs(5);

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
        let read = |name: &str, built_in: Option<&str>| {
            std::env::var(name)
                .ok()
                .or_else(|| built_in.map(str::to_owned))
                .filter(|v| !v.trim().is_empty())
        };
        let client_id = read(
            "SILENTDESK_GOOGLE_CLIENT_ID",
            option_env!("SILENTDESK_GOOGLE_CLIENT_ID"),
        )?;
        let client_secret = read(
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

struct Pkce {
    verifier: String,
    challenge: String,
}

fn pkce() -> Pkce {
    let verifier = URL_SAFE_NO_PAD.encode(random_bytes::<32>());
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    Pkce {
        verifier,
        challenge,
    }
}

fn authorization_url(
    client: &OAuthClient,
    redirect_uri: &str,
    challenge: &str,
    state: &str,
) -> String {
    let mut url = Url::parse(AUTH_URL).expect("valid constant URL");
    url.query_pairs_mut()
        .append_pair("client_id", &client.client_id)
        .append_pair("redirect_uri", redirect_uri)
        .append_pair("response_type", "code")
        .append_pair("scope", GMAIL_SCOPE)
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
    open_browser: impl FnOnce(&str) -> Result<()>,
) -> Result<Tokens> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await?;
    let redirect_uri = format!("http://127.0.0.1:{}", listener.local_addr()?.port());
    let pkce = pkce();
    let state = URL_SAFE_NO_PAD.encode(random_bytes::<16>());

    open_browser(&authorization_url(
        client,
        &redirect_uri,
        &pkce.challenge,
        &state,
    ))?;

    let code = tokio::time::timeout(SIGN_IN_TIMEOUT, receive_code(&listener, &state))
        .await
        .map_err(|_| Error::AuthTimeout)??;
    drop(listener);

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
    let token = token_request(http, &form).await?;

    if !token.scope.split_whitespace().any(|s| s == GMAIL_SCOPE) {
        return Err(Error::Auth("Gmail access was not granted.".into()));
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
    Ok(token_request(http, &form).await?.access_token)
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

async fn token_request(http: &reqwest::Client, form: &[(&str, &str)]) -> Result<TokenResponse> {
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
        "invalid_grant" => Error::Reauthorize,
        "invalid_client" | "unauthorized_client" => Error::Auth(
            "Google rejected the OAuth client. Check SILENTDESK_GOOGLE_CLIENT_ID and \
             SILENTDESK_GOOGLE_CLIENT_SECRET."
                .into(),
        ),
        _ => Error::Auth(format!("Google returned {error} ({status}).")),
    })
}

/// Accepts connections on the loopback listener until one carries the OAuth
/// redirect. Other requests (a browser's favicon fetch, for example) get 404.
async fn receive_code(listener: &TcpListener, expected_state: &str) -> Result<String> {
    loop {
        let (mut stream, _) = listener.accept().await?;
        let mut buf = vec![0u8; MAX_REQUEST_BYTES];
        let mut len = 0;
        while len < buf.len() && !buf[..len].windows(4).any(|w| w == b"\r\n\r\n") {
            match tokio::time::timeout(READ_TIMEOUT, stream.read(&mut buf[len..])).await {
                Ok(Ok(n)) if n > 0 => len += n,
                _ => break,
            }
        }
        let request = String::from_utf8_lossy(&buf[..len]);
        let request_line = request.lines().next().unwrap_or_default();

        let Some(outcome) = parse_callback(request_line, expected_state) else {
            let _ = stream
                .write_all(
                    b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                )
                .await;
            continue;
        };
        let message = match &outcome {
            Ok(_) => "Sign-in received. You can close this tab and return to SilentDesk.",
            Err(_) => "Sign-in did not complete. Return to SilentDesk for details.",
        };
        let body = format!(
            "<!doctype html><meta charset=utf-8><title>SilentDesk</title>\
             <body style=\"font-family:system-ui;margin:3rem\"><p>{message}</p>"
        );
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\
             Content-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n{body}",
            body.len()
        );
        let _ = stream.write_all(response.as_bytes()).await;
        return outcome;
    }
}

/// Parses `GET /?code=...&state=... HTTP/1.1`. Returns `None` when the
/// request is not an OAuth redirect at all.
fn parse_callback(request_line: &str, expected_state: &str) -> Option<Result<String>> {
    let mut parts = request_line.split_whitespace();
    if parts.next()? != "GET" {
        return None;
    }
    let url = Url::parse(&format!("http://127.0.0.1{}", parts.next()?)).ok()?;
    if url.path() != "/" {
        return None;
    }
    let param = |name: &str| {
        url.query_pairs()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.into_owned())
    };
    let (code, error, state) = (param("code"), param("error"), param("state"));
    if code.is_none() && error.is_none() {
        return None;
    }
    if state.as_deref() != Some(expected_state) {
        return Some(Err(Error::Auth(
            "the sign-in response did not match this request.".into(),
        )));
    }
    if let Some(error) = error {
        let reason = if error == "access_denied" {
            "access was denied.".into()
        } else {
            error
        };
        return Some(Err(Error::Auth(reason)));
    }
    code.map(Ok)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pkce_challenge_is_s256_of_verifier() {
        let p = pkce();
        assert_eq!(p.verifier.len(), 43);
        let expected = URL_SAFE_NO_PAD.encode(Sha256::digest(p.verifier.as_bytes()));
        assert_eq!(p.challenge, expected);
    }

    #[test]
    fn rfc7636_example() {
        // Appendix B of RFC 7636.
        let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(
            b"dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        ));
        assert_eq!(challenge, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
    }

    #[test]
    fn authorization_url_has_required_parameters() {
        let client = OAuthClient {
            client_id: "abc.apps.googleusercontent.com".into(),
            client_secret: None,
        };
        let url = Url::parse(&authorization_url(
            &client,
            "http://127.0.0.1:5000",
            "chal",
            "st",
        ))
        .unwrap();
        let q: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(q["client_id"], "abc.apps.googleusercontent.com");
        assert_eq!(q["redirect_uri"], "http://127.0.0.1:5000");
        assert_eq!(q["scope"], GMAIL_SCOPE);
        assert_eq!(q["code_challenge_method"], "S256");
        assert_eq!(q["state"], "st");
        assert_eq!(q["access_type"], "offline");
    }

    #[test]
    fn parses_callback() {
        let ok = parse_callback("GET /?state=s1&code=4%2Fabc&scope=x HTTP/1.1", "s1");
        assert_eq!(ok.unwrap().unwrap(), "4/abc");

        let wrong_state = parse_callback("GET /?state=other&code=abc HTTP/1.1", "s1");
        assert!(matches!(wrong_state, Some(Err(Error::Auth(_)))));

        let denied = parse_callback("GET /?state=s1&error=access_denied HTTP/1.1", "s1");
        assert!(matches!(denied, Some(Err(Error::Auth(_)))));

        assert!(parse_callback("GET /favicon.ico HTTP/1.1", "s1").is_none());
        assert!(parse_callback("GET / HTTP/1.1", "s1").is_none());
        assert!(parse_callback("POST /?code=a&state=s1 HTTP/1.1", "s1").is_none());
        assert!(parse_callback("", "s1").is_none());
    }

    #[tokio::test]
    async fn loopback_receives_code_after_unrelated_request() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let browser = tokio::spawn(async move {
            for path in ["/favicon.ico", "/?code=the-code&state=s1"] {
                let mut s = tokio::net::TcpStream::connect(("127.0.0.1", port))
                    .await
                    .unwrap();
                s.write_all(format!("GET {path} HTTP/1.1\r\nHost: x\r\n\r\n").as_bytes())
                    .await
                    .unwrap();
                let mut response = String::new();
                s.read_to_string(&mut response).await.unwrap();
            }
        });
        let code = receive_code(&listener, "s1").await.unwrap();
        assert_eq!(code, "the-code");
        browser.await.unwrap();
    }
}
