# SilentDesk

A quiet desktop task tracker for work. Built with [Tauri v2](https://v2.tauri.app/),
React, TypeScript and Vite, with a Python backend for the connected services.

## Prerequisites

- [Node.js](https://nodejs.org/) 20 or newer and [pnpm](https://pnpm.io/)
- [Rust](https://www.rust-lang.org/tools/install) (stable) with `cargo`
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 or newer and the backend's packages
- Platform libraries for Tauri. See the
  [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for macOS and Windows.

### Linux (Debian / Ubuntu)

```sh
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev \
  libssl-dev \
  build-essential \
  pkg-config \
  curl wget file libxdo-dev
```

For other distributions, use the equivalent packages listed in the Tauri prerequisites guide.

## Getting started

```sh
cp .env.example .env   # optional: fill in to enable Gmail
./dev.sh               # install dependencies if needed, load .env, run the app
```

`./dev.sh` runs `pnpm tauri dev` with the variables from `.env`; extra arguments are passed through.

Other useful commands:

| Command            | What it does                                        |
| ------------------ | --------------------------------------------------- |
| `pnpm dev`         | Run only the web frontend at http://localhost:1420  |
| `pnpm build`       | Type-check and build the frontend into `dist/`      |
| `pnpm test:backend` | Run the Python backend's tests                     |
| `pnpm release`     | Bundle Python and the backend, then build a release desktop bundle for your platform |

## Connections

The **Topics** list pulls your communications and tasks as topics. It syncs at startup, every 2 minutes and when you return to the window:

| Service | Pulls                         | Setup                                      |
|---------|-------------------------------|--------------------------------------------|
| Gmail   | Subject of every Inbox email; reply and trash | [docs/setup/gmail.md](docs/setup/gmail.md) |
| Google Tasks | Every open task, read-only | [docs/setup/google-tasks.md](docs/setup/google-tasks.md) |
| Slack   | Last 10 direct messages, sent and received | [docs/setup/slack.md](docs/setup/slack.md) |
| Jira    | Last 10 open issues assigned to you or reported by you | [docs/setup/jira.md](docs/setup/jira.md) |
| GitHub  | Open pull requests waiting for your review, assigned to you, or opened by you | [docs/setup/github.md](docs/setup/github.md) |

Gmail, Google Tasks and Slack need an app or client ID that you or your organization creates; put it in `.env`. Gmail and Google Tasks share the Google one. Jira and GitHub need only your own token, entered in Settings. On Linux, a Secret Service keyring (GNOME Keyring or KWallet) must be running, because SilentDesk keeps its keys there.

## Project layout

```
src/                     React frontend
  App.tsx                Header, Topics list and Settings
  api/backend.ts         Calls into the backend
  components/            Views and list items
  types.ts               Shared types
  styles.css             App styles (light and dark)
src-tauri/src/           Rust host: storage, secrets, starts and talks to the backend
  backend.rs             Starts the Python backend and relays messages
  host.rs                What the backend may ask of Rust
  store.rs, vault.rs     Schema-checked, encrypted local store
  secrets.rs             OS credential store access
  model.rs               Topics and source items: the schemas the backend writes
backend/silentdesk/      Python backend, ports and adapters
  core/                  Model, errors, topic logic, ports
  sources/               gmail/, tasks/, slack/, jira/, github/: sign-in, API calls and sync
  adapters/              IPC with Rust, HTTP, OAuth loopback
  app.py                 Methods the UI calls, automatic syncing
scripts/bundle-backend.sh  Puts a standalone Python and the backend in the release bundle
docs/specs/              Product specs, starting with core.md; backend.md for the backend
```

Topics and connected-service data are kept in an encrypted vault; see [docs/specs/data-model.md](docs/specs/data-model.md). Tasks live in Google Tasks.
