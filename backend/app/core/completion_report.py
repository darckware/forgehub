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
    "Sem essa linha, a mensagem é registrada como falha."
)

# Tolerates the markdown agents wrap lines in (`**STATUS: DONE**`, a list
# bullet, backticks) but nothing else on the line, so prose that merely
# mentions a status ("STATUS: DONE when tests pass") doesn't count.
_STATUS_LINE = re.compile(
    r"^[\s>*_`#-]*STATUS\s*:\s*[*_`]*\s*(DONE|PARTIAL|BLOCKED)\b[\s*_`.]*$",
    re.IGNORECASE,
)


def with_completion_contract(prompt: str) -> str:
    """The runner input: the message prompt followed by the contract."""
    return f"{prompt}\n\n{COMPLETION_CONTRACT}"


def parse_completion_status(text: str) -> str | None:
    """The status of the last `STATUS:` line in `text`, or None when absent.
    The last one wins: an agent may restate it after a correction."""
    for line in reversed((text or "").splitlines()):
        match = _STATUS_LINE.match(line)
        if match:
            return match.group(1).upper()
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
