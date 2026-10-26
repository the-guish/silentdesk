-- desk: the status a topic's service gives it, such as a Jira issue's. Both
-- columns are null for a topic whose service reports none
-- (docs/specs/topic-status.md).
ALTER TABLE desk_topics ADD COLUMN status_name TEXT;
ALTER TABLE desk_topics ADD COLUMN status_category TEXT CHECK (status_category IN ('new', 'inProgress', 'done'));
