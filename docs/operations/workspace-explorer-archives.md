# Workspace Explorer archives

The file/folder context menu provides **Compress to ZIP** for a selection and
**Extract archive** for one ZIP or TAR archive (including gzip/bzip2/xz variants).
The existing name dialog chooses a new ZIP file or extraction folder in the
displayed directory. Existing destinations are refused; originals are retained.
Listings refresh on completion, errors stay in the dialog, and backend actions
retain the selected server and administrator audit identity.

The host bridge implements both local and remote operations. Remote archive
operations require Python 3 on the selected server; no packages are installed.
The implementation uses the Explorer's existing SSH transport, not a browser
download/upload round trip. It never executes archive contents, restores archived
permissions, follows archive links, or accepts paths outside the new folder.
It refuses unsupported/encrypted/corrupt files, duplicate members, special files,
links and traversal paths. Limits: 10000 entries, 2 GiB uncompressed data and a
120-second processing deadline. Existing destinations are never overwritten.

## Release

Marcelo authorized deployment after the initial deferral. Deploy backend, frontend and host
bridge from the same reviewed commit; the new bridge modules are
`explorer_archives.py` and `explorer_archive_routes.py`. No database migration is
required. Take a verified application/bridge backup before production changes and
record current image identities and bridge source revision. Roll back all three
components together to those recorded versions. Do not retry an uncertain archive
operation before inspecting its destination.

## Verification

Tests use temporary directories and a simulated SSH transport; they do not read
production files or credentials. They cover ZIP round trips, empty directories,
TAR extraction, conflicts, unsafe paths/links, resource limits, quoting and target
selection. Component tests exercise the real Workspace menu and extraction dialog
with a mocked API.

## Production release — 2026-11-13

- Deployed source: `5ac8a31` on `release/explorer-archives`, the archive feature
  cherry-picked onto the previous production base `739808b`. Pending Auditor
  migrations and the in-progress Mission branch are excluded.
- Backend/frontend: `forgehub-backend:fh-5ac8a31` and
  `forgehub-frontend:fh-5ac8a31`; matching `latest` and `0.1.0` aliases preserve
  the selected release for normal restarts.
- Bridge: applied only the reviewed archive patch to the installed bridge under
  `/root/.forgehub/releases/mission-criteria-2d0eeab/host-bridge`, preserving its
  existing source changes, and restarted `forgehub-chat-bridge.service`.
- Backup: `/root/backup/explorer-archives-5ac8a31`. Includes prior images, validated
  PostgreSQL custom dump, bridge originals, image aliases, rollout metadata and
  `rollback.sh`. Execute that script to restore the prior images/aliases and bridge.
- Database remains at `1994f24fd6e1`; no migration was applied.
- Post-deploy: backend/frontend/bridge HTTP 200, service active, containers healthy,
  running backend SHA `5ac8a31`, served bundle includes both Portuguese actions,
  and unauthenticated valid archive requests return 401 at both API and bridge.
  The installed module passed a temporary ZIP/extraction round trip and refused
  an existing destination. No client machine was contacted during validation.
- Evidence: `DEPLOY_COMPLETE.json` and `verification.json` in the private backup.
