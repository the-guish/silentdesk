"""Adapters every app can be given: the contract's shared services, built on
SQLCipher, the OS keyring, HTTPS and the system browser. `api.py` creates
them and passes them to each app, which sees only their classes in
`silentdesk.contract`. An app's own adapters live in that app."""
