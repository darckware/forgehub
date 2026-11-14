# Auditor frequencies: activation plan

Approved by Marcelo on 2026-11-13. Each Auditor check gets a frequency
(daily, weekly, monthly, quarterly). The audit schedule moves from the single
Hermes cron `ecosystem-weekly-audit` (Athos, Sunday 19:00, every enabled check
at once) to four Operação 24x7 routines. Each routine runs one tier's checks.

| Routine (Athos) | Tier | Schedule (America/Sao_Paulo) | Checks |
|---|---|---|---|
| Auditoria diária | daily | `0 19 * * *` | 005 006 007 009 010 015 018 020 022 046 047 049 051 052 054 057 059 060 061 064 066 |
| Auditoria semanal | weekly | `0 19 * * 0` | 004 008 012 013 014 017 019 024 027 028 029 039 040 041 044 045 053 062 063 065 |
| Auditoria mensal | monthly | `0 19 1 * *` | 001 002 003 011 016 023 025 026 030 031–038 042 043 |
| Auditoria trimestral | quarterly | `0 19 1 1,4,7,10 *` | 058 (restore drill; stays disabled until its activation condition is met) |

Checks not in the list (048, 050, 055, 056, all disabled, and 021, retired)
stay `weekly`, the frequency the Sunday audit always gave them.

## How it works

- `company.audit_checks.frequency` holds the tier. Migration `e4a6c8d0f2b3`
  fills it from the table above by check name. An admin changes it on the
  Auditor page (`PUT /api/v1/audit/checks/{id}/frequency`).
- An audit routine is `agent_routines.kind = 'audit'` with `audit_frequency`
  set. The database allows one routine per tier. When an occurrence is due, it
  does **not** become a Messages task, and no LLM runs. The routine loop claims
  the run and calls the Auditor runner for that tier's enabled checks
  (`run_audit_batch`). It writes the batch id to
  `agent_routine_runs.audit_batch_id` before the batch starts.
  - When the batch finishes, the run is `completed`.
    `evidence_received` = every enabled check of the tier has a result in the
    batch.
  - A failing check still opens its owner's correction Task, as before.
  - A batch that is still `running` after its deadline is recorded as
    `failed`. This happens when the backend restarted mid-batch.
- Batches run one at a time. On a Sunday that is also the 1st, the tiers run
  in sequence.
- Audit runs do not use Athos's daily run budget.
- Every check command now carries `FORGEHUB_AUDIT_FREQUENCY=<tier>`. The
  verifier writes that value to Foundation's `check_interval`. Before this
  change, every check was recorded as `weekly`.
- ECO-023 accepts either the four enabled routines with the schedules above
  or, until then, the legacy cron. If the routines pass and the cron is still
  active, ECO-023 passes with a "disable it" note.
- On the Auditor page, the cron monitor shows "Substituído pelas rotinas"
  ("replaced") once the four routines are on and the cron is paused.
- ECO-066 no longer counts a running audit batch as "missing demand".

## Activation (supervisor)

Run each step only after the one before it is confirmed.

1. **Publish the verifier first.** The live verifier is
   `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`. Copy
   `ops/athos/checklist_verifier.py` and `ops/athos/module_health.py` over it
   (keep a `.bak` of each). Do this before the backend: an old ECO-023 does
   not know about the routines and fails once the cron is paused. An old
   ECO-066 counts running audit batches as missing a demand.
   ```bash
   cd /root/.hermes/profiles/athos/scripts
   cp checklist_verifier.py checklist_verifier.py.bak-pre-frequencies
   cp module_health.py module_health.py.bak-pre-frequencies
   cp /root/project/forgehub/ops/athos/checklist_verifier.py /root/project/forgehub/ops/athos/module_health.py .
   python3 checklist_verifier.py --check ECO-023   # still OK through the legacy cron
   ```
2. **Deploy ForgeHub.** Deploy the backend and frontend with the usual release
   procedure. The migration runs to `e4a6c8d0f2b3`. Check:
   ```sql
   SELECT frequency, count(*) FROM company.audit_checks GROUP BY 1;
   -- daily 21, weekly 25 (20 + 5 disabled/retired), monthly 19, quarterly 1
   ```
   Nothing changes in behavior yet. The cron still runs every check on Sunday.
3. **Create the four routines, disabled.**
   ```bash
   docker exec forgehub-backend python -m app.core.audit_routines
   # {'created': ['daily', 'weekly', 'monthly', 'quarterly'], 'existing': [], 'error': None}
   ```
   The command is idempotent. A second run creates nothing and changes
   nothing.
4. **Enable the four routines.** Go to Operação 24x7 → Programação. Use
   "Retomar" (resume) on Auditoria diária, semanal, mensal and trimestral.
   Enabling a routine re-arms its cursor from now, so no past occurrence is
   replayed. Optional smoke test: run "Executar agora" on *Auditoria diária*.
   The run appears in Execuções as `completed`, with "Lote no Auditor" and
   `N/N ok`.
5. **Verify the first scheduled daily run (19:00).** Check all of these:
   - Operação 24x7 → Execuções has an *Auditoria diária* run that is
     `completed`. The run has `audit_batch_id` set and `evidence_received = true`.
   - Auditor → Faixas de frequência → Diária shows "Último lote completo" at
     today 19:00.
   - `SELECT requested_by, count(*) FROM company.audit_check_runs WHERE batch_id = '<id>' GROUP BY 1;`
     returns `routine | 21`.
   - Foundation: `SELECT check_interval, count(*) FROM audit.foundation_checklist GROUP BY 1;`
     on `hindsight_postgres` shows `daily` for those 21 checks.
6. **Pause the Hermes cron.** Do this only after step 5 passes. Use pause, not
   remove: pause keeps the job and its history.
   ```bash
   hermes -p athos cron list | grep ecosystem-weekly-audit   # id 2718ef651fec
   hermes -p athos cron pause 2718ef651fec
   ```
   Then check:
   - The Auditor monitor shows "Substituído pelas rotinas".
   - `python3 checklist_verifier.py --check ECO-023` reports
     "scheduled by the four Operação 24x7 audit routines" with no "disable it"
     note.
7. **The following Sunday,** check that *Auditoria semanal* ran at 19:00 and
   that no `requested_by='cron'` batch appeared.

## Rollback

Any step can be undone without losing data:

- **Return to the weekly cron:**
  1. Resume the cron: `hermes -p athos cron resume 2718ef651fec`.
  2. Pause the four routines in Operação 24x7.
  3. The Auditor monitor goes back to watching the cron (`schedule_source = hermes_cron`).
- **Undo the deploy:**
  1. Redeploy the previous image.
  2. Run `alembic downgrade d2e4f6a8b0c1`. This deletes the audit routines and
     their runs. Check results in `audit_check_runs` stay, since only the
     `frequency` column is dropped.
  3. Resume the cron if it was paused.
- **Undo the verifier:**
  1. Restore the `.bak-pre-frequencies` copies.
  2. Resume the cron first, because the old ECO-023 accepts only the cron.

## Notes

- The legacy endpoint `/api/v1/audit/run-internal` still runs every check when
  called without `?frequency=`. The cron script is unchanged, so resuming the
  cron is a complete rollback.
- Evidence validity now depends on frequency: daily 2 days, weekly 8, monthly
  32, quarterly 93. A monthly check is no longer reported "expired" a week
  after it ran.
