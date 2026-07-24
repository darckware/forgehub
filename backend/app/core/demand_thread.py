"""Builds the CLI prompt for an Inbox dispatch (api/routes/demand.py's
/dispatch), by walking a demand's origin_type=="demand" chain back to its
root.

Each host-bridge agent-run is a fresh, stateless process (`claude` runs with
`--no-session-persistence`) -- there is no session to resume, so continuing
an existing thread means re-sending enough of the prior exchange as context,
not just the latest message.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.demand import AgentDemand

MAX_THREAD_ITEMS = 20  # sane ceiling -- a runaway back-and-forth shouldn't blow up the prompt


async def _thread_chain(db: AsyncSession, demand: AgentDemand) -> list[AgentDemand]:
    """Root-first list of every demand in this item's origin_type=="demand"
    chain, ending with `demand` itself. Stops at a "task" origin or no
    origin (that's the root)."""
    chain = [demand]
    current = demand
    while current.origin_type == "demand" and current.origin_id is not None:
        if len(chain) >= MAX_THREAD_ITEMS:
            break
        parent = (
            await db.execute(select(AgentDemand).where(AgentDemand.id == current.origin_id))
        ).scalar_one_or_none()
        if parent is None:
            break
        chain.append(parent)
        current = parent
    return list(reversed(chain))


async def build_thread_prompt(db: AsyncSession, demand: AgentDemand, command_text: str | None) -> str:
    """The prompt sent to the target agent's CLI: the demand's own context,
    plus (if this item is part of a longer exchange) the prior turns, plus
    Marcelo's command_text when he's the one initiating/forwarding."""
    chain = await _thread_chain(db, demand)
    if len(chain) == 1:
        parts = [demand.body]
    else:
        parts = ["Conversation so far:\n"]
        for item in chain:
            parts.append(f"— {item.from_agent}: {item.body}")
    if command_text:
        parts.append(f"\nInstruction: {command_text}")
    return "\n".join(parts)
