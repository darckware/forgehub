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

Deployment is deferred at Marcelo's request. Deploy backend, frontend and host
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
