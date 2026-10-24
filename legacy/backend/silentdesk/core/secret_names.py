"""Names of the secrets Rust keeps in the OS credential store. Rust accepts
only these (see `src-tauri/src/secrets.rs`); the values are the same as
before the backend moved to Python, so existing sign-ins keep working."""

GMAIL_REFRESH_TOKEN = "gmail-refresh-token"
# JSON: {"email": str | null, "token": str}
JIRA_CREDENTIAL = "jira-credential"
# JSON: {"access_token": str, "refresh_token": str | null, "expires_at": int | null}
SLACK_CREDENTIAL = "slack-credential"
GITHUB_TOKEN = "github-token"
GOOGLE_TASKS_REFRESH_TOKEN = "google-tasks-refresh-token"
