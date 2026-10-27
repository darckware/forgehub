# Dashboard cleanup

User-requested delivery: remove the unused CLI ForgeRouter Global card and fit independent-height cards without empty grid cells.

Published frontend commit: `9fa658e`. Independent Porthus review #41582 approved publication. No CLI or VPN configuration was changed. The backend image was preserved.

Validation:
- Existing Dashboard and SystemStatsCard tests: 4 passed.
- Production build and locale catalog check passed. Existing large-chunk and Mermaid import warnings remain.
- Actual Dashboard browser rendering with controlled data: 1440px/two columns and 390px/one column, no horizontal overflow, no CLI Global card, no page errors. Screenshots: `/tmp/forgehub-dashboard-1440.png`, `/tmp/forgehub-dashboard-390.png`.
- Global premium static audit: 44 pre-existing form/textarea findings outside the changed Dashboard. Output retained at `/tmp/forgehub-dashboard-premium-audit.json`; this delivery does not claim global UI compliance.
- Production serves `/assets/index-BPwDKjiA.js`; the asset responds successfully. API proxy rejects unauthenticated telemetry with HTTP 401. Existing backend image remained unchanged.

Release and rollback metadata: `/root/.forgehub/releases/dashboard-9fa658e/`. Published image: `forgehub-frontend:dashboard-9fa658e`.

The follow-up monitoring proposal is separate: `docs/superpowers/specs/2026-10-26-server-monitoring-dashboard-design.md`. Its new collectors/cards are not yet implemented. Existing live Tailscale status and peer metadata are available for reuse through the admin-only VPN API.
