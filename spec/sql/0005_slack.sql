-- slack: the connected user and workspace.
CREATE TABLE slack_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    team_id TEXT NOT NULL,
    team_name TEXT NOT NULL
);
