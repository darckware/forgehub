# SSH diagnostic scripts

User request: deliver local Windows and Linux diagnostics and register the same
scripts in Remote Access. Implementation stays in this worktree; no publish/deploy.

Use standalone assets loaded by the existing system script catalog (startup seed).
Category: remote access; risk: read; no parameters, network probes or changes.
Report missing dependencies and permission limitations independently, never print
credentials, authorized key contents, authentication logs or raw configuration.
Check server availability, service state, listening ports, selected SSH directives,
Tailscale service/address, darckware account and key file metadata. Reports cannot
prove that ForgeHub's candidate key matches or that the network path is reachable.

1. Test catalog registration/rendering and Linux absent-tool/failed-query behavior.
2. Create shared standalone .ps1/.sh assets and register both in SYSTEM_SCRIPTS.
3. Run targeted tests, shell syntax check and Ruff; independently review diagnostic
   safety and platform pitfalls. Windows execution requires the user's workstation.
4. Provide both files and local execution instructions, reporting pending live checks.

Follow-up request: add a "Diagnosticar acesso" footer disclosure in PrepareDialog.
Use an admin-only GET /api/v1/servers/{id}/preparation/diagnostic to deliver the
same static asset without requiring SSH, enabled access or complete pending
credentials. Key/cancel requests by machine; show loading, retry, clipboard error
and manual copy. Localize in pt-BR/en/es. Preserve all preparation actions.

Verification: 144 targeted backend integration tests on the isolated test DB;
5 offline diagnostic tests, including missing/failing tools and a readable key
file whose contents must never enter output; 129 Remote Access frontend tests;
Ruff, sh -n and diff whitespace checks passed. Independent safety review completed
and findings addressed. Browser fixtures checked Windows/Linux at 390px/1440px:
copy, retries, keyboard focus, machine changes and no horizontal overflow.
PowerShell unavailable on the development host: live Windows execution remains
pending the station's diagnostic return. No merge, push, deploy or production DB
test was performed.
