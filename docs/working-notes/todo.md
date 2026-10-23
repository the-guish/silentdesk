# To do

Working notes. Not a spec.

## App
- [x] Encrypted local vault, with its key in the OS credential store.
- [x] Gmail: connect securely and sync the last 10 emails as topics.
- [ ] Gmail: test against a real account (needs an OAuth client, see `docs/setup/gmail.md`).
- [ ] Move tasks from localStorage into the vault (core principle 1).
- [ ] Link tasks to topics.
- [ ] Group emails into topics (by thread first).
- [ ] Slack and Jira as topic sources (core principle 4).
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
