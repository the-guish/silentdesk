-- jira: the connected user, the site and where its API is.
CREATE TABLE jira_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    site TEXT NOT NULL,
    api_base TEXT NOT NULL,
    flavor TEXT NOT NULL CHECK (flavor IN ('cloud', 'dataCenter'))
);
