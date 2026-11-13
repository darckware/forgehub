# T12 governed remote/browser implementation checkpoint

T12 is **partially implemented, not accepted**. No real remote command, remote-site action, authenticated page inspection, live grant or credential change was performed during this checkpoint.

## Confirmed gaps and implemented bounds

SSH command/library/proposal/file tools already existed in both canonical Messages and unified Factory MCP. They use the individual dispatch credential file, existing machine authority, global pause, active task checks and host execution auditing. The MCP transport previously propagated uncoded timeouts/disconnections and treated gateway errors generically. It now marks lost write acknowledgements (including invalid success JSON) `UPSTREAM_UNCERTAIN`, never retries, and requires reconciliation without reflecting transport/body secrets.

The Workspace browser was absent from both catalogs. More seriously, middleware admitted individual `agt_` credentials to the entire Workspace prefix while the legacy routes lacked their own actor checks, including shared state and operator login. Those legacy routes now require a human principal. The existing visual `control_owner` expires after 2.5 seconds and is not a lease; the process-launch lock does not serialize browser actions. It cannot establish task ownership or consent to share authenticated cookies.

The new `task_browser` tool provides `open`, `read`, `navigate`, `fill`, `click`, `submit`, and `close`. It uses a separate Chromium process on a dedicated loopback port and a distinct test-browser profile, plus an incognito context and exact target per execution/run/agent. It never attaches to the shared Workspace page, cookies, profile or login. A dedicated delegable action, `task.browser.execute` (admin-granted only; medium-risk ceiling for input/click/submission; it replaced the original reuse of `planning.execution.dispatch` on 2026-11-13) is checked for the task's project on every request, together with canonical running execution, executor, active assignment, current dispatch credential, task status, and global pause. Pending intent and outcome use existing AuditEvent records; no permission registry or live grant is introduced.

Bridge SQLite metadata binds context and target to scope. Commands record a fingerprint and pending entry before effects; same-key replay cannot repeat an effect and changed payload conflicts. Lost mutation acknowledgement fences fresh mutations until a human administrator takes over, observes the exact page and explicitly confirms the original operation with its current observation hash. Contexts expire after 30 minutes, with periodic context disposal and four active contexts maximum. Backend audit metadata retains task, execution, run, principal and delegation; URLs are hashed in the audit rather than stored with possible query secrets.

The bridge refuses attachment to an unknown listener after restart. That condition needs operator reconciliation; it does not silently adopt a possibly unrelated process/context. In particular, reopening with a fresh key cannot recover an uncertain open whose target acknowledgement was lost.

An isolated live-CDP smoke was subsequently run against a disposable headless Chromium profile and an HTTP fixture bound to loopback. It opened a separate browser context, navigated, read the page, filled and submitted a fixture form, observed exactly one POST after same-key replay, performed human takeover/read/confirmation, and closed the context. Receipt: `isolated_context=true`, `local_submit_count=1`, `same_key_replayed=true`, `human_takeover_confirmed=true`, `operator_profile_used=false`. This qualifies the broker's real CDP lifecycle and local uncertain-submit recovery; it does not qualify a native agent runtime invoking the MCP or any remote/authenticated site.

## Catalog inventory versus runtime evidence

| Runtime | Source-installed path | Current evidence |
| --- | --- | --- |
| Claude | Session `--mcp-config` -> canonical Messages MCP | Mocked/imported catalog exposes bounded browser and existing SSH tools; no actual CLI browser operation qualified |
| Codex | Session TOML MCP override -> canonical Messages MCP | Same imported catalog; no actual CLI browser operation qualified |
| AGY / Antigravity | Dedicated shared MCP registration + inherited dispatch credential environment | Same server source; configuration/profile/runtime visibility still requires isolated runtime execution evidence |
| Hermes | Profile `forgehub` MCP may load Messages or Factory; individual credential forwarded through XDG name | Both catalogs checked; existing include/exclude profile filters can still hide tools; no profile modified or runtime browser action performed |

