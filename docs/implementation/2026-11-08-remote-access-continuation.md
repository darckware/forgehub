# Remote access continuation — implementation ledger

Binding requirements: Marcelo's final per-agent configuration model on 2026-11-06,
requests #42232–#42235, and authorization to finish implementation and publish before
whole-project validation. Continued on 2026-11-08. Goal: agents safely work on registered
workstations and servers through ForgeHub, with auditable operations and revocable authority.

## Work and boundaries

- Reuse the existing `feat/direct-access-panel` worktree. Preserve unrelated main-checkout edits.
- Finish backend configuration, exact task/run authority, terminal credential revocation,
  retention setting/worker, and isolated migrations/security tests.
- Replace temporary opening/closing UI with inline per-agent configuration, three locales,
  confirmation of sensitive coverage, and explicit failure/expiry/empty-scope states.
- Implement file transfers in ForgeHub's bridge; confine host paths, stream bytes, publish
  atomically, verify hashes, and record metadata without file content.
- Finish restricted-secret support in the separate ForgeVault worktree; test and prepare
  activation separately. Do not infer approval for granting any agent access to any machine.
- Verify domain/full suites, build, browser, review, commit and publish exact artifacts.
- Whole-project validation and FileNest baseline/pilot remain the second phase.

## Decisions and evidence

AuthorityDelegation is retained so existing execution foreign keys and history stay valid.
All-machines authority explicitly includes future prepared machines; selected groups are a
snapshot. Empty scope grants nothing. New UI defaults do not grant authority until saved
and sensitive coverage is confirmed by a human administrator.

UI ownership: existing Button, Select, Textarea, ConfirmDialog and domain TanStack Query hooks.
Native select remains browser-owned; configuration edits expand inline, confirmations use the
shared accessible dialog. UI uses the maintained tokens, pt-BR/en/es and current theme.

Initial UI regression proved 9 missing-behavior failures and 2 existing passes before UI changes
(`/tmp/fh-remote-ui-red.log`). Subsequent results and publication evidence are recorded below
once actually verified.

## Release verification — resumed after terminal interruption

Marcelo authorized completion/publication ("finaliza a instalação"). Scope: this ForgeHub
branch, its host bridge, and the companion ForgeVault restricted-secret release. Publication
does not change machine accounts, fleet permissions, Foundation rules, installed skills or
the Hermes gateway. Private release manifests record image IDs, revisions and backup checksums.

Fresh checks on the release tree:

- Backend: `ENVIRONMENT=test .venv/bin/pytest -q` — **2,011 passed, 21 skipped**.
  Includes isolated Linux upload/command/download acceptance. The prior fixture-key path
  and in-memory dispatch-session failures are resolved. No production database is used.
- Frontend: `npm test -- --run --maxWorkers=2` — **483 passed in 107 files**.
- Bridge: `../backend/.venv/bin/pytest -q` — **163 passed**.
- Frontend: `npm run build` — locale parity, TypeScript and Vite passed; the existing
  large-bundle warning remains.
- Ruff on every changed/new backend Python file and `git diff --check` — passed.
  Full backend lint retains an unrelated F811 in `test_moodle_student_batch.py`.
- ForgeVault: `dotnet test ForgeVault.slnx --no-restore` — **100 passed**;
  activation/rollback tests — **9 passed**. Existing EF reference warnings remain.
- Browser evidence from the preceding continuation: desktop 1440 px and mobile 390 px,
  no horizontal overflow, sensitive-coverage confirmation, loading/error behavior and no
  uncaught browser errors. Fixture requests never change production agent permissions.

The independent reviewer found three issues and then confirmed all resolved: a refreshed
shared task lock covers operation acceptance; explicit dispatch rejection revokes the
reserved run credential before clearing its ID; transfer MCP calls allow 650 seconds.
No important issue remained. This resumption adds only a test lint annotation and publication
evidence to ForgeHub after that review.

Ruling: protect the **seven active, currently referenced SSH keys**, rather than reactivating
the retired eighth key. Live metadata and server references agree: the former `srv-app05`
key is revoked and unreferenced. The activation script keeps its default exact count of eight
and accepts an explicit `--expected-key-count 7`, covered by regression tests. If inventory
changes again, reconcile the manifest before activation.

## Behavior and boundaries

- Migration revokes existing temporary direct openings. A human administrator must save the
  intended per-agent configuration; publication itself grants no machine access.
- A dispatch credential is limited to its exact still-running task and revoked on terminal
  reconciliation, including rejected dispatches. Uncertain runner outcomes remain blocked.
- Transfers require POSIX targets/GNU coreutils, allow at most 200 MiB per file, confine local
  paths to task/run directories, publish atomically and verify SHA-256. Windows transfer
  explicitly returns unsupported; Windows command support is unchanged.
- Output expires after configured retention (default 90 days); execution/audit metadata and
  active/unfinished results remain.
- Restricted values need explicit grants. Administrative policy writers can still change
  restrictions/grants, with audit; this is not host/root isolation. New alert delivery and
  shared skill publication remain separate work.
- Whole-project validation and the FileNest baseline/pilot remain the second phase.

## Publication

Exact artifacts, backup/restore and migration rehearsal, activation results and service
health are recorded in `/root/.forgehub/releases/remote-access-*`. Append final publication
results after activation and health checks complete. Never commit private dumps.
