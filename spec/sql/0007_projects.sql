-- desk: projects the user groups topics in. A topic without a project is in
-- Default, which is no row here.
CREATE TABLE desk_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

-- Deleting a project moves its topics back to Default.
ALTER TABLE desk_topics ADD COLUMN project_id TEXT REFERENCES desk_projects (id) ON DELETE SET NULL;
