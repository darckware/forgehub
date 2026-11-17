"""The completion report every Messages dispatch must end with (2026-10-24).

A run's exit code only says the CLI stopped, not that the work is done: on
2026-10-24 several of Aramis' runs ended mid-task ("Now let me...") with
exit 0 and were filed under Completed. So the runner input carries a
contract asking for a last `STATUS: DONE | PARTIAL | BLOCKED` line, and
`_finalize_dispatch` (api/routes/demand.py) only records `completed` for
DONE. PARTIAL, BLOCKED or no line at all (a reply cut short, an agent that
ignored the contract) become `failed` with the reason in `dispatch_error`,
where the result is still kept and the reprocess button already exists.
"""
import re

COMPLETION_STATUSES = ("DONE", "PARTIAL", "BLOCKED")

COMPLETION_CONTRACT = (
    "---\n"
    "Relatório de conclusão (obrigatório): termine a resposta com uma linha final "
    "exatamente neste formato:\n"
    "STATUS: DONE | PARTIAL | BLOCKED\n"
    "- DONE: tudo o que foi pedido está feito e verificado; antes dessa linha, "
    "liste as evidências (arquivos, commits, testes, comandos e resultados).\n"
    "- PARTIAL: parte foi feita; diga o que falta e por quê.\n"
    "- BLOCKED: não foi possível avançar; diga o que impede e o que é preciso.\n"
    "- Se o que impede é uma autorização ou decisão do Marcelo, a linha final é "
    "STATUS: BLOCKED | AUTORIZAÇÃO: <o que ele precisa autorizar ou decidir>. "
    "A mensagem vai para a aprovação dele e volta para você quando ele aprovar.\n"
    "- Se você fez tudo o que podia e só espera a resposta de uma pessoa (instrutor, "
    "cliente, outro agente), a linha final é "
    "STATUS: BLOCKED | AGUARDANDO RESPOSTA: <o que falta e de quem>.\n"
    "Sem essa linha, a mensagem é registrada como falha."
)

# Tolerates the markdown agents wrap lines in (`**STATUS: DONE**`, a list
# bullet, backticks) and an evidence note after the status, introduced by `|`
# or by an em/en dash (`**STATUS: DONE** — Briefing enviado`, how Athos' routines
# end, 2026-11-15), but nothing else on the line, so prose that merely mentions
# a status ("STATUS: DONE when tests pass") doesn't count. A plain hyphen stays
# refused: it reads as prose ("STATUS: DONE - commit abc").
_STATUS_LINE = re.compile(
    r"^[\s>*_`#-]*STATUS\s*:\s*[*_`]*\s*(DONE|PARTIAL|BLOCKED)\b[\s*_`.]*(?:[|\u2014\u2013](.*))?$",
    re.IGNORECASE,
)
_STATUS_WORD = re.compile(r"[\s*_`]*(?:DONE|PARTIAL|BLOCKED)\b", re.IGNORECASE)


def _is_evidence_note(note: str) -> bool:
    """Whether what follows the `|` is a real note. The contract's own model
    line, `STATUS: DONE | PARTIAL | BLOCKED`, has the same shape, so a second
    status in any `|` segment means no status was chosen, and an empty note may
    be that line cut short. Fails closed, also for `STATUS: DONE | done in abc`:
    a false failure can be reprocessed, a false DONE goes unnoticed."""
    return bool(note.strip(" \t*_`.|")) and not any(
        _STATUS_WORD.match(segment) for segment in note.split("|")
    )


def with_completion_contract(prompt: str) -> str:
    """The runner input: the message prompt followed by the contract."""
    return f"{prompt}\n\n{COMPLETION_CONTRACT}"


def parse_completion_report(text: str) -> tuple[str | None, str | None]:
    """(status, note) of the last `STATUS:` report in `text`; (None, None)
    when absent. The last one wins: an agent may restate it after a
    correction. A line that isn't a report (prose, the contract's model line)
    is skipped."""
    for line in reversed((text or "").splitlines()):
        match = _STATUS_LINE.match(line)
        if match and (match.group(2) is None or _is_evidence_note(match.group(2))):
            note = match.group(2).strip(" \t*_`") if match.group(2) is not None else None
            return match.group(1).upper(), note or None
    return None, None


def parse_completion_status(text: str) -> str | None:
    """The status of the last `STATUS:` report in `text`, or None when absent."""
    return parse_completion_report(text)[0]


# 2026-11-16 (Marcelo, ECO-054 5a/5b): two ways to stop that are not failures.
# Only an explicit label right after the `|` counts -- never a guess from prose,
# so a real blocker can't hide as a "wait" by wording alone.
_BLOCKED_KINDS = (
    ("awaiting_authorization", re.compile(r"^AUTORIZA[ÇC][ÃA]O\s*:\s*(\S.*)$", re.IGNORECASE | re.DOTALL)),
    ("waiting_reply", re.compile(r"^AGUARDANDO\s+RESPOSTA\s*:\s*(\S.*)$", re.IGNORECASE | re.DOTALL)),
)


def blocked_outcome(status: str | None, note: str | None) -> tuple[str, str] | None:
    """(outcome, what is needed) for `STATUS: BLOCKED | AUTORIZAÇÃO: ...` or
    `STATUS: BLOCKED | AGUARDANDO RESPOSTA: ...`; None for anything else."""
    if status != "BLOCKED" or not note:
        return None
    for outcome, pattern in _BLOCKED_KINDS:
        match = pattern.match(note.strip())
        if match:
            needed = match.group(1).strip()
            if needed.startswith("<") and needed.endswith(">"):
                return None  # the contract's own model line, echoed
            return outcome, needed[:2000]
    return None


def completion_failure_reason(status: str | None) -> str | None:
    """Why a cleanly-exited run still isn't completed work; None for DONE.
    Never say "uncertain" here: core/demand_workflow.py's
    requires_reconciliation reads that word as an unknown run outcome and
    would block reprocessing a run that is known to have ended."""
    if status == "DONE":
        return None
    if status is None:
        return ("The agent run ended without the completion report "
                "(STATUS: DONE | PARTIAL | BLOCKED); the work may be unfinished.")
    return f"The agent reported STATUS: {status}; the work is not finished."
