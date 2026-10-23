# SilentDesk

A quiet desktop task tracker for work. Built with [Tauri v2](https://v2.tauri.app/),
React, TypeScript and Vite.

## Prerequisites

- [Node.js](https://nodejs.org/) 20 or newer and [pnpm](https://pnpm.io/)
- [Rust](https://www.rust-lang.org/tools/install) (stable) with `cargo`
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
| `pnpm tauri build` | Build a release desktop bundle for your platform    |

## Connections

The **Topics** view pulls your recent communications as topics, on demand:

| Service | Pulls                         | Setup                                      |
|---------|-------------------------------|--------------------------------------------|
| Gmail   | Last 10 emails, sent and received | [docs/setup/gmail.md](docs/setup/gmail.md) |
| Slack   | Last 10 direct messages, sent and received | [docs/setup/slack.md](docs/setup/slack.md) |
| Jira    | Last 10 open issues assigned to you or reported by you | [docs/setup/jira.md](docs/setup/jira.md) |

Gmail and Slack need an app or client ID that you or your organization creates; put it in `.env`. Jira needs only your own API token, entered in the app. On Linux, a Secret Service keyring (GNOME Keyring or KWallet) must be running, because SilentDesk keeps its keys there.

## Project layout

```
src/                     React frontend
  App.tsx                Header and Tasks / Topics switch
  api/backend.ts         Calls into the Rust backend
  components/            Views and list items
  store/tasks.ts         Task store (localStorage for now)
  types.ts               Shared types
  styles.css             App styles (light and dark)
src-tauri/src/           Rust backend
  commands/              Commands the frontend can call
  vault.rs               Encrypted local store
  secrets.rs             OS credential store access
  model.rs               Topics and source items
  oauth.rs               Shared sign-in pieces (PKCE, loopback redirect)
  gmail/, slack/, jira/  Sign-in, API calls and sync per service
docs/specs/              Product specs, starting with core.md
```

Topics and connected-service data are kept in an encrypted vault; see [docs/specs/data-model.md](docs/specs/data-model.md). Tasks are still saved in the webview's `localStorage` and will move into the vault.
