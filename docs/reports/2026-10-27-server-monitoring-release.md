# Server monitoring release

Approved design: ../superpowers/specs/2026-10-26-server-monitoring-dashboard-design.md.
Implementation: ../superpowers/plans/2026-10-26-server-monitoring.md.

Changes: read-only admin host metadata endpoint and live dashboard; reuse existing basic resource, VPN, Docker occupancy and backup sources. No migrations or IP history. Primary resources precede secondary tool information. Responsive independent-height cards retain current tokens.

Verification before release:
- Collector: rate initialization/reset, IPv6/process-only socket metadata, SSH log allowlist, sanitized source errors, disk cache, blocked-source deadline/inflight reuse, portable session read.
- API: anonymous/internal-bridge-only denied, nonadmin forbidden, admin accepted; HTTP/JSON/schema errors normalized without upstream body disclosure. No production DB writes.
- Frontend: loading, unavailable, stale, payload-level VPN failure, independent disk freshness and Docker/log metadata; existing resource/dashboard/VPN/backup view-model tests.
- Browser fixtures: 390px and 1440px; no page overflow or JS errors, details/tables and process sort function, failed system backup remains visible beside successful application backup. Screenshots: /tmp/forgehub-monitoring-{390,1440}.png and expanded variants.
- Real host: all eight lightweight sources fresh; system/user units active. Six authorized roots and 24 container log metadata rows collected separately in about 21 seconds. SSH journal has no evidence for the queried hour and is unavailable. Runtime rates need two samples.
- Fresh whole-branch review: no Critical findings; four Important findings corrected with regression coverage (VPN source error, per-source age, bounded collectors, Docker storage breakdown). Ruff passes.

Release strategy: versioned runtime images and isolated host bridge source with a WorkingDirectory override. Preserve unrelated dirty original checkout, SSH changes, original unit/token settings, databases and Hermes gateway. Record image IDs and final smoke results after publication.

Limits: live view only; application login events lack structured source. Socket IPs do not identify users; traffic rates are per interface, not per remote IP. Directory totals cover the fixed allowlist, local Docker log sizes depend on log driver. Endpoint service health is unknown unless an existing container healthcheck reports it. Pre-existing bundle-size warnings remain outside this feature.
