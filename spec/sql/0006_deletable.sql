-- desk: whether the user can delete each topic and item, as its connector
-- judged at sync time.
ALTER TABLE desk_topics ADD COLUMN deletable INTEGER NOT NULL DEFAULT 0 CHECK (deletable IN (0, 1));
ALTER TABLE desk_items ADD COLUMN deletable INTEGER NOT NULL DEFAULT 0 CHECK (deletable IN (0, 1));

-- Gmail can trash any message, and its syncs only list threads that change,
-- so its existing topics get now what their next sync would give them.
UPDATE desk_topics SET deletable = 1 WHERE service = 'gmail';
UPDATE desk_items SET deletable = 1 WHERE topic_id IN (SELECT id FROM desk_topics WHERE service = 'gmail');
