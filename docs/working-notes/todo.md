# To do

Working notes. Not a spec.

## App
- [ ] Replace the localStorage task store with encrypted local storage (core principle 1).
- [ ] Load tasks from corporate systems (Jira, Gmail, Slack) instead of storing them locally (core principle 4).
- [ ] Run `pnpm tauri dev` on a machine with a display to check that the native window works.

## Specs
- [ ] Answer the open product questions in `docs/SPEC.md`:
  1. Who uses it: one person or a team?
  2. Task fields beyond the title.
  3. How the home screen is organized.
  4. Desktop features: global hotkey, tray icon, reminders.
  5. Storage target (now mostly settled by core principle 4).
  6. Platforms.
- [ ] Split `docs/SPEC.md` into topic files under `docs/specs/` (e.g. `screens.md`, `data.md`), then delete it.
- [ ] Resolve the open questions in `docs/specs/core.md`.
