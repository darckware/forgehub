# Personal group capture verification — forwarding #41682

Verified on 2026-10-29 in `/root/project/forgehub`, starting from clean `develop` at `2af5af0`. This is evidence for the authorized correction, not a new diagnostic request. Attempt #41598, message `17503e23-ced6-429b-9ab0-d4fbb88bc16e`, stopped before preflight with `Not inside a trusted directory and --skip-git-repo-check was not specified.` No effects or provider reset are inferred from that attempt.

Preflight commands `pwd`, `git status --short --branch`, `git worktree list`, and `git log` succeeded. The MCP entry point is `backend/app/mcp/factory_server.py`; `personal_contacts.register` registers `personal_groups` only for allowed agents. No ForgeHub connector was exposed in this runtime's tool catalog; verification used the repository's real MCP registration and API tests.

The required implementation already exists in history (`dab6be5`, `721ae6c`, and `f882312`) and is present in the starting checkout. Group history returns a content-derived `mensagem_ref`. `personal_capture_from_group` calls `/api/v1/personal/groups/captures`, which verifies the monitored inventory and observed message, persists a pending suggestion, and returns its actual database UUID. It preserves source author, timestamp, and group independently of contacts. Acceptance uses the persisted UUID; source references are rejected as UUIDs. Direct demand registration is a separate path for explicit authorization. Existing tests verify source provenance, private access, agent scoping, concurrency, idempotency, contact compatibility, and audit events.

This correction updates the two PostgreSQL test guards to require `ENVIRONMENT=test` and the current central database allowlist. Because those fixtures clear synthetic personal records and the migration test cycles the additive group schema, they also require `PERSONAL_CAPTURE_TEST_RESET=1`. Run only on the disposable test stack, never against production. Production settings and the database allowlist were not changed.

The first test run produced 49 passes and two failures in stale contact MCP fixtures (missing message IDs and outdated suggestion fields). The fixtures now include message IDs and assert origin fields. A new API regression proves that a group reference cannot be accepted directly and that capture returns a persisted UUID before acceptance creates one demand. MCP registration assertions include both group tools.

Verification from `backend/`:

```sh
ENVIRONMENT=test PERSONAL_CAPTURE_TEST_RESET=1 .venv/bin/python -m pytest --noconftest -q tests_unit/test_personal_group_sources.py tests_unit/test_personal_group_mcp_capture.py tests_unit/test_personal_group_capture_api.py tests_unit/test_personal_group_capture_migration.py app/tests/test_personal_groups.py app/tests/test_personal_contacts_mcp.py
```

Result: **52 passed in 7.72s**, using the approved isolated database `forgehub_test` on port `5439`, synthetic records and temporary group files. `--noconftest` avoids unrelated session fixtures; the API and migration tests enforce their own environment, allowlist and explicit reset guards. No production capture, contact, suggestion, demand, outbound message, or diagnostic record was created.

```sh
ENVIRONMENT=test .venv/bin/ruff check app/mcp/personal_groups.py app/mcp/personal_group_sources.py app/mcp/personal_contacts.py app/core/personal_captures.py app/api/routes/personal_groups.py app/tests/test_personal_contacts_mcp.py tests_unit/test_personal_group_capture_api.py tests_unit/test_personal_group_capture_migration.py
```

Result: **All checks passed**.

The scoped Maia overlay at `/root/.hermes/profiles/maia/skills/integrations/forgehub/SKILL.md` contained contradictory instructions: its direct-registration section allowed authorized group demands, while its group section prohibited them. The group section now refers to the authorized direct path, identifies `sugestao.id` as the only acceptance UUID, and prohibits substituting contact suggestions. A pre-edit copy is at `/tmp/forgehub-41682/maia-SKILL.before.md`; the reviewable diff accompanies this report. Shared immutable skills were not edited.

Delivery branch: `fix/personal-group-capture-verification-41682`. No push, merge, production migration, service restart, or deployment was performed in this correction. Repository changes affect tests and documentation; runtime backend behavior was already implemented. Independent Porthus review remains required before integration. Historical release claims do not approve these changes.
