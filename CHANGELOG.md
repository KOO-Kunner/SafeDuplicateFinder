# Changelog

## 0.1.0 — 2026-10-20

- Initial release.
- Duplicate scanning by file size and SHA-256.
- Desktop GUI and command-line interface.
- JSON and CSV reports.
- Quarantine with a restore manifest instead of permanent deletion.
- Unit tests and GitHub Actions test workflow.

## 0.2.0 — 2026-10-20

- Added two-stage hashing to reduce full reads on same-size non-duplicates.
- Added atomic JSON writes for reports and quarantine manifests.
- Added stale-report checks before quarantine and integrity checks before restore.
- Added Windows PyInstaller build script and spec.
- Added safety regression tests.
