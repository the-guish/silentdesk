# To do

Working notes. Not a spec.

## App
- [x] Encrypted local vault, with its key in the OS credential store.
- [x] Gmail: connect securely and sync the last 10 emails as topics.
- [ ] Gmail: test against a real account (needs an OAuth client, see `docs/setup/gmail.md`).
- [x] Slack: connect securely and sync the last 10 direct messages as topics.
- [ ] Slack: test against a real workspace, especially the `to:me` / `from:<@me>` search queries.
- [ ] Slack: include channel mentions; open a message in Slack from its permalink.
- [x] Tasks are a topic kind backed by Google Tasks (read-only); the localStorage Tasks tab is gone.
- [ ] Task statuses and actions (complete, edit, create): needs the `tasks` scope.
- [ ] Join a task to the topic of the email it came from (Gmail `email` links).
- [ ] Group emails into topics (by thread first).
- [x] Jira: connect with an API token and sync the last 10 open issues as topics.
- [ ] Jira: test against a real Cloud site (scoped token via the gateway) and a Data Center instance.
- [x] GitHub: connect with a personal access token and sync open pull requests (review requested, assigned, authored) as topics.
- [ ] GitHub: test against a real account (this sandbox's proxy replaces GitHub credentials and blocks /search).
- [ ] Open source items (email, Slack message, Jira issue, pull request) from the queue.
- [ ] Link items across services (e.g. an email that mentions PAY-412 joins that issue's topic).
- [ ] In-app setup screen for client IDs, instead of `.env` (see the Gmail client ID discussion).
- [ ] Run `pnpm tauri dev` on a desktop machine to check the native window.

## Specs
- [ ] Answer the open product questions in `docs/SPEC.md`:
  1. Who uses it: one person or a team?
  2. Task fields beyond the title.
  3. How the home screen is organized.
  4. Desktop features: global hotkey, tray icon, reminders.
  5. Storage target (now mostly settled by core principle 4).
  6. Platforms.
- [ ] Split `docs/SPEC.md` into topic files under `docs/specs/` (e.g. `screens.md`, `data.md`), then delete it.
- [ ] Resolve the open questions in `docs/specs/core.md` and `docs/specs/data-model.md`.
