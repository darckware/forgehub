"""Guard for Auditor remediation commands.

`AuditCheck.remediation_command` is not executed verbatim: it is the
*suggested* correction handed to Athos (an LLM agent) when an administrator
approves a remediation. A stale suggestion therefore steers Athos straight
into the stale action. The 2026-10-02 review found exactly that -- restarts
of per-profile `hermes-gateway-<profile>.service` units that stopped
existing with the multiplex gateway (and that the gateway policy forbids:
Foundation `52_policies/hermes-gateway-operations.md`), the
`company_postgres`/`foundation_postgres` containers retired on 2026-09-04,
and scripts that were never on disk.

Two levels, because they fail at different times:
- structural problems (retired targets, policy violations) are wrong no
  matter what the host looks like -- refused when a check is saved;
- missing files depend on the host -- a script may be added after the check
  is saved -- so they are only refused right before delegating.
"""
import os
import re
from collections.abc import Callable

RETIRED_CONTAINERS = ("company_postgres", "foundation_postgres")

_GATEWAY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"hermes-gateway-[\w$.{}-]+"),
        "per-profile gateway units no longer exist; the only permitted restart is "
        "`systemctl --user restart hermes-gateway`",
    ),
    (
        re.compile(r"hermes\s+gateway\s+run"),
        "starting a second Hermes gateway is forbidden by the gateway policy",
    ),
    (
        re.compile(r"\b(pkill|killall)\b[^;&|]*hermes|\bkill\s+-9\b"),
        "killing Hermes processes is forbidden by the gateway policy",
    ),
)
_FILE_REFERENCES = (
    re.compile(r"(?:^|[\s;&|(])(?:bash|sh|python3?)\s+(/[^\s;&|)]+)"),
    re.compile(r"<\s*(/[^\s;&|)]+)"),
)


def structural_remediation_problems(command: str | None) -> list[str]:
    if not command:
        return []
    problems = [
        f"references retired container {name} (removed in the 2026-09-04 topology migration)"
        for name in RETIRED_CONTAINERS
        if re.search(rf"\b{name}\b", command)
    ]
    problems.extend(reason for pattern, reason in _GATEWAY_RULES if pattern.search(command))
    return problems


def referenced_files(command: str | None) -> list[str]:
    """Absolute paths the command executes (`bash|sh|python3 <path>`) or reads
    from (`< <path>`), in order of appearance, deduplicated."""
    if not command:
        return []
    found: list[str] = []
    for pattern in _FILE_REFERENCES:
        found.extend(path for path in pattern.findall(command) if path not in found)
    return found


def remediation_problems(
    command: str | None, *, path_exists: Callable[[str], bool] = os.path.exists
) -> list[str]:
    """`path_exists` must answer for the *host*: inside the backend container
    `/root/.hermes/profiles` is mounted elsewhere, so the route resolves
    existence through the bridge and passes the answer in."""
    problems = structural_remediation_problems(command)
    problems.extend(
        f"referenced file does not exist: {path}"
        for path in referenced_files(command)
        if not path_exists(path)
    )
    return problems
