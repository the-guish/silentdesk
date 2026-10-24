"""Technical building blocks that every app's adapters share: settings, the
SQLCipher database, the OS keyring, HTTPS and the system browser.

Only adapters and wiring use these. Core, ports and application never do."""
