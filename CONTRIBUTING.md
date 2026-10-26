# Contributing to SilentDesk

SilentDesk was started by Luis Castro and is maintained by The SilentDesk Authors (see [AUTHORS](AUTHORS)). Contributions are welcome.

Before you build a feature, read the [core principles](docs/specs/core.md). A change that conflicts with them will not be merged.

## How the repository fits together

SilentDesk has two cores, one per platform, that must behave the same: [`linux/core`](linux/core) in Python and [`apple/core`](apple/core) in Swift. Their shared behaviour is specified in [`docs/specs/`](docs/specs) and [`spec/`](spec), and tested by the conformance suite in `spec/`. Each app uses only its core's public API (`silentdesk.api` in Python, `SilentDeskCore` in Swift).

To change behaviour:

1. Change the contract first: [`docs/specs/cli.md`](docs/specs/cli.md), a schema in `spec/`, and a conformance case.
2. Implement it in `linux/core`.
3. Implement it in `apple/core`, or list the case in [`apple/core/conformance-pending.txt`](apple/core/conformance-pending.txt) until it does.

## Set up your workspace

- [uv](https://docs.astral.sh/uv/) for the Python parts.
- For the Linux app, the GTK packages listed in [linux/gtk/README.md](linux/gtk/README.md).
- For the Swift core, Swift 6: Xcode 16 or newer on macOS, or [swift.org/install](https://www.swift.org/install/) on Linux, with the SQLCipher and OpenSSL development packages (`libsqlcipher-dev` and `libssl-dev` on Ubuntu).

## Branches

Start every branch from `main` and name it after the kind of change:

| Prefix | For | Example |
|--------|-----|---------|
| `feature/` | New features and other planned work | `feature/swift-setup` |
| `fix/` | Bug fixes | `fix/gmail-sync-timeout` |

After the prefix, use a short name in lowercase words separated by hyphens. Every branch goes back into `main` through a pull request.

## Before you open a pull request

CI runs these; run the ones for the parts you changed:

```sh
# spec/
uvx ruff check spec/runner && uvx ruff format --check spec/runner
uv run --no-project --with pytest --with 'jsonschema>=4.23' pytest -q spec/runner/tests

# linux/core
uv sync --directory linux/core
uv run --directory linux/core ruff check && uv run --directory linux/core ruff format --check
uv run --directory linux/core pytest -q
uv run spec/runner/conformance.py --pending linux/core/conformance-pending.txt -- linux/core/.venv/bin/silentdesk

# linux/gtk (xvfb-run is only needed without a display)
uv run --directory linux/gtk ruff check && uv run --directory linux/gtk ruff format --check
xvfb-run -a uv run --directory linux/gtk pytest -q

# apple/core
swift build --package-path apple/core && swift test --package-path apple/core
uv run spec/runner/conformance.py --pending apple/core/conformance-pending.txt -- apple/core/.build/debug/silentdesk

# apple/app (the SwiftUI app builds on macOS only; Linux tests its model)
swift test --package-path apple/app
```

- Keep each pull request small and focused on one change.
- Describe what changed and why.

## SonarQube Cloud

SonarQube Cloud has one project per platform, set in `linux/sonar-project.properties` and `apple/sonar-project.properties`. CI scans a project only when its folder changes.

The conformance suite sets the Linux core's coverage. It runs the CLI under coverage. Unit tests report no coverage. These commands show it locally:

```sh
uv sync --directory linux/core
export COVERAGE_RCFILE=$PWD/linux/core/pyproject.toml COVERAGE_FILE=$PWD/linux/core/.coverage
uv run spec/runner/conformance.py --pending linux/core/conformance-pending.txt -- linux/core/.venv/bin/coverage run -m silentdesk
cd linux && core/.venv/bin/coverage combine && core/.venv/bin/coverage report
```

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE). Add your name to [AUTHORS](AUTHORS) in your first pull request.
