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

## Project layout

```
src/                 React frontend
  App.tsx            Home screen (task list)
  components/        UI components
  store/tasks.ts     Task store hook and persistence (localStorage for now)
  types.ts           Shared types (Task)
  styles.css         App styles (light and dark)
src-tauri/           Rust backend and Tauri configuration
```

Tasks are currently saved in the webview's `localStorage`. All persistence goes
through the `TaskRepository` interface in `src/store/tasks.ts`, so it can be
swapped for a native backend later without changing the UI.
