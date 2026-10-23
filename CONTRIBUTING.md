# Contributing to SilentDesk

SilentDesk was started by Luis Castro and is maintained by The SilentDesk Authors (see [AUTHORS](AUTHORS)). Contributions are welcome.

Before you build a feature, read the [core principles](docs/specs/core.md). A change that conflicts with them will not be merged.

## Set up your workspace

1. Install the prerequisites:
   - Node.js 20 or newer, and pnpm
   - Rust (stable), installed with [rustup](https://rustup.rs/)
   - The platform libraries Tauri needs. On Debian or Ubuntu, use the `apt-get` command in the [README](README.md#linux-debian--ubuntu). On other systems, follow the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

2. Clone the repository and install dependencies:

   ```sh
   git clone https://github.com/the-guish/silentdesk.git
   cd silentdesk
   pnpm install
   ```

3. Run the app:

   ```sh
   pnpm tauri dev
   ```

## Before you open a pull request

These must pass:

```sh
pnpm build                                        # type-check and build the frontend
cd src-tauri && cargo test && cargo clippy        # test and lint the Rust backend
```

- Keep each pull request small and focused on one change.
- Describe what changed and why.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE). Add your name to [AUTHORS](AUTHORS) in your first pull request.
