#!/usr/bin/env python3
"""ECO-060: only forgehub-remote-access may read a *_SSH_KEY secret in ForgeVault (Athos).

Read-only. Scans every SECRET_READ/SECRET_REVEAL in ForgeVault's audit_logs from MARKER on, in
one aggregated query with no row limit. MARKER is the check's creation, fixed here on purpose:
the reads known from 2026-11-06 (#42179) stay out, and nothing else can move it.

Exit 0 = nothing found, 1 = at least one other identity read a key, 2 = not verified. Not
verified is never a pass: no database access, no allowed identity, no key or no audit rows to
read, or a read by another identity of a secret that no longer has a row to classify it.

Prints identity, secret name, count and last time. It selects no value and no metadata.

A key secret is a name ending in `_SSH_KEY`, or in `_SSH_KEY_<YYYYMMDDHHMMSS>_<8 HEX>`
(2026-11-12): until then ForgeHub's rotations wrote that suffix AFTER the purpose, and those
secrets keep their names, so the old ends-with match missed every read of them. ForgeHub now
puts the suffix before the purpose (`WS_<CLIENT>_<MACHINE>_<SUFFIX>_SSH_KEY`). The exact old
suffix is matched, not any `_SSH_KEY_...`, so `X_SSH_KEYS` or `X_SSH_KEY_PASSPHRASE` aren't
counted as keys.

ACKNOWLEDGED_READS lists single audit rows Marcelo confirmed as legitimate, by row id, so the
exception covers exactly those reads and nothing that happens later. The 7 reads by `aramis` on
2026-11-08 23:49:48Z were the restricted-secret activation of the 4b6ef28 publication, which he
asked for (Marcelo, 2026-11-12: "sim, fui eu que pedi, pode registrar"). Record in the
Foundation: 47_migrations/2026-11-12-eco060-acknowledged-activation-reads.md.
"""
from __future__ import annotations

import json
import subprocess
import sys

MARKER = "2026-11-06T21:36:00+00:00"
ALLOWED_IDENTITY = "forgehub-remote-access"
CONTAINER = "forgevault-postgres-1"
OUTPUT_BUDGET = 3400  # the verifier cuts its notes at 4000 characters

EXIT_OK, EXIT_FOUND, EXIT_NOT_VERIFIED = 0, 1, 2

# ForgeVault audit_logs.id of each read Marcelo confirmed; never a time window or an identity.
ACKNOWLEDGED_READS = (
    # aramis, 2026-11-08 23:49:48Z, activation of the restricted SSH keys (4b6ef28)
    "52b8ccd8-e3a4-4c0a-ae39-372eae860b49",  # ..._GAT_ADM_PC01_SSH_KEY
    "2a1a8bbb-e60e-46f0-8aa7-cd608636e1d6",  # ..._GAT_GES_NB01_SSH_KEY
    "c477fe61-3014-4c4c-9f77-1ea766cbf3e3",  # ..._DESK_SEMED_ADMIN_SSH_KEY
    "501a9de2-f8ee-4115-b6f4-095afebc6a28",  # ..._SRV_APP01_SSH_KEY
    "0af727c4-0551-464b-bc1d-cd5d493a6000",  # ..._SRV_APP02_SSH_KEY
    "f9cfc909-c67b-4e9b-9364-6f212627d820",  # ..._SRV_SUP_SSH_KEY
    "7b7fba32-d3fc-4b7b-821e-8bdbb1d45b7e",  # ..._VMI3547248_SSH_KEY
)

