-- The first schema. Each app owns the tables that start with its name.

-- desk: one row per topic, and its items in order.
CREATE TABLE desk_topics (
    id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (service, key)
);

CREATE TABLE desk_items (
    topic_id TEXT NOT NULL REFERENCES desk_topics (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    key TEXT NOT NULL,
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    author TEXT,
    url TEXT,
    date TEXT NOT NULL,
    PRIMARY KEY (topic_id, position)
);

-- desk: single values, such as when topics last changed.
CREATE TABLE desk_values (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- gmail: the connected account and where the next sync starts.
CREATE TABLE gmail_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    email TEXT NOT NULL,
    history_id TEXT
);

-- google_tasks: the connected account, per service.
CREATE TABLE google_tasks_state (
    service TEXT PRIMARY KEY,
    email TEXT NOT NULL
);
