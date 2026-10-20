"""Builds the CLI prompt for an Inbox dispatch (api/routes/demand.py's
/dispatch).

Each host-bridge agent-run is a fresh, stateless process (`claude` runs with
`--no-session-persistence`) -- there is no session to resume, so the prompt
is just this message's own body plus Marcelo's command_text when he's the
one initiating/forwarding. There is no more multi-turn thread to walk here
(2026-07-28): the old origin_type=="demand" reply chain this used to
traverse back to its root was retired along with that Tipo value -- an
auto-generated return message never itself gets dispatched, so a dispatch
prompt never has one to walk through.
"""
from app.db.models.demand import AgentDemand


def build_thread_prompt(demand: AgentDemand, command_text: str | None) -> str:
    """The prompt sent to the target agent's CLI: this message's own body,
    plus Marcelo's command_text when he's the one initiating/forwarding."""
    parts = [demand.body]
    if command_text:
        parts.append(f"\nInstruction: {command_text}")
    return "\n".join(parts)
