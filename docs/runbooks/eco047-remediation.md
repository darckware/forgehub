# ECO-047: prepared remediation, 2026-11-05

Origin: authorized continuation Messages #42049; operational request #42045.
Host: `vmi3547248`. Implementation only; Porthus reviews independently and
Hephaestus applies through the normal production gate. No restart, deploy,
firewall modification, live verifier replacement or audit DB write was performed.

## Artifacts and policy

- Darckware: `backend/app/main.py` disables the OpenAPI route in production;
  existing Swagger/ReDoc restrictions remain. `docker-compose.yml` explicitly
  sets `ENVIRONMENT: production`: the inspected container still has development.
  Production JWT prerequisites were checked for presence and distinctness only.
  `backend/isolated_tests/test_production_docs.py` checks real ASGI responses in
  separate processes without lifespan, database connections or email workers.
  `backend/pytest.ini` includes these isolated tests in normal test discovery.
- RustDesk: `/root/project/remoto/compose.yml` switches host networking to the
  default bridge; publishes TCP 21115/21116/21117 and UDP 21116 exclusively on
  `100.105.235.114`. Web ports 21118/21119 remain unpublished. Persistent data,
  keys and the relay address are preserved. No image update is part of this work.
  The directory has no Git repository: the reversible patch is versioned here
  at `ops/eco047/rustdesk-compose.patch`. Local backup: `compose.pre-eco-047.yml`.
  `/root/project/remoto/README.md` documents the new network arrangement.
- Auditor: `ops/athos/checklist_verifier.py` is the release copy; the live script
  remains `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`.
  Only the node's exact Tailscale IPv4 gets the new exceptions: port 22 owned by
  sshd/systemd; dynamic TCP peer API owned exclusively by tailscaled; RustDesk
  reserved TCP ports 21115–21117 published by docker-proxy. Existing 3000/8020
  baseline stays in place. Wildcards remain failures regardless of process.
  The sole IPv4 wildcard exception is 8910 with active UFW, default incoming
  deny/reject, and relevant permits limited to lo, 127.0.0.1 or 172.19.0.0/16.
  Public permits (including ranges/all ports) invalidate that exception;
  comments do not establish restrictions. Unknown UFW profiles fail closed.
  HTTP documentation probes cover ForgeHub, ForgeVault and Darckware domains.

RustDesk source reference: [official Docker and ports documentation](https://rustdesk.com/docs/en/self-host/rustdesk-server-oss/docker/).
Bridge networking needs functional validation for NAT and relay after application.
`ss -p` requires sufficient privilege to identify owners; missing ownership fails
closed for the added Tailscale infrastructure and RustDesk exceptions.

RustDesk SHA-256:

- prepared: `74effebf98488143c82fafeea3137f506030ea3edb448a889f4caa416ae696a5`
- original: `066eabffb05521811f725ee68d2a0dde790c41b2e62a2e1eb22227ddc1002b31`

## Checks before application

```bash
cd /root/project/darckware/backend
.venv/bin/python -m pytest isolated_tests/test_production_docs.py -q
cd /root/project/darckware
docker compose --profile app config -q
cd /root/project/forgehub
backend/.venv/bin/python -m pytest ops/athos/tests/test_eco047.py -q
cd /root/project/remoto
docker compose config -q
```

The production docs regression failed before the fix (`/openapi.json`: 200,
expected 404), then passed. ECO-047 regression cases cover accepted owners,
wrong/missing/mixed owners, arbitrary application wildcards, UFW inactive/error,
permissive default/rules, spoofed comments, and all nine public docs probes.
Read-only execution of the prepared check on the unchanged host correctly fails
for the five RustDesk wildcards; SSH, Tailscale and filtered 8910 are accepted.

## Application plan — operator only after independent review and approval

1. Record approved commits and clean deployment checkout. Preserve existing
   unrelated edits; do not deploy a dirty repository wholesale. Save current
   Darckware backend image ID/tag, installed verifier and RustDesk configuration
   to an operator snapshot. Preserve RustDesk image IDs and `data` unchanged.
2. Darckware: use its normal build/deploy gate to rebuild/recreate **backend only**
   from the approved commit, with the prepared Compose environment. Check
   `/health` = 200 and `/docs`, `/redoc`, `/openapi.json` = 404 on loopback and
   Tailscale port 8020. Verify normal authentication/API and Lara bridge reachability.
3. RustDesk: ensure the Tailscale address exists; check the rendered Compose and
   apply `docker compose up -d --no-build --pull never hbbs hbbr` from `remoto`.
   No pull, data reset or firewall change is required by this patch. Inspect
   `docker compose ps`, `docker port hbbs`, `docker port hbbr`, `ss -ltnpH` and
   `ss -lunpH`. Require the exact Tailscale publications above, no host wildcards
   on 21115–21119, and no published 21118/21119. From two tailnet clients verify
   ID registration/heartbeat and a forced-relay remote session. Test that public
   interfaces cannot reach the ports. Review Docker forwarding/Tailscale ACLs if
   reachability differs; do not open public access to compensate.
4. Auditor: compare release copy to live verifier for intervening changes before
   installing the reviewed file, preserving permissions. Re-run isolated tests.
   Run a read-only `check_public_interfaces()` first; then use the normal
   `python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-047`
   to record the production result (this latter command writes audit state).
   Require ECO-047 OK and retain socket, firewall and HTTP status evidence.

## Rollback — operator only

- Darckware: restore the saved backend image and previous Compose environment,
  recreate backend through the normal gate, verify health/authentication. This
  restores the previous documentation exposure; record that security regression.
  No migration is involved. For source rollback, revert only the ECO-047 commit.
- RustDesk: copy `compose.pre-eco-047.yml` to `compose.yml`, validate config, then
  use the same no-build/no-pull recreation command. This restores host networking
  and its known wildcard findings. Keep `data` and image IDs intact. In a separate
  clean copy, `patch -R -p1 < rustdesk-compose.patch` also restores the original.
- Auditor: restore the saved live verifier and its mode, re-run the read-only
  check; record that the previous baseline can report the known false positives.
  Source rollback reverts only the ForgeHub ECO-047 commit.

No production OK or remote-access success is claimed before operator application.

## Reconciliation on 2026-11-12

See [read-only preflight and merge evidence](../reports/2026-11-12-eco047-preflight.md).
RustDesk already matches the prepared Compose hash and exact tailnet publications;
Darckware health/docs responses already match the intended route behavior. Recheck
before any restart or redeploy. The repository verifier now merges the live
classification and diagnostics with the release changes; it is not installed.
One live Tailscale IPv6 peer-API listener remains outside the authorized IPv4
exception. Do not declare ECO-047 OK or widen that exception without review.