`get_workspace_browser_capabilities` describes support without opening a browser or reading credentials. It explicitly states that catalog presence is not runtime qualification.

## Verification and remaining acceptance

New tests were observed failing before implementation. The focused real-Postgres API test passed (1 test): canonical run accepted, legacy shared page refused, low-risk grant cannot mutate, revoked grant refused, and pending/completed audit retained. Pure authority tests passed (7); isolated broker/catalog/transport tests passed, including submission acknowledgement fencing. Isolated tests cover both MCP catalogs, transport uncertainty with one request, exact target isolation, durable replay across broker restart, conflicting command keys, closed/foreign scopes, uncertainty fencing, expiry disposal, task/run/executor/grant/pause refusal, shared authenticated context denial, and pending audit commit before a simulated effect.

Still unsupported: authenticated context handoff, human takeover UI for isolated contexts (admin API takeover/read/confirm/release is implemented), arbitrary JavaScript, and general browser test automation. Input/click/submission use fixed DOM operations with bounded CSS selectors and JSON-encoded text. Site click/submission acknowledgement remains uncertain until a human administrator observes and confirms the exact original operation; CDP dispatch is not business confirmation. No automatic submission retry is implemented. Navigation/read supports consultation and documentation, but this is not full R18 acceptance. Production deployment, real isolated per-runtime evidence, authenticated handoff design, and live browser lifecycle qualification remain necessary. This checkpoint does not assert SSH pause/expiry/reassignment has been requalified against every runtime.

## Switches and pre-enable requirements (2026-11-13)

After an independent review the feature ships **off**; off is the behavior before this checkpoint.

| Switch | Default | Effect when off |
| --- | --- | --- |
| `TASK_BROWSER_ENABLED` (backend settings) | `false` | `/api/v1/workspace-browser/task-context` and `/task-context/control` answer 503 `TASK_BROWSER_DISABLED`, nothing read or written. |
| `FORGEHUB_TASK_BROWSER_ENABLED=1` (bridge and MCP environment) | unset | Bridge: the `/v1/workspace-browser/task-context*` routes are not registered (404) and no task Chromium is ever launched. MCP: `task_browser` and `get_workspace_browser_capabilities` are absent from both catalogs (Messages and Factory). |
| `FORGEHUB_TASK_BROWSER_ALLOWED_HOSTS` (bridge) | empty | Comma-separated hosts exempt from the SSRF policy below. |

The legacy shared Workspace browser routes stay human-only (each one is tested to refuse an `agt_` credential); that boundary is not behind a switch.

Changes made with the switches:

- **SSRF policy** (bridge, `check_navigation_url`): navigation accepts only `http`/`https` without embedded credentials; the host is resolved and refused if any address is loopback, RFC 1918, CGNAT `100.64.0.0/10`, link-local (including `169.254.169.254`), IPv6 loopback/link-local/ULA, unspecified, multicast or otherwise non-global (IPv4-mapped IPv6 is unwrapped); an unresolvable host is refused. A refused URL is never recorded as an operation. Allow-listed hosts skip the check.
- `--remote-allow-origins=*` is no longer passed to the task Chromium (its CDP client sends no `Origin`); the separate test-run browser keeps its flags.
- Broker SQLite connections are always closed. The task Chromium's PID is recorded; at the next bridge start (only when enabled) it is stopped if that PID is still a Chromium on the task port, and every open session is marked closed. Recorded operations, including uncertain ones, are kept. An unknown listener on the port still refuses (409).

Requirements before turning it on:

- Run the task Chromium as an unprivileged user. Today it runs as the bridge's user (root) with `--no-sandbox`. Not done in this change.
- Add a network egress barrier (proxy or firewall) for the task browser: the SSRF check resolves before navigating, but Chromium resolves again (DNS rebinding) and follows redirects to internal addresses on its own.
- Grant `task.browser.execute` only to the qualified agent and project, with the risk ceiling the site needs.
- Qualify the MCP in each native runtime (table above), which this change does not do.
