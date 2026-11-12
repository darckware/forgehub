# ECO-047 reconciliation before integration work — 2026-11-12

Status: repository merge prepared; production application and independent review pending.
Source checkout: clean `develop` at `b97de6e` before this work. No deployment,
restart, live verifier replacement, secret access or audit database write was performed.

## Necessity assessment

No repeat RustDesk rollout or Darckware deploy is justified by this preflight:
their inspected configuration and HTTP behavior already meet the checked parts
of the runbook. Exact deployment provenance and functional relay/application
tests remain separate evidence gaps, not reasons to restart working services.

Keep the verifier merge for review: replacing the live file with the previous
release copy would lose existing checks and diagnostics. Its IPv6 finding is a
baseline discrepancy for a tailscaled-owned tailnet socket; the observation
does not establish public exposure or justify closing that socket. Preserve the
finding pending review rather than fabricate a passing result.

`record()` stores a check result and updates audit status; it does not approve a
deployment or accept a mission. No extra "approval in the Auditor" is needed.
Recording the final check is needed only to close ECO-047 through its runbook.

The inspected integrated-plan dependency tables and FileNest checklist do not
name ECO-047 as a prerequisite. Do not treat this maintenance finding as a new
blanket gate on integration work; apply the documented gates of the actual task.

## Verified state

- ForgeHub backend/frontend containers use `fh-3715a28`; backend healthy.
- Read-only SQL confirms `company.alembic_version = 1994f24fd6e1`.
- RustDesk is already on `remoto_default`, not host networking. Docker publishes
  TCP 21115/21116 and UDP 21116 on hbbs, TCP 21117 on hbbr, all exclusively on
  `100.105.235.114`; no 21118/21119 publication is configured.
- `/root/project/remoto/compose.yml` SHA-256 is
  `74effebf98488143c82fafeea3137f506030ea3edb448a889f4caa416ae696a5`, matching
  the runbook's prepared version. Do not apply the patch again or restart solely
  to apply it. Two-client ID/heartbeat, forced relay and external reachability
  remain unverified; Docker configuration alone does not establish them.
- Darckware returns `/health` 200 and `/docs`, `/redoc`, `/openapi.json` 404 on
  both `127.0.0.1:8020` and `100.105.235.114:8020`. The nine public documentation
  probes produced no findings in the final read-only ECO-047 probe.
  This does not prove the running container's ENVIRONMENT value or its exact
  deployment commit. Authentication and Lara bridge were not exercised.
- Darckware checkout has pre-existing modified and untracked files; do not
  deploy it wholesale. No Darckware source was modified in this session.

## Merge prepared in the repository

The live verifier differs from the release copy. Its SHA-256 at comparison was
`bf690e9f30720fe5179733b8a399730c930a97603aabdb44b864983a937c1188`.
The merge preserves its `ipaddress` classification, IPv4-mapped IPv6 handling,
existing owner checks, host context, process diagnostics and omitted-finding
counts. It retains the release's stricter UFW proof, exact-node infrastructure
exceptions and Darckware documentation probes. Ports 3000/8020 continue to
require docker-proxy ownership, as in the live verifier. Independent review also
removed the live generic SSH fallback: infrastructure exceptions apply only to
the exact native IPv4, excluding other tailnet nodes and mapped IPv6 aliases.

Real sockets revealed `%tailscale0` scope suffixes. The merge normalizes these
before parsing and matching the exact authorized IPv4. It does not introduce
an IPv6 peer-API exception that the runbook has not authorized.

Validation:

```text
cd /root/project/forgehub/ops/athos
/root/project/forgehub/backend/.venv/bin/python -m pytest -q --noconftest tests/ -rs
79 passed in 0.22s
```

The initial added regression tests failed against the release copy, exposing
lost live behavior. Scoped-address tests also failed before their correction.
The full isolated suite then passed outside the sandbox, including the test
that evaluates SQL literals in the test PostgreSQL. No vault reads are needed.

## Final read-only ECO-047 result

Called the merged module's `check_public_interfaces()` directly, without
calling `main()` or `record()`. The installed verifier and audit state remain
unchanged. This is a preflight result, not a recorded production acceptance.

```text
FAIL: Public interface drift (1)
tcp [fd7a:115c:a1e0::2501:ebce]%tailscale0:63157 process=tailscaled[881945]: Tailscale bind, no authorized baseline (function unverified)
```

The full result also states that external reachability is not verified, UFW is
evaluated only for the 8910 exception, and nft is not evaluated. The remaining
listener is on the node's Tailscale IPv6; it must be addressed through a reviewed
policy decision, not a broad port or network exemption or an unapproved closure.

## Operator handoff and rollback

Hephaestus applies; Porthus reviews; Marcelo authorizes, as specified in
`docs/runbooks/eco047-remediation.md`. Before any live installation, recompare
the live verifier and prepare
`/root/.hermes/profiles/athos/state-snapshots/eco047-<timestamp>/` with the
installed verifier, original permissions, hashes and README describing this
merge, the approved commit, evidence and rollback. Stop if intervening changes
are not included. No live snapshot was created here because no live file was
changed.

Rollback for the verifier: restore that saved file with its original mode and
run the read-only check; retain the previous audit history. Existing RustDesk
and Darckware rollback procedures remain in the runbook. Do not recreate either
service until a specific unmet requirement justifies it and a fresh snapshot
records the actual current configuration and image IDs.

After review and resolution of the IPv6 baseline, Hephaestus can install the
merged verifier, rerun tests, complete the two-client relay and application
checks, then execute the runbook's `--check ECO-047` command to record evidence.
That last command writes audit state and requires its production backup first.

Handoff could not be sent in this session: tool discovery via `ALL_TOOLS` found
no names matching `tool_search|forgehub|list_deploy|agent_message`, and no
`tool_search` capability is exposed. This is a tool-availability limitation,
not evidence that the ForgeHub server is down. No substitute credential or
direct database dispatch was used. Application remains BLOCKED pending the
normal Messages handoff/review and the IPv6 policy resolution.

## Pre-publication review

A separate code-review sub-agent found an inherited generic SSH exception and
mapped IPv6 aliases bypassing the exact-address policy. Four added regressions
failed before correction; all 79 isolated Auditor tests passed afterward. A
second review found no remaining critical or important issues. This review is
not a Porthus identity, operator approval, or installation of the live verifier.

Release validation before commit: backend isolated suite **2348 passed, 21
skipped, 23 warnings**; frontend **610 passed across 117 files**; `npm run build`
succeeded with Mermaid import/chunk-size warnings; `git diff --check` passed.
