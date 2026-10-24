-- github: the connected account and the server it is on.
CREATE TABLE github_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    login TEXT NOT NULL,
    name TEXT NOT NULL,
    api_base TEXT NOT NULL,
    web_base TEXT NOT NULL
);