# :marker, :allowed and :acknowledged are bound by psql, never formatted into the text.
QUERY = """
WITH reads AS (
    SELECT l.actor_id, l."timestamp" AS read_at, s.id AS secret_id, s.name AS secret_name,
           coalesce(sa.name, u.email, l.actor_id) AS identity,
           l.actor_type = 'Service' AND sa.name IS NOT DISTINCT FROM :'allowed' AS allowed,
           l.id::text = ANY(string_to_array(:'acknowledged', ',')) AS acknowledged
    FROM audit_logs l
    LEFT JOIN secrets s ON s.id = l.resource_id
    LEFT JOIN service_accounts sa ON sa.id::text = l.actor_id
    LEFT JOIN users u ON u.id::text = l.actor_id
    WHERE l.action IN ('SECRET_READ', 'SECRET_REVEAL')
      AND l."timestamp" >= :'marker'::timestamptz
), key_reads AS (
    SELECT * FROM reads WHERE upper(secret_name) ~ '_SSH_KEY(_[0-9]{14}_[0-9A-F]{8})?$'
)
SELECT json_build_object(
    'audit_rows', (SELECT count(*) FROM audit_logs WHERE action IN ('SECRET_READ', 'SECRET_REVEAL')),
    'scanned', (SELECT count(*) FROM reads),
    'key_secrets', (SELECT count(*) FROM secrets WHERE upper(name) ~ '_SSH_KEY(_[0-9]{14}_[0-9A-F]{8})?$'),
    'allowed_accounts', (SELECT count(*) FROM service_accounts WHERE name = :'allowed'),
    'allowed_reads', (SELECT count(*) FROM key_reads WHERE allowed),
    'acknowledged_reads', (SELECT count(*) FROM key_reads WHERE acknowledged AND NOT allowed),
    'unclassified', (SELECT count(*) FROM reads
                     WHERE secret_id IS NULL AND NOT allowed AND NOT acknowledged),
    'findings', coalesce((
        SELECT json_agg(f ORDER BY f.last_read DESC, f.identity, f.secret)
        FROM (
            SELECT identity, secret_name AS secret, count(*) AS reads,
                   to_char(max(read_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_read
            FROM key_reads WHERE NOT allowed AND NOT acknowledged GROUP BY identity, secret_name
        ) f
    ), '[]'::json)
);
"""


def read_audit(marker: str = MARKER) -> dict:
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
         "-v", f"marker={marker}", "-v", f"allowed={ALLOWED_IDENTITY}",
         "-v", f"acknowledged={','.join(ACKNOWLEDGED_READS)}",
         "-U", "forgevault", "-d", "forgevault", "-At", "-f", "-"],
        input=QUERY, capture_output=True, text=True, timeout=40, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"psql exit {result.returncode}")
    return json.loads(result.stdout)


def evaluate(data: dict) -> tuple[int, str]:
    if data["allowed_accounts"] != 1:
        return EXIT_NOT_VERIFIED, f"NOT VERIFIED: service account {ALLOWED_IDENTITY} not found"
    if not data["key_secrets"] or not data["audit_rows"]:
        return EXIT_NOT_VERIFIED, "NOT VERIFIED: no *_SSH_KEY secret or no read in the audit log"
    findings = data["findings"]
    if findings:
        total = sum(row["reads"] for row in findings)
        lines = [f"FAIL: {total} read(s) of *_SSH_KEY by an identity other than "
                 f"{ALLOWED_IDENTITY} since {MARKER}"]
        used = len(lines[0])
        for position, row in enumerate(findings):
            line = (f"identity={row['identity']} secret={row['secret']} "
                    f"count={row['reads']} last={row['last_read']}")
            if used + len(line) + 1 > OUTPUT_BUDGET:
                lines.append(f"... {len(findings) - position} more identity/secret pair(s) omitted")
                break
            lines.append(line)
            used += len(line) + 1
        if data["unclassified"]:
            lines.append(f"{data['unclassified']} other read(s) could not be classified")
        return EXIT_FOUND, "\n".join(lines)
    if data["unclassified"]:
        return EXIT_NOT_VERIFIED, (
            f"NOT VERIFIED: {data['unclassified']} read(s) since {MARKER} point at a secret "
            "with no row, so the name can't be checked"
        )
    return EXIT_OK, (
        f"OK: no other identity read a *_SSH_KEY since {MARKER}; {data['scanned']} read(s) "
        f"scanned, {data['allowed_reads']} of them by {ALLOWED_IDENTITY} on "
        f"{data['key_secrets']} key secret(s); {data.get('acknowledged_reads', 0)} read(s) "
        "acknowledged by Marcelo left out"
    )


def main() -> int:
    try:
        code, notes = evaluate(read_audit())
    except (OSError, RuntimeError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        code, notes = EXIT_NOT_VERIFIED, f"NOT VERIFIED: ForgeVault audit unreadable ({type(exc).__name__})"
    print(notes)
    return code


if __name__ == "__main__":
    sys.exit(main())
