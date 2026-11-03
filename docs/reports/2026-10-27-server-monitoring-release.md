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

Final Foundation review: Porthus approved message #41583 for publication, with no blocking Critical/Important issue. Recommended rate-window correction implemented and regression observed RED→GREEN: samples separated by over 60s return unknown until the next sample. Tailscale link goes directly to Remote Access. SSH event usernames are untrusted log metadata and restricted to admin.

## Published and verified

Released commit `b7f802f` on 2026-10-27 (UTC); remote branch `feat/server-monitoring` updated. Final focused tests: **12 Python + 23 frontend passing**. Locale parity, TypeScript/Vite build and Ruff passed. Existing large-bundle warnings remain.

Active images:
- `forgehub-backend:monitoring-b7f802f`, observed image `sha256:547fb2901cf5bab3711b65d5271881dbaa52c81824173bfdbeea319a53a59511`.
- `forgehub-frontend:monitoring-b7f802f`, observed image `sha256:7330a67d2cd41096887ecb71c68a701e70435f65486b996ce7531350c802df01`.

Release artifacts/approval/rollback: `/root/.forgehub/releases/monitoring-b7f802f/`. The bridge runs from that release's `host-bridge/` via `/etc/systemd/system/forgehub-chat-bridge.service.d/90-monitoring-release.conf`. Its original `KillMode=control-group` was restored after a temporary process-preserving restart; detached auxiliary process PID 3880104 survived. No Hermes gateway restart. Original dirty project sources were not overwritten.

Post-deploy evidence: backend running/healthy; frontend running; bridge active and health 200. Private host snapshot passes production schema. All nine source envelopes fresh after scan; all six allowed directory totals available; log metadata collected for 24 containers. Two successive samples confirm live network rates. Terminal session source fresh; SSH events and app login events explicitly unavailable. API details reject anonymous and bridge-only requests (401); existing basic stats still accept their original bridge-token scope (200), adjacent path remains denied. Actual admin/nonadmin behavior is covered in offline ASGI tests; production smoke did not impersonate an admin user. Published frontend `/assets/index-DOcOXaBF.js` hash equals the tested build.

## Subsequent deploy and rollback

Use the versioned compose override with the original compose file/project name. Future normal builds must first integrate the feature branch; do not rebuild the unrelated dirty checkout expecting these changes to be included. The bridge now loads the isolated release directory, so changing the original host-bridge/app.py alone does not publish changes.

Rollback containers using `rollback.override.yml` in the release directory with `docker compose -p forgehub -f /root/project/forgehub/docker-compose.yml -f <rollback.override.yml> up -d --no-build --no-deps forgehub-backend forgehub-frontend`. Restore only this bridge WorkingDirectory override to its previous location, reload systemd and restart the bridge with process preservation as during release; keep unrelated unit/token settings. Validate health afterward.

## Execution record

User approved design and implementation. Existing isolated branch feat/server-monitoring verified clean at e48d791.
Ruling: execute inline continuously; prior approval covers design, implementation and release. Preserve unrelated original checkout changes.
Task 1 started: fixed host metadata collectors; tests precede implementation.
Task 1: five meaningful collector tests observed RED then GREEN. Real sandbox snapshot completed in 0.12s, Docker unavailable due sandbox; verify privileged host before release.
Task 2: two API tests observed RED then GREEN; admin succeeds, anonymous/bridge-only rejected, nonadmin forbidden, upstream response never exposed. No DB writes.
Task 3: loading/unavailable/stale UI tests observed missing component RED; implementation underway.
Whole-branch fresh reviewer: no Critical, 4 Important. Verified and corrected in one fix pass: payload-level VPN failure, per-source TTL (10min disk/logs), deadline+inflight reuse for blocked collectors, Docker disk categories+local log metadata. Regression tests observed RED→GREEN for VPN/stale/deadline. Docker and portable who regression added; who --ips unsupported on actual host, removed flag (default performs no DNS lookup).
Real host: all 8 primary sources fresh; six directory roots and 24 container log metadata rows; system/user services active. Disk scan took ~21s in background. SSH journal lacked evidence in queried hour (unavailable). Sessions retest after portable fix required.
Frontend: 23 focused/reuse tests pass. Browser 390/1440px no horizontal page overflow, expanded detail tables and sorting work, per-target failed backup visible, HTTP-200 VPN unavailable handled; screenshots /tmp/forgehub-monitoring-*.png. Preview harness will be removed before commit.
Ruling: release host bridge from isolated versioned directory using a systemd WorkingDirectory override, preserving original dirty source and excluding unrelated SSH work; live bridge has no SSH routes. Keep original token/unit settings, never restart Hermes gateway.

Final: review #41583 approved, idle-rate fix RED→GREEN, 12+23 tests passed, build passed, release active and live metadata/rates verified. Own temporary preview and plan workspace cleaned.
