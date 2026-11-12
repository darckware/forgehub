#!/usr/bin/env python3
"""ECO-060: only forgehub-remote-access may read a *_SSH_KEY secret in ForgeVault (Athos).

Read-only. Scans every SECRET_READ/SECRET_REVEAL in ForgeVault's audit_logs from MARKER on, in
one aggregated query with no row limit. MARKER is the check's creation, fixed here on purpose:
the reads known from 2026-11-06 (#42179) stay out, and nothing else can move it.

Exit 0 = nothing found, 1 = at least one other identity read a key, 2 = not verified. Not
verified is never a pass: no database access, no allowed identity, no key or no audit rows to
read, or a read by another identity of a secret that no longer has a row to classify it.

Prints identity, secret name, count and last time. It selects no value and no metadata.

A key secret is any name CONTAINING `_SSH_KEY` (2026-11-12), not only one ending in it:
rotations wrote `WS_<CLIENT>_<MACHINE>_SSH_KEY_<SUFFIX>` before ForgeHub moved the suffix in
front of the purpose (`WS_<CLIENT>_<MACHINE>_<SUFFIX>_SSH_KEY`), and those secrets keep their
names, so a suffix-match missed every read of them.
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

# :marker and :allowed are bound by psql, never formatted into the text.
QUERY = """
WITH reads AS (
    SELECT l.actor_id, l."timestamp" AS read_at, s.id AS secret_id, s.name AS secret_name,
           coalesce(sa.name, u.email, l.actor_id) AS identity,
           l.actor_type = 'Service' AND sa.name IS NOT DISTINCT FROM :'allowed' AS allowed
    FROM audit_logs l
    LEFT JOIN secrets s ON s.id = l.resource_id
    LEFT JOIN service_accounts sa ON sa.id::text = l.actor_id
    LEFT JOIN users u ON u.id::text = l.actor_id
    WHERE l.action IN ('SECRET_READ', 'SECRET_REVEAL')
      AND l."timestamp" >= :'marker'::timestamptz
), key_reads AS (
    SELECT * FROM reads WHERE strpos(upper(secret_name), '_SSH_KEY') > 0
)
SELECT json_build_object(
    'audit_rows', (SELECT count(*) FROM audit_logs WHERE action IN ('SECRET_READ', 'SECRET_REVEAL')),
    'scanned', (SELECT count(*) FROM reads),
    'key_secrets', (SELECT count(*) FROM secrets WHERE strpos(upper(name), '_SSH_KEY') > 0),
    'allowed_accounts', (SELECT count(*) FROM service_accounts WHERE name = :'allowed'),
    'allowed_reads', (SELECT count(*) FROM key_reads WHERE allowed),
    'unclassified', (SELECT count(*) FROM reads WHERE secret_id IS NULL AND NOT allowed),
    'findings', coalesce((
        SELECT json_agg(f ORDER BY f.last_read DESC, f.identity, f.secret)
        FROM (
            SELECT identity, secret_name AS secret, count(*) AS reads,
                   to_char(max(read_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_read
            FROM key_reads WHERE NOT allowed GROUP BY identity, secret_name
        ) f
    ), '[]'::json)
);
"""


def read_audit(marker: str = MARKER) -> dict:
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
         "-v", f"marker={marker}", "-v", f"allowed={ALLOWED_IDENTITY}",
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
        f"{data['key_secrets']} key secret(s)"
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
