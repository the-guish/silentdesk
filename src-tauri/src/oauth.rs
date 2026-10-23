//! OAuth 2.0 building blocks shared by every integration: PKCE (RFC 7636)
//! and the loopback redirect for native apps (RFC 8252). The browser does the
//! sign-in, so SilentDesk never sees the user's password, and SSO or MFA work
//! as usual.

use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;
use url::Url;

use crate::error::{Error, Result};
use crate::secrets::random_bytes;

const SIGN_IN_TIMEOUT: Duration = Duration::from_secs(180);
const MAX_REQUEST_BYTES: usize = 8 * 1024;
const READ_TIMEOUT: Duration = Duration::from_secs(5);

pub struct Pkce {
    pub verifier: String,
    pub challenge: String,
}

pub fn pkce() -> Pkce {
    let verifier = URL_SAFE_NO_PAD.encode(random_bytes::<32>());
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    Pkce {
        verifier,
        challenge,
    }
}

/// Reads a setting from the environment at runtime, falling back to a value
/// baked in at build time. Empty values count as unset.
pub fn setting(name: &str, built_in: Option<&str>) -> Option<String> {
    std::env::var(name)
        .ok()
        .or_else(|| built_in.map(str::to_owned))
        .filter(|v| !v.trim().is_empty())
}

/// An unguessable value tying the redirect to the request that started it.
pub fn state() -> String {
    URL_SAFE_NO_PAD.encode(random_bytes::<16>())
}

/// A one-shot HTTP listener on the loopback interface that waits for the
/// provider to redirect the browser back with an authorization code.
pub struct Loopback {
    listener: TcpListener,
    path: String,
    pub redirect_uri: String,
}

impl Loopback {
    /// Random free port, root path: `http://127.0.0.1:<port>`. For providers
    /// that accept any loopback port (Google).
    pub async fn any_port() -> Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await?;
        let redirect_uri = format!("http://127.0.0.1:{}", listener.local_addr()?.port());
        Ok(Self {
            listener,
            path: "/".into(),
            redirect_uri,
        })
    }

    /// Fixed port and path: `http://localhost:<port><path>`. For providers
    /// that match the registered redirect URL exactly (Slack).
    pub async fn fixed(port: u16, path: &str, port_var: &str) -> Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", port)).await.map_err(|e| {
            if e.kind() == std::io::ErrorKind::AddrInUse {
                Error::Auth(format!(
                    "port {port} is already in use. Set {port_var} to a free port and update \
                     the app's redirect URL to match."
                ))
            } else {
                e.into()
            }
        })?;
        Ok(Self {
            listener,
            path: path.into(),
            redirect_uri: format!("http://localhost:{port}{path}"),
        })
    }

    /// Waits for the redirect carrying `state`, up to the sign-in timeout.
    pub async fn wait_for_code(self, state: &str) -> Result<String> {
        tokio::time::timeout(
            SIGN_IN_TIMEOUT,
            receive_code(&self.listener, &self.path, state),
        )
        .await
        .map_err(|_| Error::AuthTimeout)?
    }
}

/// Accepts connections until one carries the OAuth redirect. Other requests
/// (a browser's favicon fetch, for example) get 404.
async fn receive_code(listener: &TcpListener, path: &str, expected_state: &str) -> Result<String> {
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

        let Some(outcome) = parse_callback(request_line, path, expected_state) else {
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

/// Parses `GET <path>?code=...&state=... HTTP/1.1`. Returns `None` when the
/// request is not an OAuth redirect at all.
fn parse_callback(request_line: &str, path: &str, expected_state: &str) -> Option<Result<String>> {
    let mut parts = request_line.split_whitespace();
    if parts.next()? != "GET" {
        return None;
    }
    let url = Url::parse(&format!("http://127.0.0.1{}", parts.next()?)).ok()?;
    if url.path() != path {
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
    fn parses_callback() {
        let ok = parse_callback("GET /?state=s1&code=4%2Fabc&scope=x HTTP/1.1", "/", "s1");
        assert_eq!(ok.unwrap().unwrap(), "4/abc");

        let wrong_state = parse_callback("GET /?state=other&code=abc HTTP/1.1", "/", "s1");
        assert!(matches!(wrong_state, Some(Err(Error::Auth(_)))));

        let denied = parse_callback("GET /?state=s1&error=access_denied HTTP/1.1", "/", "s1");
        assert!(matches!(denied, Some(Err(Error::Auth(_)))));

        assert!(parse_callback("GET /favicon.ico HTTP/1.1", "/", "s1").is_none());
        assert!(parse_callback("GET / HTTP/1.1", "/", "s1").is_none());
        assert!(parse_callback("POST /?code=a&state=s1 HTTP/1.1", "/", "s1").is_none());
        assert!(parse_callback("", "/", "s1").is_none());
    }

    #[test]
    fn parses_callback_on_a_path() {
        let ok = parse_callback(
            "GET /slack/callback?code=c&state=s1 HTTP/1.1",
            "/slack/callback",
            "s1",
        );
        assert_eq!(ok.unwrap().unwrap(), "c");
        assert!(
            parse_callback("GET /?code=c&state=s1 HTTP/1.1", "/slack/callback", "s1").is_none()
        );
    }

    #[tokio::test]
    async fn loopback_receives_code_after_unrelated_request() {
        let loopback = Loopback::any_port().await.unwrap();
        let port: u16 = loopback
            .redirect_uri
            .rsplit(':')
            .next()
            .unwrap()
            .parse()
            .unwrap();
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
        let code = loopback.wait_for_code("s1").await.unwrap();
        assert_eq!(code, "the-code");
        browser.await.unwrap();
    }

    #[tokio::test]
    async fn fixed_port_in_use_is_explained() {
        let taken = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = taken.local_addr().unwrap().port();
        let err = Loopback::fixed(port, "/cb", "SOME_PORT_VAR")
            .await
            .err()
            .unwrap();
        assert!(err.to_string().contains("SOME_PORT_VAR"));
    }
}
