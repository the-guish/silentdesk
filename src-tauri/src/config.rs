//! App registrations the backend needs to sign in: the Google and Slack
//! client IDs. Read at runtime from the environment, or baked in at build
//! time, and handed to Python at startup.

use serde::Serialize;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Config {
    google_client_id: Option<String>,
    /// Google issues a secret for desktop clients but does not treat it as
    /// confidential; PKCE protects the flow.
    google_client_secret: Option<String>,
    slack_client_id: Option<String>,
    /// Must match the Slack app's redirect URL.
    slack_redirect_port: Option<String>,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            google_client_id: setting(
                "SILENTDESK_GOOGLE_CLIENT_ID",
                option_env!("SILENTDESK_GOOGLE_CLIENT_ID"),
            ),
            google_client_secret: setting(
                "SILENTDESK_GOOGLE_CLIENT_SECRET",
                option_env!("SILENTDESK_GOOGLE_CLIENT_SECRET"),
            ),
            slack_client_id: setting(
                "SILENTDESK_SLACK_CLIENT_ID",
                option_env!("SILENTDESK_SLACK_CLIENT_ID"),
            ),
            slack_redirect_port: setting(
                "SILENTDESK_SLACK_REDIRECT_PORT",
                option_env!("SILENTDESK_SLACK_REDIRECT_PORT"),
            ),
        }
    }
}

/// Reads a setting from the environment at runtime, falling back to a value
/// baked in at build time. Empty values count as unset.
fn setting(name: &str, built_in: Option<&str>) -> Option<String> {
    std::env::var(name)
        .ok()
        .or_else(|| built_in.map(str::to_owned))
        .filter(|v| !v.trim().is_empty())
}
