# Server monitoring implementation

Goal: deliver the approved live, admin-only dashboard without changing existing basic stats permissions.
Spec: ../specs/2026-10-26-server-monitoring-dashboard-design.md
Architecture: host-only, fixed read-only collectors → authenticated admin proxy → responsive cards; reuse VPN and backup contracts. No DB changes or persisted IP history.

1. Add bounded host collector and tests: independent source envelopes, monotonic rates, metadata only, fixed directory roots with asynchronous 5-minute cache; no command/path input. Verify reset rates, redaction, socket parsing, cache and failures.
2. Add admin-only details endpoint and bridge integration. Validate response and normalize transport failures without leaking bridge output. Verify admin/nonadmin/anonymous and bridge-token scope.
3. Add live dashboard cards, reuse VPN and backup queries; explicit loading/error/stale states, table details, localized content, visible-tab polling, source timestamps. Preserve existing theme and independent card heights. Verify rendering and narrow viewport.
4. Review whole change, fix material findings, build isolated images, deploy only changed services, verify health and real host snapshot. Record evidence and rollback images.

Completion: meaningful Python/frontend tests, locale check, frontend build, browser narrow/desktop check; no raw args/logs/secrets; new endpoint rejects unauthorized callers; healthy release.
