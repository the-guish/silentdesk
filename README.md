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
pnpm install       # install frontend and Tauri CLI dependencies
pnpm tauri dev     # run the desktop app with hot reload
```

Other useful commands:

| Command            | What it does                                        |
| ------------------ | --------------------------------------------------- |
| `pnpm dev`         | Run only the web frontend at http://localhost:1420  |
| `pnpm build`       | Type-check and build the frontend into `dist/`      |
| `pnpm tauri build` | Build a release desktop bundle for your platform    |

## Gmail

The **Topics** view can connect a Gmail account and pull the last 10 emails as topics. It needs an OAuth client from your Google Cloud project; see [docs/setup/gmail.md](docs/setup/gmail.md). On Linux, a Secret Service keyring (GNOME Keyring or KWallet) must be running, because SilentDesk keeps its keys there.

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
  commands.rs            Commands the frontend can call
  vault.rs               Encrypted local store
  secrets.rs             OS credential store access
  model.rs               Topics and source items
  gmail/                 OAuth sign-in, Gmail API, sync
docs/specs/              Product specs, starting with core.md
```

Topics and Gmail data are kept in an encrypted vault; see [docs/specs/data-model.md](docs/specs/data-model.md). Tasks are still saved in the webview's `localStorage` and will move into the vault.
