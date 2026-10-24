"""The applications. Each one has the same five folders:

- `core`: the domain, pure logic and data, no I/O.
- `ports`: abstract classes for what the app needs from outside, used only inside the app.
- `adapters`: the ports' implementations.
- `application`: the use cases, implementing what the app exposes in `silentdesk.contract`.
- `wiring`: `create()`, which builds the application with its adapters.

Apps never import each other; they meet only through `silentdesk.contract`."""
