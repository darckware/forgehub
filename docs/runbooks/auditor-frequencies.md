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
  does **not** become a Messages task, and no LLM runs. The routine loop runs
  the tier's enabled checks through the Auditor runner (`run_audit_batch`)
  and writes the batch id to `agent_routine_runs.audit_batch_id` before the
  batch starts.
  - When the batch finishes, the run is `completed`.
    `evidence_received` = every enabled check of the tier has a result in the
    batch.
  - A failing check still opens its owner's correction Task, as before.
- **One batch at a time.** Routine tiers, the manual "Executar lista de
  verificação" (`POST /audit/run`) and the legacy `run-internal` all take the
  same lock:
  - A manual run while a batch is running gets **409**.
  - The legacy cron waits for the lock instead of failing.
  - A routine run turns `running` only once it holds the lock. A tier waiting
    behind another tier stays `scheduled` and is never failed.
- **Interrupted batches.** A batch still `running` after its deadline, counted
  from when it took the lock, is recorded as `failed`. This happens when the
  backend restarted mid-batch.
- **Lost runs.** Every `failed` or `missed` audit run, in any tier, raises one
  *warning* Notification. A monthly or quarterly one also gets **one** retry
  occurrence an hour later (`retry_of_run_id`, unique). A retry is never
  retried again.
- "Executar faixa agora" on the Auditor page uses the tier routine's
  "Executar agora". The batch runs in the background, so the request returns
  at once and never times out on a long tier.
- Audit runs do not use Athos's daily run budget.
- **Verifier.** Every check command now carries `FORGEHUB_AUDIT_FREQUENCY=<tier>`.
  The verifier writes that value to Foundation's `check_interval`.
- **ECO-023** passes only when the four routines are enabled with the
  schedules above *and* each tier has completed a run within one period plus a
  day: daily 2 days, weekly 8, monthly 32, quarterly 93. The window counts from
  the last completed run or from when the routine was enabled
  (`agent_routines.enabled_at`). Until then the legacy cron still satisfies it.
- **ECO-066** gains `failed_audit`: `failed` or `missed` runs of enabled audit
  routines in the last 7 days whose retry did not complete. It no longer
  counts a running audit batch as "missing demand".
- On the Auditor page, the cron monitor shows "Substituído pelas rotinas"
  ("replaced") once the four routines are on and the cron is paused.

## Activation (supervisor)

Run each step only after the one before it is confirmed.

1. **Deploy ForgeHub.** Deploy the backend and frontend with the usual release
   procedure. The migration runs to `e4a6c8d0f2b3`. Check:
   ```sql
   SELECT frequency, count(*) FROM company.audit_checks GROUP BY 1;
   -- daily 21, weekly 25 (20 + 5 disabled/retired), monthly 19, quarterly 1
   ```
   Nothing changes in behavior yet. The cron still runs every check on Sunday.
2. **Publish the verifier, right after the deploy.** The live verifier is
   `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`. Copy
   `ops/athos/checklist_verifier.py` and `ops/athos/module_health.py` over it
   (keep a `.bak` of each).
   - Do this *after* the migration: the new ECO-066 query reads
     `retry_of_run_id`.
   - Do it *before* any audit routine runs: the old ECO-066 would count running
     audit batches as missing a demand.
   ```bash
   cd /root/.hermes/profiles/athos/scripts
   cp checklist_verifier.py checklist_verifier.py.bak-pre-frequencies
   cp module_health.py module_health.py.bak-pre-frequencies
   cp /root/project/forgehub/ops/athos/checklist_verifier.py /root/project/forgehub/ops/athos/module_health.py .
   python3 checklist_verifier.py --check ECO-023   # still OK through the legacy cron
   python3 checklist_verifier.py --check ECO-066   # OK, failed_audit=0
   ```
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
   replayed. It also records `enabled_at`.
5. **Run every tier once now.** Click "Executar agora" on all four routines, or
   "Executar faixa agora" on the Auditor page.
   - The batches queue and run one after another.
   - Why this matters: the last full cron run is the only evidence the
     monthly and quarterly checks have. Their first scheduled occurrence can be
     up to ~38 and ~99 days after it, while their evidence lasts only 32 and
     93 days.
6. **Verify every tier has a complete routine batch.**
   ```sql
   SELECT r.audit_frequency, x.status, x.evidence_received, x.audit_batch_id, x.finished_at
   FROM company.agent_routine_runs x JOIN company.agent_routines r ON r.id = x.routine_id
   WHERE r.kind = 'audit' ORDER BY x.finished_at DESC;
   -- one completed run with evidence_received = true for each of the four tiers
   ```
   - Auditor → Faixas de frequência: all four tiers show "Último lote completo"
     from today, and none says "atrasada".
   - `SELECT requested_by, count(*) FROM company.audit_check_runs WHERE batch_id = '<id>' GROUP BY 1;`
     returns `routine | 21` for the daily batch.
   - On `hindsight_postgres`:
     `SELECT check_interval, count(*) FROM audit.foundation_checklist GROUP BY 1;`
     shows the real tiers.
   - `python3 checklist_verifier.py --check ECO-023` passes.
7. **Verify the first scheduled daily run (19:00).** Operação 24x7 →
   Execuções shows *Auditoria diária* as `completed`, with "Lote no Auditor",
   and no "Auditoria … não concluída" Notification.
8. **Pause the Hermes cron.** Do this only after steps 6 and 7 pass. Use pause,
   not remove: pause keeps the job and its history.
   ```bash
   hermes -p athos cron list | grep ecosystem-weekly-audit   # id 2718ef651fec
   hermes -p athos cron pause 2718ef651fec
   ```
   Then check:
   - The Auditor monitor shows "Substituído pelas rotinas".
   - `python3 checklist_verifier.py --check ECO-023` reports
     "scheduled and run by the four Operação 24x7 audit routines" with no
     "disable it" note.
9. **The following Sunday,** check that *Auditoria semanal* ran at 19:00 and
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
  1. Resume the cron first, because the old ECO-023 accepts only the cron.
  2. Pause the four routines, because the old ECO-066 flags running audit
     batches.
  3. Restore the `.bak-pre-frequencies` copies.

## Notes

- The legacy endpoint `/api/v1/audit/run-internal` still runs every check when
  called without `?frequency=`. The cron script is unchanged, so resuming the
  cron is a complete rollback.
- Evidence validity now depends on frequency: daily 2 days, weekly 8, monthly
  32, quarterly 93. A monthly check is no longer reported "expired" a week
  after it ran.
