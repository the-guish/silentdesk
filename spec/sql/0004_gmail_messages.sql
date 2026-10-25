-- gmail: the headers of every synced message, never bodies.
CREATE TABLE gmail_messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    date TEXT NOT NULL
);

CREATE INDEX gmail_messages_by_thread ON gmail_messages (thread_id);
