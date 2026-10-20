# Security policy

## Supported versions

Security fixes are applied to the latest main branch.

## Reporting a vulnerability

Please do not publish private files, file names, or sensitive paths in an issue. Contact the repository owner privately through GitHub's security advisory feature when it is enabled. If private reporting is unavailable, open a minimal issue without sensitive details and ask for a private contact route.

## Safety notes

The application scans file metadata and contents to compute SHA-256 hashes. It does not upload file contents. Quarantine moves files and writes a manifest containing original paths. Treat the manifest as sensitive because it may reveal your directory structure.
