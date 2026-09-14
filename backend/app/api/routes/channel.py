"""ChatChannel domain routes -- a real-time, shared-context room for the
logged-in human + N Agent members. See db/models/channel.py's module
docstring for the design decisions (member choice is always explicit,
project attachment is mutable, turn_policy="mention_only" only, tasks are
lightweight until promoted).

Deliberate scope note on streaming: unlike chat.py's stream_chat_message
(token-by-token SSE proxy of a single agent), a channel turn can wake
several agents at once, each running concurrently on its own DB session
(see _wake_agent_turn_isolated -- 2026-08-06, Marcelo: "o chat do canal
deve executar vários agentes ao mesmo tempo... veja a execução do chat da
conversations"). GET .../messages/stream here streams one SSE event per
completed message (human echo, then each mentioned agent's full reply as
it finishes, in whatever order that turns out to be) rather than per-token
-- real, functional real-time updates without re-implementing chat.py's
incremental token relay for an N-agent fan-out. Token-level streaming per
agent is a reasonable future enhancement, not required for the room to
function.
"""
import asyncio
import anyio
import contextlib
import json
import logging
import re
import uuid
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.chat import (
    _bridge_headers,
    _call_bridge_text,
    _with_language_note,
)
from app.api.schemas.channel import (
    ChatChannelAttachProject,
    ChatChannelCreate,
    ChatChannelCreateResult,
    ChatChannelDispatchTaskRequest,
    ChatChannelMemberAdd,
    ChatChannelMemberOut,
    ChatChannelMemberUpdate,
    ChatChannelMessageCreate,
    ChatChannelMessageOut,
    ChatChannelOut,
    ChatChannelTaskCreate,
    ChatChannelTaskOut,
    ChatChannelTaskProposeIn,
    ChatChannelTaskUpdate,
    ChatChannelUpdate,
    ChatChannelWithMembersOut,
)
from app.api.schemas.prompt_technique import ImprovePromptRequest
from app.core.prompt_improvement import build_prompt_improvement_request, get_prompt_technique
from app.core import conversions
from app.core import active_turns
from app.core.config import settings
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal, get_current_username
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.agent import Agent
from app.db.models.channel import (
    CHANNEL_TASK_STATUSES,
    ChatChannel,
    ChatChannelMember,
    ChatChannelMessage,
    ChatChannelTask,
)
from app.db.models.governance import Approval
from app.db.models.active_turn import ActiveTurn
from app.db.models.orchestration import PROJECT_AGENT_ROLES, ProjectAgentMembership
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])
logger = logging.getLogger(__name__)

# Safety cap referenced in the plan's risk section -- a message with more
# mentions than this only wakes the first N (in text order); the rest are
# left un-woken rather than silently truncating the message itself.
MAX_MENTIONS_PER_MESSAGE = 5
# How much prior transcript is folded into each woken agent's prompt --
# same "bounded window, not full history" trade-off chat.py's voice mode
# already accepts (chat.py:642-650) generalized to N authors.
CONTEXT_WINDOW_MESSAGES = 30

# Channel turns must outlive the browser request that launched them, just as
# chat turns do. Strong references prevent asyncio from collecting detached
# tasks, while the id map gives the explicit Stop endpoint a precise target.
_LIVE_CHANNEL_TASKS: set[asyncio.Task] = set()
_CHANNEL_TASKS_BY_TURN: dict[uuid.UUID, asyncio.Task] = {}
_CHANNEL_STREAM_IDS_BY_TURN: dict[uuid.UUID, set[str]] = {}
_CHANNEL_AGENT_LOCKS: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Lock] = {}


def _channel_agent_lock(channel_id: uuid.UUID, agent_id: uuid.UUID) -> asyncio.Lock:
    """One linear Hermes context per agent inside one channel."""
    return _CHANNEL_AGENT_LOCKS.setdefault((channel_id, agent_id), asyncio.Lock())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


async def _get_channel_or_404(db: AsyncSession, channel_id: uuid.UUID) -> ChatChannel:
    channel = await db.get(ChatChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def _sync_project_membership_role(
    db: AsyncSession, project_id: uuid.UUID | None, agent_id: uuid.UUID | None, role: str | None
) -> None:
    """Keeps a channel member's function in sync with their formal project
    team role (2026-08-06, Marcelo: "eu acho que é a mesma coisa função no
    canal e projeto" -- after discussing, the two stay separate concepts
    since ProjectAgentMembership also gates real task-assignment
    eligibility elsewhere, but this closes the gap so they don't visibly
    diverge for no reason). Only ever upserts a real role -- never clears
    or deletes a membership (role is NOT NULL on ProjectAgentMembership,
    and clearing someone's channel role shouldn't silently pull them off
    the project's formal team, a more consequential action the human
    should still take explicitly via Project Center). No-op when the
    channel has no project attached, since there's nothing to sync into.
    """
    if project_id is None or agent_id is None or role is None:
        return
    existing = (await db.execute(select(ProjectAgentMembership).where(
        ProjectAgentMembership.project_id == project_id,
        ProjectAgentMembership.agent_id == agent_id,
    ))).scalar_one_or_none()
    if existing is not None:
        existing.role = role
    else:
        db.add(ProjectAgentMembership(project_id=project_id, agent_id=agent_id, role=role))


async def _list_members(db: AsyncSession, channel_id: uuid.UUID) -> list[ChatChannelMember]:
    return list((
        await db.execute(select(ChatChannelMember).where(ChatChannelMember.channel_id == channel_id))
    ).scalars().all())


async def _get_agent_member_or_404(
    db: AsyncSession, channel_id: uuid.UUID, agent_id: uuid.UUID
) -> ChatChannelMember:
    member = (
        await db.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel_id,
                ChatChannelMember.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if member is None or member.muted:
        raise HTTPException(status_code=400, detail="Target agent must be an active member of this channel")
    return member


async def _channel_with_members_out(db: AsyncSession, channel: ChatChannel) -> ChatChannelWithMembersOut:
    # Built from ChatChannelOut's own dump rather than
    # ChatChannelWithMembersOut.model_validate(channel) directly -- the
    # latter eagerly touches the ORM `members` relationship attribute,
    # which async SQLAlchemy can't lazy-load outside an await (raises
    # MissingGreenlet). Members are fetched explicitly instead.
    members = await _list_members(db, channel.id)
    base = ChatChannelOut.model_validate(channel).model_dump()
    return ChatChannelWithMembersOut(**base, members=[ChatChannelMemberOut.model_validate(m) for m in members])


def _mentions_everyone(text: str) -> bool:
    """"#all" (case-insensitive, same word-boundary rule as an agent name)
    -- a deliberate broadcast, not something a real agent could ever be
    named (2026-08-06, Marcelo: "como enviar a mensagem para todos os
    agentes, quando envio o comando sem informar o agente não [funciona]").
    Checked separately from _extract_mentions below so callers can also
    decide to skip MAX_MENTIONS_PER_MESSAGE for an explicit broadcast."""
    for match in re.finditer("#", text):
        rest_lower = text[match.end():].lower()
        if not rest_lower.startswith("all"):
            continue
        next_char = rest_lower[3:4]
        if next_char == "" or re.match(r"[\s.,!?;:]", next_char):
            return True
    return False


def _extract_mentions(text: str, candidates: list[Agent]) -> list[Agent]:
    """Same algorithm as ChatPane.tsx's extractMentionedAgents (longest-name-
    first match on a "#" prefix, word-boundary aware), ported server-side so
    the wake logic never trusts the client's own parsing alone. "#all"
    mentions every current agent member -- see _mentions_everyone."""
    if _mentions_everyone(text):
        return list(candidates)
    by_length = sorted(candidates, key=lambda a: len(a.name), reverse=True)
    found: list[Agent] = []
    for match in re.finditer("#", text):
        rest = text[match.end():]
        rest_lower = rest.lower()
        for agent in by_length:
            name_lower = agent.name.lower()
            if not rest_lower.startswith(name_lower):
                continue
            next_char = rest[len(agent.name):len(agent.name) + 1]
            if next_char == "" or re.match(r"[\s.,!?;:]", next_char):
                found.append(agent)
                break
    seen: dict[uuid.UUID, Agent] = {}
    for agent in found:
        seen.setdefault(agent.id, agent)
    return list(seen.values())


def _resolve_mentions(content: str, agents: list[Agent]) -> list[Agent]:
    """Which agent-members actually wake for this turn. "#all" is an
    explicit broadcast (see _mentions_everyone); as of 2026-08-06 (Marcelo:
    "quando não especificar o agente a mensagem é para todos e #all seja
    opcional"), a message that names no agent at all -- no #Name match, no
    #all -- broadcasts the same way, since requiring "#all" just to reach
    everyone was the actual complaint. Only an explicit #Name (or several)
    narrows the turn to those specific agents, capped at
    MAX_MENTIONS_PER_MESSAGE; neither broadcast form is ever truncated."""
    mentioned = _extract_mentions(content, agents)
    if not mentioned:
        return list(agents)
    if _mentions_everyone(content):
        return mentioned
    return mentioned[:MAX_MENTIONS_PER_MESSAGE]


async def _build_shared_context(db: AsyncSession, channel: ChatChannel) -> str:
    """The concrete mechanism behind "real shared context" (see
    db/models/channel.py's module docstring): every hermes_stream.py call
    is still one isolated subprocess per agent per turn, so instead of
    relying on any single agent's own resumed session, the last N
    messages -- from every author -- are formatted and reinjected into the
    prompt on every wake."""
    rows = list((
        await db.execute(
            select(ChatChannelMessage)
            .where(ChatChannelMessage.channel_id == channel.id)
            .order_by(ChatChannelMessage.created_at.desc())
            .limit(CONTEXT_WINDOW_MESSAGES)
        )
    ).scalars().all())
    rows.reverse()
    # Was a generator expression with `await` inside `", ".join(...)` --
    # that's an async-generator expression (PEP 530), which str.join()
    # can't consume ("can only join an iterable"). Every single call ever
    # raised here, always before reaching the bridge -- invisible until
    # 2026-08-06's broadened exception handling in stream_channel_message
    # actually surfaced it instead of silently killing the SSE connection
    # (the root cause of "enviei a mensagem e não foi feito nada").
    names: list[str] = []
    for m in await _list_members(db, channel.id):
        if m.agent_id is None:
            names.append("Marcelo")
            continue
        member_agent = await db.get(Agent, m.agent_id)
        if member_agent is not None:
            names.append(member_agent.name)
    member_names = ", ".join(names)
    # Hidden tone instruction, every turn (not just onboarding) -- 2026-08-06,
    # Marcelo: "mande uma instrução oculta para os agentes participante
    # para soar de forma natural a interação". Kept separate from
    # _onboarding_note (which explains the mechanics once); this is about
    # *how* to sound, said on every wake so the tone doesn't only hold for
    # the first turn.
    lines = [
        f'Você está no canal "#{channel.name}". Membros: {member_names}.',
        (
            "[Roteamento interno ForgeHub] Ao delegar com send_agent_message, "
            f"use channel='workspace' e channel_ref='{channel.id}' para o resultado voltar a este canal."
        ),
        "[Instrução interna, não visível aos demais membros] Responda de forma natural e "
        "conversacional, como um colega de equipe participando de uma discussão em grupo -- "
        "direto e humano, sem tom de relatório formal nem recapitular tudo que já foi dito.",
        "",
    ]
    for row in rows:
        author = row.author_label or {"human": "Marcelo", "system": "Sistema"}.get(row.author_type, "Agente")
        lines.append(f"{author}: {row.content}")
    return "\n".join(lines)


async def _onboarding_note(db: AsyncSession, channel: ChatChannel, member: ChatChannelMember) -> str:
    """Prepended once, only on an agent-member's very first real turn in
    this channel (member.hermes_session_id still None -- see
    _wake_agent_turn), so the agent learns how the room works before it
    ever has to guess (2026-08-06, Marcelo: "cada agente quando iniciar no
    grupo precisa receber uma mensagem informando que ele está dentro do
    contexto de um grupo de trabalho... para ele poder saber como
    interagir no ambiente" -- the concrete gap this closes is the same one
    Athos hit, asking for a message-based command that doesn't exist).
    Condensed from help/FORGEHUB_CHANNELS_AGENT_GUIDE.md -- keep
    the two in sync if this changes."""
    role_line = (
        f'Sua função neste canal é "{member.role}".'
        if member.role
        else "Você ainda não tem uma função definida neste canal."
    )
    # Project-level role is a separate, formal thing from the channel role
    # above (see _sync_project_membership_role's docstring) -- surfaced
    # here too so the agent understands its actual responsibility on the
    # underlying project, not just its label in this room (2026-08-06,
    # Marcelo: "cada agente precisa entender a sua função em cada projeto
    # dentro do canal").
    project_role_line = ""
    if channel.project_id is not None and member.agent_id is not None:
        membership = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == channel.project_id,
            ProjectAgentMembership.agent_id == member.agent_id,
        ))).scalar_one_or_none()
        project_role_line = (
            f' No projeto formal ligado a este canal, sua função é "{membership.role}".'
            if membership is not None
            else " Você ainda não é membro formal do time do projeto ligado a este canal."
        )
    return (
        f'[Contexto interno, não visível a Marcelo nem aos demais membros] Você acabou de entrar '
        f'no canal "#{channel.name}" do ForgeHub -- uma sala compartilhada (Marcelo + agentes), '
        f'diferente do Messages/Inbox ponto-a-ponto. {role_line}{project_role_line} Você só gera '
        f'uma resposta real quando alguém escreve #SeuNome na mensagem, escreve #all, ou não '
        f'menciona nenhum agente (mensagem vai para todo o canal) -- turn_policy=mention_only, '
        f'nunca reaja a mensagens de outros agentes por conta própria. Ferramentas MCP '
        f'disponíveis (servidor forgehub-messages): list_channel_members (quem está aqui e a '
        f'função de cada um), propose_channel_task (propor tarefa para você mesmo -- livre dentro '
        f'da sua função -- ou para um colega -- sempre cria uma Approval pendente em Governança), '
        f'list_agent_skills (conferir skills antes de propor/aceitar uma tarefa). Não existe '
        f'comando de mensagem para adicionar/remover membro, mudar função de outro membro ou '
        f'decidir uma aprovação -- essas ações exigem autoridade delegada por Marcelo via '
        f'Governança > Delegações de Autoridade, mesmo para o orquestrador do canal. Este canal '
        f'faz parte do módulo Software Factory do ForgeHub (Product -> Project -> Planejamento -> '
        f'Task, com Cockpit, Pipeline e Governança) -- se precisar entender o pipeline completo '
        f'além do canal em si, consulte help/MANUAL.md (seção Software Factory). Guia do '
        f'canal em si: help/FORGEHUB_CHANNELS_AGENT_GUIDE.md. Antes de responder à '
        f'mensagem real abaixo, cumprimente brevemente e de forma natural os demais membros do '
        f'canal, apresentando-se e sua função em uma frase -- depois continue normalmente.\n\n'
    )


# --------------------------------------------------------------------------
# CRUD + membership + project attachment
# --------------------------------------------------------------------------


@router.post("", response_model=ChatChannelCreateResult, status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChatChannelCreate,
    db: AsyncSession = Depends(get_db),
    current_username: str = Depends(get_current_username),
) -> ChatChannelCreateResult:
    if payload.project_id is not None:
        await _get_project_or_404(db, payload.project_id)
    if payload.orchestrator_agent_id is not None and payload.orchestrator_agent_id not in payload.member_agent_ids:
        raise HTTPException(
            status_code=400, detail="orchestrator_agent_id must be one of member_agent_ids"
        )

    channel = ChatChannel(
        name=payload.name.strip(),
        description=payload.description,
        project_id=payload.project_id,
        working_directory_path=payload.working_directory_path,
        created_by=current_username,
        orchestrator_agent_id=payload.orchestrator_agent_id,
    )
    db.add(channel)
    await db.flush()

    db.add(ChatChannelMember(channel_id=channel.id, is_human=True))
    seen: set[uuid.UUID] = set()
    member_roles = payload.member_roles or {}
    for agent_id in payload.member_agent_ids:
        if agent_id in seen:
            continue
        seen.add(agent_id)
        member_agent = await _get_agent_or_404(db, agent_id)
        # Pre-filled from the registered specialty unless the human
        # overrode it in the creation form -- see ChatChannelMemberAdd.role
        # and ChatChannelCreate.member_roles' docstrings.
        role_override = member_roles.get(str(agent_id))
        if role_override is not None and role_override not in PROJECT_AGENT_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {PROJECT_AGENT_ROLES}")
        db.add(ChatChannelMember(
            channel_id=channel.id, agent_id=agent_id, role=role_override or member_agent.default_role
        ))
        # Only sync an explicit choice, never a silent default_role prefill
        # -- see _sync_project_membership_role's docstring.
        await _sync_project_membership_role(db, payload.project_id, agent_id, role_override)

    suggested: list[ProjectAgentMembership] = []
    if payload.project_id is not None:
        suggested = list((
            await db.execute(
                select(ProjectAgentMembership).where(
                    ProjectAgentMembership.project_id == payload.project_id,
                    ProjectAgentMembership.status == "active",
                )
            )
        ).scalars().all())

    await db.commit()
    await db.refresh(channel)
    channel_out = await _channel_with_members_out(db, channel)
    return ChatChannelCreateResult(channel=channel_out, suggested_project_members=suggested)


@router.get("", response_model=list[ChatChannelOut])
async def list_channels(
    project_id: uuid.UUID | None = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[ChatChannel]:
    stmt = select(ChatChannel)
    if project_id is not None:
        stmt = stmt.where(ChatChannel.project_id == project_id)
    if not include_archived:
        stmt = stmt.where(ChatChannel.archived.is_(False))
    result = await db.execute(stmt.order_by(ChatChannel.updated_at.desc()))
    return list(result.scalars().all())


@router.get("/{channel_id}/active-turn")
async def get_channel_active_turn(
    channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """"Há algo rodando neste canal, e o que já aconteceu?"

    Mesma pergunta que o chat responde em /chat/sessions/{id}/active-turn, e
    a mesma resposta -- ver core/active_turns.py, o helper que serve as duas
    superfícies (2026-08-13).

    A diferença do canal aparece no conteúdo, não no formato: vários agentes
    podem estar rodando no mesmo turno, então cada passo diz de quem é e o
    texto vem também separado por agente (`live_text_by_agent`). Uma trilha
    plana misturaria o trabalho de dois agentes sem dono, e um texto único
    intercalaria as frases deles.
    """
    await _get_channel_or_404(db, channel_id)
    turn = await active_turns.get_active(db, scope="channel", scope_id=channel_id)
    if turn is None:
        return {"turn": None}
    await active_turns.mark_reattached(db, turn.id)
    await db.commit()
    return {
        "turn": {
            "id": str(turn.id),
            "stream_id": turn.stream_id,
            "prompt": turn.prompt,
            "agent_id": str(turn.agent_id) if turn.agent_id else None,
            "steps": turn.steps or [],
            "live_text": turn.live_text or "",
            "live_text_by_agent": turn.live_text_by_agent or {},
            "pending_approval": turn.pending_approval,
            "started_at": turn.created_at.isoformat(),
            "deadline_at": turn.deadline_at.isoformat() if turn.deadline_at else None,
        }
    }


@router.get("/{channel_id}", response_model=ChatChannelWithMembersOut)
async def get_channel(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChatChannelWithMembersOut:
    channel = await _get_channel_or_404(db, channel_id)
    return await _channel_with_members_out(db, channel)


@router.patch("/{channel_id}", response_model=ChatChannelOut)
async def update_channel(
    channel_id: uuid.UUID,
    payload: ChatChannelUpdate,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> ChatChannel:
    """Renames/archives the channel or (re)designates its orchestrator --
    same governed-authority gate as the member routes (2026-08-06,
    Marcelo: "adicione o icone de editar e excluir o canal" -- this route
    had no authorization dependency at all before, the same gap already
    fixed for add/remove/role.assign member routes on 2026-08-05)."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.manage", project_id=channel.project_id)
    if payload.name is not None:
        channel.name = payload.name.strip()
    if payload.description is not None:
        channel.description = payload.description
    if payload.archived is not None:
        channel.archived = payload.archived
    if payload.orchestrator_agent_id is not None:
        is_member = (await db.execute(select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.agent_id == payload.orchestrator_agent_id,
        ))).scalar_one_or_none()
        if is_member is None:
            raise HTTPException(
                status_code=400, detail="orchestrator_agent_id must be a current agent member of this channel"
            )
        channel.orchestrator_agent_id = payload.orchestrator_agent_id
    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> None:
    """Same "channel.manage" gate as update_channel -- deleting a channel
    is consequential enough (its whole transcript and tasks go with it)
    that it should never have been reachable with no authorization check
    at all."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.manage", project_id=channel.project_id)
    await db.delete(channel)
    await db.commit()


@router.delete("/{channel_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_channel_messages(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> None:
    """Wipes the transcript without deleting the channel itself or its
    membership/tasks (2026-08-06, Marcelo: "adicione um icone de limpeza do
    chat" -- the trash icon next to the channel name already deletes the
    whole channel; this is the lighter "start this room over" action, same
    "channel.manage" gate as update_channel/delete_channel). Also resets
    every member's hermes_session_id: leaving it set would clear the
    visible transcript while every agent's own bridge session still
    remembers the old conversation, and it re-arms _onboarding_note for
    each member's next turn -- the same "fresh start" a brand-new channel
    gets."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.manage", project_id=channel.project_id)
    await db.execute(delete(ChatChannelMessage).where(ChatChannelMessage.channel_id == channel_id))
    await db.execute(
        update(ChatChannelMember)
        .where(ChatChannelMember.channel_id == channel_id)
        .values(hermes_session_id=None)
    )
    await db.commit()


@router.post("/{channel_id}/project", response_model=ChatChannelOut)
async def attach_channel_project(
    channel_id: uuid.UUID, payload: ChatChannelAttachProject, db: AsyncSession = Depends(get_db)
) -> ChatChannel:
    """Attaches/switches the channel's Project at any point in the
    conversation -- the "add a project like an MCP" action (see
    db/models/channel.py's module docstring). Never touches membership."""
    channel = await _get_channel_or_404(db, channel_id)
    await _get_project_or_404(db, payload.project_id)
    channel.project_id = payload.project_id
    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/{channel_id}/project", response_model=ChatChannelOut)
async def detach_channel_project(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChatChannel:
    channel = await _get_channel_or_404(db, channel_id)
    channel.project_id = None
    await db.commit()
    await db.refresh(channel)
    return channel


@router.post("/{channel_id}/members", response_model=ChatChannelMemberOut, status_code=status.HTTP_201_CREATED)
async def add_channel_member(
    channel_id: uuid.UUID,
    payload: ChatChannelMemberAdd,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> ChatChannelMember:
    """Adds an agent not yet in this channel -- Marcelo (admin) always
    passes; an agent principal needs an active AuthorityDelegation granting
    "channel.member.manage" (optionally scoped to this channel's
    project_id), same governed-authority mechanism as
    "channel.member.role.assign" (2026-08-05, Marcelo: "o orquestrador pode
    adicionar agentes que não foram colocados no canal"). Distinct action
    key from role.assign -- deciding *who is in the room* is a different
    trust boundary than adjusting an existing member's function."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.member.manage", project_id=channel.project_id)
    agent = await _get_agent_or_404(db, payload.agent_id)
    existing = (
        await db.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel_id, ChatChannelMember.agent_id == payload.agent_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Agent is already a member of this channel")
    # Pre-filled from the agent's registered specialty when not given
    # explicitly -- see ChatChannelMemberAdd.role and Agent.default_role's
    # docstrings. Still just a starting point, editable afterwards.
    member = ChatChannelMember(
        channel_id=channel_id, agent_id=payload.agent_id, role=payload.role or agent.default_role
    )
    db.add(member)
    # Only sync an explicit choice, never a silent default_role prefill --
    # see _sync_project_membership_role's docstring.
    await _sync_project_membership_role(db, channel.project_id, payload.agent_id, payload.role)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch("/{channel_id}/members/{member_id}", response_model=ChatChannelMemberOut)
async def update_channel_member(
    channel_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: ChatChannelMemberUpdate,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> ChatChannelMember:
    """Sets/edits a member's function *in this channel* (see
    db/models/channel.py's ChatChannelMember.role docstring and
    docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md). Marcelo
    (admin) always passes; an agent principal needs an active
    AuthorityDelegation granting "channel.member.role.assign" (optionally
    scoped to this channel's project_id), the same governed-authority
    mechanism "governance.approval.decide" already uses for a delegated
    orchestrator (e.g. Athos) -- not a channel-specific permission flag.
    2026-08-05: this route previously had no authorization dependency at
    all, so any caller who could reach it (any valid JWT *or* any agt_
    credential, since the middleware only checks the credential is
    unrevoked) could already edit any channel's member roles despite the
    "Marcelo-only" docstring claiming otherwise -- fixed here, not just
    documented."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.member.role.assign", project_id=channel.project_id)
    member = await db.get(ChatChannelMember, member_id)
    if member is None or member.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel member not found")
    if payload.role is not None:
        if payload.role not in PROJECT_AGENT_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {PROJECT_AGENT_ROLES}")
        member.role = payload.role
        # Auto-sync into the formal project team role (2026-08-06, Marcelo:
        # "eu acho que é a mesma coisa função no canal e projeto") -- see
        # _sync_project_membership_role's docstring for why this stays an
        # upsert-only sync rather than a merge of the two concepts.
        await _sync_project_membership_role(db, channel.project_id, member.agent_id, payload.role)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{channel_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_member(
    channel_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> None:
    """Same "channel.member.manage" gate as add_channel_member -- see its
    docstring. Removing was the other half of this route pair with no
    authorization dependency at all before 2026-08-05."""
    channel = await _get_channel_or_404(db, channel_id)
    await authorize_action(db, principal, "channel.member.manage", project_id=channel.project_id)
    member = await db.get(ChatChannelMember, member_id)
    if member is None or member.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel member not found")
    if member.is_human:
        raise HTTPException(status_code=400, detail="Cannot remove the human member of a channel")
    await db.delete(member)
    await db.commit()


# --------------------------------------------------------------------------
# Messages -- shared transcript, mention-driven turns
# --------------------------------------------------------------------------


async def _post_human_message(db: AsyncSession, channel: ChatChannel, content: str, attachment_names: str | None) -> ChatChannelMessage:
    message = ChatChannelMessage(
        channel_id=channel.id,
        author_type="human",
        author_label=channel.created_by or "Marcelo",
        content=content,
        attachment_names=attachment_names,
    )
    db.add(message)
    await db.flush()
    return message


async def _build_agent_turn_context(db: AsyncSession, channel: ChatChannel, member: ChatChannelMember) -> str:
    """The full prompt sent to the bridge for one member's turn -- the
    shared-transcript context, the onboarding note prepended exactly once
    (member.hermes_session_id still None; set right after the bridge call
    and never cleared afterwards, so a later turn never repeats it), and
    the response-language note. Shared by both the blocking
    (_wake_agent_turn) and streaming (_wake_agent_turn_streaming) bridge
    call paths so the two prompts can't drift apart."""
    context = await _build_shared_context(db, channel)
    if member.hermes_session_id is None:
        context = await _onboarding_note(db, channel, member) + context
    return _with_language_note(context)


def _new_agent_reply(channel: ChatChannel, agent: Agent, content: str) -> ChatChannelMessage:
    """A new, unflushed ChatChannelMessage for one agent's reply -- the
    caller still owns add/flush-or-commit on whichever session it's
    building this turn on."""
    return ChatChannelMessage(
        channel_id=channel.id,
        author_type="agent",
        author_agent_id=agent.id,
        author_label=agent.name,
        content=content,
    )


async def _wake_agent_turn(
    db: AsyncSession, channel: ChatChannel, member: ChatChannelMember, agent: Agent
) -> ChatChannelMessage:
    """One agent-member's real turn via the blocking, non-streaming bridge
    call (/v1/chat, same call chat.py's non-streaming path uses) -- used by
    the plain POST /messages route. The SSE route
    (stream_channel_message) uses _wake_agent_turn_streaming instead,
    which additionally relays tool_start/tool_complete steps live as they
    happen -- see its own docstring."""
    context = await _build_agent_turn_context(db, channel, member)
    bridge_result = await _call_bridge_text(agent.profile_slug, context, member.hermes_session_id)
    member.hermes_session_id = bridge_result.get("session_id") or member.hermes_session_id
    reply = _new_agent_reply(channel, agent, bridge_result["reply"])
    db.add(reply)
    await db.flush()
    return reply


async def _wake_agent_turn_isolated(
    channel_id: uuid.UUID, member_id: uuid.UUID, agent_id: uuid.UUID
) -> ChatChannelMessageOut:
    """Runs one mentioned agent's turn end-to-end on its own AsyncSession so
    several mentioned/broadcast agents can be woken concurrently instead of
    one after another (2026-08-06, Marcelo: "o chat do canal deve executar
    vários agentes ao mesmo tempo... veja a execução do chat da
    conversations" -- each Workspace/Conversas tab already fires its own
    independent request; the same "independent, concurrent request per
    target" idea applies here across agents within one channel turn instead
    of across tabs). A single AsyncSession isn't safe to drive from several
    concurrent coroutines (SQLAlchemy's async session assumes one logical
    transaction in flight at a time), so this opens its own, re-fetches the
    channel/member/agent fresh in it, and commits its own reply + updated
    hermes_session_id independently -- a slow agent no longer blocks a
    faster one, and one agent's bridge failure can't corrupt another's
    already-persisted turn."""
    async with _channel_agent_lock(channel_id, agent_id):
        async with AsyncSessionLocal() as db:
            channel = await db.get(ChatChannel, channel_id)
            member = await db.get(ChatChannelMember, member_id)
            agent = await db.get(Agent, agent_id)
            reply = await _wake_agent_turn(db, channel, member, agent)
            await db.commit()
            await db.refresh(reply)
            return ChatChannelMessageOut.model_validate(reply)


async def _iter_bridge_stream(bridge_params: dict[str, str]) -> AsyncIterator[dict]:
    """Yields each parsed JSON payload from the host-bridge's token/tool-
    event SSE stream (/v1/chat/stream -- the same endpoint chat.py's
    stream_chat_message proxies for 1:1 sessions). SSE comment lines (the
    bridge's own keepalive pings) are silently skipped. Raises
    HTTPException(502) on a non-200 response or an explicit {"error": ...}
    payload, same convention as _call_bridge_text. Factored out on its own
    so tests can monkeypatch this one async generator instead of stubbing
    httpx's streaming client directly."""
    async with httpx.AsyncClient(timeout=660.0) as client:
        async with client.stream(
            "GET",
            f"{settings.CHAT_BRIDGE_URL}/v1/chat/stream",
            params=bridge_params,
            headers=_bridge_headers(),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Chat bridge error: {body.decode()[:500]}",
                )
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("error"):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Chat bridge error: {data['error']}",
                    )
                yield data


async def _wake_agent_turn_streaming(
    channel_id: uuid.UUID,
    member_id: uuid.UUID,
    agent_id: uuid.UUID,
    events: asyncio.Queue,
) -> None:
    """Same job as _wake_agent_turn_isolated for one mentioned agent, but
    consumes the host-bridge's token/tool-event SSE stream via
    _iter_bridge_stream instead of the blocking /v1/chat call, so
    tool_start/tool_complete steps can be relayed to the channel's own SSE
    stream live as they happen (2026-08-06, Marcelo: "traz o passo a passo
    de ferramentas em tempo real também"). Token deltas are read but never
    forwarded -- the channel stays message-level streaming by design (see
    module docstring); only the tool trail is live. Runs on its own
    isolated DB session, same reasoning as _wake_agent_turn_isolated.

    Never raises past this function (both the ordinary-failure and
    cancellation branches below catch, persist, and stop) -- exactly one
    terminal event (`("done", ...)` or `("failed", ...)`) reaches `events`
    per agent when its turn ends, so the caller can track how many turns
    are still outstanding by counting terminal tuples instead of polling
    task objects. But `events` is an in-memory queue with no guarantee
    anyone is still reading it -- this task is scheduled independently of
    the SSE connection that requested it (`asyncio.ensure_future` in
    stream_channel_message, the whole point of concurrent per-agent
    turns), so the browser may have long navigated away by the time a slow
    agent finishes. Every terminal outcome (success, ordinary failure, or
    a cancelled/dropped connection) is therefore also durably written to
    the channel's transcript, same discipline chat.py's stream_chat_message
    already applies to 1:1 sessions -- a turn must never vanish with zero
    trace just because nobody was watching live (2026-08-07, Marcelo: "ao
    sair da tela perdi o processamento da conversão com o agente. precisa
    se manter igual ao chat da conversation" -- confirmed via
    chat_channel_messages: the human message existed, but zero agent reply
    and zero error row for "#Athos, preciso que você crie um usuário...").
    """
    steps_run: list[str] = []
    accumulated: list[str] = []

    def _interrupted_turn_content() -> str:
        """Same idea as chat.py's own _interrupted_turn_content: the tool
        steps the turn ran before it was cut off count as real,
        user-visible processing activity -- persist them instead of
        letting them evaporate with the connection."""
        if not steps_run:
            warning = "⚠️ Turno interrompido antes de concluir (nenhuma etapa registrada)."
        else:
            unique_steps = list(dict.fromkeys(steps_run))
            warning = "⚠️ Turno interrompido antes de concluir. Etapas executadas:\n" + "\n".join(
                f"- {s}" for s in unique_steps
            )
        partial = "".join(accumulated).strip()
        return f"{warning}\n\n{partial}" if partial else warning

    lane_lock = _channel_agent_lock(channel_id, agent_id)
    async with AsyncSessionLocal() as db:
        channel = await db.get(ChatChannel, channel_id)
        member = await db.get(ChatChannelMember, member_id)
        agent = await db.get(Agent, agent_id)
        await lane_lock.acquire()
        try:
            # Another message to this agent may have completed while this
            # worker waited. Reload the continuation id it just wrote before
            # opening the next bridge stream.
            await db.refresh(member)
            context = await _build_agent_turn_context(db, channel, member)
            bridge_params: dict[str, str] = {"profile": agent.profile_slug, "message": context}
            if agent.runtime_type and agent.runtime_type != "hermes":
                bridge_params["runtime"] = agent.runtime_type
            if member.hermes_session_id:
                bridge_params["session_id"] = member.hermes_session_id
            full_reply = ""
            new_hermes_session_id: str | None = None
            async for data in _iter_bridge_stream(bridge_params):
                if data.get("stream_id"):
                    await events.put(("stream_id", agent.id, str(data["stream_id"])))
                tool_start = data.get("tool_start")
                if isinstance(tool_start, dict):
                    step = tool_start.get("context") or tool_start.get("name")
                    if step:
                        steps_run.append(str(step))
                    await events.put((
                        "step",
                        agent.id,
                        agent.name,
                        {
                            "tool_id": tool_start.get("tool_id"),
                            "name": tool_start.get("name"),
                            "context": tool_start.get("context"),
                            "detail": tool_start.get("detail"),
                            "done": False,
                        },
                    ))
                tool_complete = data.get("tool_complete")
                if isinstance(tool_complete, dict):
                    await events.put((
                        "step",
                        agent.id,
                        agent.name,
                        {
                            "tool_id": tool_complete.get("tool_id"),
                            "name": tool_complete.get("name"),
                            "summary": tool_complete.get("summary"),
                            "demand_number": tool_complete.get("demand_number"),
                            "done": True,
                        },
                    ))
                delta = data.get("delta", "")
                if delta:
                    accumulated.append(delta)
                    await events.put(("text", agent.id, delta))
                if data.get("done"):
                    full_reply = data.get("reply") or "".join(accumulated) or full_reply
                    new_hermes_session_id = data.get("session_id")
                    break
            member.hermes_session_id = new_hermes_session_id or member.hermes_session_id
            reply = _new_agent_reply(channel, agent, full_reply)
            db.add(reply)
            await db.commit()
            await db.refresh(reply)
            await events.put(("done", agent.id, ChatChannelMessageOut.model_validate(reply)))
        except asyncio.CancelledError:
            # The SSE connection that requested this turn dropped (client
            # navigated away, tab closed) -- cancellation reaches this task
            # too (it's spawned from within that request's own cancel
            # scope), and an unshielded `await db.commit()` here would
            # itself get cut off mid-flight and save nothing, same failure
            # mode chat.py's own proxy_stream already documents fixing.
            # shield=True is required to let this specific write finish.
            with anyio.CancelScope(shield=True):
                try:
                    failure_reply = _new_agent_reply(channel, agent, _interrupted_turn_content())
                    db.add(failure_reply)
                    await db.commit()
                except Exception:
                    await db.rollback()
            raise
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            try:
                failure_reply = _new_agent_reply(
                    channel, agent, f"⚠️ {detail}" if detail else "⚠️ (falha desconhecida ao processar o turno)"
                )
                db.add(failure_reply)
                await db.commit()
            except Exception:
                # Persisting the failure message itself failed (e.g. the DB
                # session is unusable after the original error) -- don't
                # let that mask the real failure below.
                await db.rollback()
            await events.put(("failed", agent.id, agent.name, str(detail)))
        finally:
            lane_lock.release()


async def _process_channel_turn(
    db: AsyncSession, channel: ChatChannel, content: str, attachment_names: str | None
) -> list[ChatChannelMessageOut]:
    """turn_policy="mention_only" enforced here: #-mentioned members
    (capped at MAX_MENTIONS_PER_MESSAGE) get a real turn -- concurrently,
    each on its own isolated session (see _wake_agent_turn_isolated), never
    triggered by another agent's own reply (no re-scan of agent-authored
    content for mentions in this call chain -- see module docstring on why
    autonomous agent-to-agent turns aren't implemented yet). An explicit
    "#all", or a message that names no agent at all, wakes every member
    instead and is never truncated -- see _resolve_mentions. The human
    message is committed immediately (not held for one all-or-nothing
    commit at the end) so the concurrent isolated sessions -- separate DB
    transactions -- can actually see it when they build their shared
    context; a consequence is that a later agent-turn failure no longer
    rolls back the human echo or any sibling agent's already-persisted
    reply, matching stream_channel_message's existing partial-persistence
    behavior below."""
    human_message = await _post_human_message(db, channel, content, attachment_names)
    await db.commit()
    await db.refresh(human_message)
    produced: list[ChatChannelMessageOut] = [ChatChannelMessageOut.model_validate(human_message)]

    members = await _list_members(db, channel.id)
    agent_members = {m.agent_id: m for m in members if not m.is_human and not m.muted}
    if not agent_members:
        return produced
    agents = [await db.get(Agent, agent_id) for agent_id in agent_members]
    agents = [a for a in agents if a is not None]

    mentioned = _resolve_mentions(content, agents)
    if mentioned:
        results = await asyncio.gather(
            *[
                _wake_agent_turn_isolated(channel.id, agent_members[agent.id].id, agent.id)
                for agent in mentioned
            ],
            return_exceptions=True,
        )
        failure = next((r for r in results if isinstance(r, BaseException)), None)
        produced.extend(r for r in results if not isinstance(r, BaseException))
        if failure is not None:
            raise failure
    return produced


@router.post("/{channel_id}/messages", response_model=list[ChatChannelMessageOut])
async def post_channel_message(
    channel_id: uuid.UUID, payload: ChatChannelMessageCreate, db: AsyncSession = Depends(get_db)
) -> list[ChatChannelMessageOut]:
    channel = await _get_channel_or_404(db, channel_id)
    try:
        return await _process_channel_turn(db, channel, payload.content, payload.attachment_names)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Chat bridge error: {exc}") from exc


@router.get("/{channel_id}/messages", response_model=list[ChatChannelMessageOut])
async def list_channel_messages(
    channel_id: uuid.UUID, limit: int = 200, db: AsyncSession = Depends(get_db)
) -> list[ChatChannelMessage]:
    await _get_channel_or_404(db, channel_id)
    result = await db.execute(
        select(ChatChannelMessage)
        .where(ChatChannelMessage.channel_id == channel_id)
        .order_by(ChatChannelMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _run_channel_turn(
    *,
    channel_id: uuid.UUID,
    turn_id: uuid.UUID,
    agents: list[tuple[uuid.UUID, uuid.UUID, str]],
    out_queue: "asyncio.Queue[str | None]",
) -> None:
    """Runs every agent in one channel turn independently of its SSE client.

    ``agents`` contains (agent_id, member_id, display_name). The workers keep
    their existing isolated DB sessions for reply persistence; this
    coordinator owns the ActiveTurn row and the live client tap. Consequently
    a browser disconnect only abandons ``out_queue`` -- it cannot cancel the
    work, its database writes, or the underlying bridge processes.
    """
    events: asyncio.Queue = asyncio.Queue()
    workers: list[asyncio.Task] = []
    failures: list[str] = []
    try:
        for agent_id, _member_id, agent_name in agents:
            await out_queue.put(
                "event: agent_started\ndata: "
                f"{json.dumps({'agent_id': str(agent_id), 'agent_name': agent_name})}\n\n"
            )
        workers = [
            asyncio.create_task(_wake_agent_turn_streaming(channel_id, member_id, agent_id, events))
            for agent_id, member_id, _agent_name in agents
        ]
        remaining = len(workers)
        async with AsyncSessionLocal() as db:
            while remaining > 0:
                try:
                    item = await asyncio.wait_for(events.get(), timeout=15)
                except asyncio.TimeoutError:
                    await out_queue.put(": ping\n\n")
                    continue
                kind = item[0]
                if kind == "stream_id":
                    _, _agent_id, stream_id = item
                    _CHANNEL_STREAM_IDS_BY_TURN.setdefault(turn_id, set()).add(stream_id)
                elif kind == "text":
                    _, agent_id, delta = item
                    await active_turns.record_text(db, turn_id, delta, agent_id=agent_id)
                    await db.commit()
                elif kind == "step":
                    _, agent_id, agent_name, step = item
                    step_id = step.get("tool_id") or str(uuid.uuid4())
                    if step.get("done"):
                        await active_turns.update_step(
                            db,
                            turn_id,
                            step_id,
                            {"status": "done", "label": step.get("summary") or step.get("name")},
                        )
                    else:
                        await active_turns.record_step(
                            db,
                            turn_id,
                            {
                                "id": step_id,
                                "name": step.get("name"),
                                "label": step.get("context") or step.get("name"),
                                "status": "running",
                            },
                            agent_id=agent_id,
                        )
                    await db.commit()
                    await out_queue.put(
                        "event: agent_step\ndata: "
                        f"{json.dumps({'agent_id': str(agent_id), 'agent_name': agent_name, **step})}\n\n"
                    )
                elif kind == "done":
                    _, _agent_id, reply_out = item
                    remaining -= 1
                    await out_queue.put(
                        f"data: {json.dumps(reply_out.model_dump(mode='json'))}\n\n"
                    )
                else:  # failed
                    _, _agent_id, agent_name, detail = item
                    remaining -= 1
                    failures.append(f"{agent_name}: {detail}")

            await asyncio.gather(*workers, return_exceptions=True)
            await active_turns.close_turn(
                db,
                turn_id,
                status="failed" if failures else "completed",
                error="; ".join(failures)[:2000] if failures else None,
            )
            await db.commit()
        if failures:
            await out_queue.put(
                f"event: error\ndata: {json.dumps({'detail': '; '.join(failures)})}\n\n"
            )
        await out_queue.put("event: done\ndata: {}\n\n")
    except asyncio.CancelledError:
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        with anyio.CancelScope(shield=True):
            async with AsyncSessionLocal() as db:
                await active_turns.close_turn(db, turn_id, status="cancelled")
                await db.commit()
        raise
    except Exception as exc:
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        async with AsyncSessionLocal() as db:
            await active_turns.close_turn(db, turn_id, status="failed", error=str(detail)[:2000])
            await db.commit()
        await out_queue.put(f"event: error\ndata: {json.dumps({'detail': str(detail)})}\n\n")
    finally:
        await out_queue.put(None)


@router.post("/{channel_id}/turns/{turn_id}/stop")
async def stop_channel_turn(
    channel_id: uuid.UUID, turn_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Stops a channel turn deliberately; navigation never calls this."""
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.scope != "channel" or turn.scope_id != channel_id:
        raise HTTPException(status_code=404, detail="No such turn")
    if turn.status != "running":
        return {"status": turn.status}

    stream_ids = tuple(_CHANNEL_STREAM_IDS_BY_TURN.get(turn_id, ()))
    task = _CHANNEL_TASKS_BY_TURN.get(turn_id)
    if task is not None and not task.done():
        # Cancellation first makes Stop immediate and gives every worker a
        # chance to persist its partial reply. The bridge calls below are an
        # additional best-effort cleanup, not something the UI must wait on
        # before the backend stops its own work.
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if stream_ids:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await asyncio.gather(*[
                    client.post(
                        f"{settings.CHAT_BRIDGE_URL}/v1/chat/stop",
                        json={"stream_id": stream_id},
                        headers=_bridge_headers(),
                    )
                    for stream_id in stream_ids
                ], return_exceptions=True)
        except httpx.HTTPError:
            pass

    await active_turns.close_turn(db, turn_id, status="cancelled")
    await db.commit()
    return {"status": "cancelled"}


@router.get("/{channel_id}/messages/stream")
async def stream_channel_message(
    channel_id: uuid.UUID, content: str, attachment_names: str | None = None, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """One SSE event per completed message (see module docstring for why
    this isn't token-level streaming): the human echo lands first, then
    each #-mentioned agent's full reply as its bridge call returns -- all
    mentioned agents run concurrently (2026-08-06, Marcelo: "o chat do
    canal deve executar vários agentes ao mesmo tempo... veja a execução do
    chat da conversations"), so replies are emitted in whichever order they
    actually finish, not mention order. See _wake_agent_turn_isolated for
    why each runs on its own DB session rather than sharing this one."""
    channel = await _get_channel_or_404(db, channel_id)
    human_message = await _post_human_message(db, channel, content, attachment_names)
    await db.commit()
    await db.refresh(human_message)
    human_event = f"data: {json.dumps(ChatChannelMessageOut.model_validate(human_message).model_dump(mode='json'))}\n\n"

    members = await _list_members(db, channel.id)
    agent_members = {m.agent_id: m for m in members if not m.is_human and not m.muted}
    available_agents = [a for a in [await db.get(Agent, aid) for aid in agent_members] if a is not None]
    mentioned = _resolve_mentions(content, available_agents)
    if not mentioned:
        async def _empty_tap() -> AsyncIterator[str]:
            yield human_event
            yield "event: done\ndata: {}\n\n"
        return StreamingResponse(_empty_tap(), media_type="text/event-stream")

    turn = await active_turns.open_turn(
        db,
        scope="channel",
        scope_id=channel.id,
        stream_id=f"channel:{uuid.uuid4().hex}",
        prompt=content,
        supersede_existing=False,
    )
    await db.commit()
    turn_id = turn.id
    queue: "asyncio.Queue[str | None]" = asyncio.Queue()
    await queue.put(human_event)
    await queue.put(f"event: turn_started\ndata: {json.dumps({'turn_id': str(turn_id)})}\n\n")
    task = asyncio.create_task(
        _run_channel_turn(
            channel_id=channel.id,
            turn_id=turn_id,
            agents=[(agent.id, agent_members[agent.id].id, agent.name) for agent in mentioned],
            out_queue=queue,
        )
    )
    _LIVE_CHANNEL_TASKS.add(task)
    _CHANNEL_TASKS_BY_TURN[turn_id] = task

    def _turn_finished(finished: asyncio.Task) -> None:
        _LIVE_CHANNEL_TASKS.discard(finished)
        _CHANNEL_TASKS_BY_TURN.pop(turn_id, None)
        _CHANNEL_STREAM_IDS_BY_TURN.pop(turn_id, None)
        if not finished.cancelled() and (exc := finished.exception()) is not None:
            logger.exception("Channel turn task for channel %s failed", channel_id, exc_info=exc)

    task.add_done_callback(_turn_finished)

    async def _tap() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item

    return StreamingResponse(
        _tap(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{channel_id}/improve-prompt/stream")
async def stream_improve_prompt(
    channel_id: uuid.UUID, payload: ImprovePromptRequest, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Asks the channel's orchestrator agent to rewrite a draft message
    per an improvement instruction -- a private utility call, never a real
    channel turn: no ChatChannelMessage is created, nothing is added to
    the shared transcript, and the call always starts a fresh bridge
    session (hermes_session_id=None) so it never interferes with the
    orchestrator's own conversational continuity in this room (2026-08-06,
    Marcelo: "preciso que o próprio orquestrador me ajude a criar o
    texto... quando confirma ele altera o prompt" -- confirming only
    replaces the compose draft, sending is still a separate, deliberate
    Enter afterwards). Same SSE + ping pattern as stream_channel_message
    (a single non-streaming bridge call can take up to ~650s -- see that
    route's own docstring for why a plain request would otherwise die
    silently on a slow reply)."""
    channel = await _get_channel_or_404(db, channel_id)
    if channel.orchestrator_agent_id is None:
        raise HTTPException(
            status_code=400,
            detail="This channel has no orchestrator designated yet -- set one first (crown icon on a member).",
        )
    orchestrator = await _get_agent_or_404(db, channel.orchestrator_agent_id)
    technique = await get_prompt_technique(db, payload.technique_code)

    prompt = build_prompt_improvement_request(
        actor_context=(
            f'Você é o orquestrador do canal "#{channel.name}" do ForgeHub. O usuário está '
            "rascunhando uma mensagem para o canal e pediu sua ajuda para melhorá-la."
        ),
        draft=payload.draft,
        instruction=payload.instruction,
        technique=technique,
    )

    async def _events() -> AsyncIterator[str]:
        try:
            task = asyncio.ensure_future(_call_bridge_text(orchestrator.profile_slug, prompt, None))
            while True:
                done, _pending = await asyncio.wait([task], timeout=15)
                if done:
                    break
                yield ": ping\n\n"
            bridge_result = await task
            improved_text = (bridge_result.get("reply") or "").strip()
            yield f"data: {json.dumps({'improved_text': improved_text})}\n\n"
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield f"event: error\ndata: {json.dumps({'detail': str(detail)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


# --------------------------------------------------------------------------
# Real execution bridge -- reuses demand.py's dispatch pipeline verbatim
# --------------------------------------------------------------------------


@router.post("/{channel_id}/messages/{message_id}:dispatch-task", response_model=ChatChannelMessageOut)
async def dispatch_channel_message(
    channel_id: uuid.UUID, message_id: uuid.UUID, payload: ChatChannelDispatchTaskRequest, db: AsyncSession = Depends(get_db)
) -> ChatChannelMessage:
    """Explicit, never-automatic bridge from "conversation" to "real
    execution" (see db/models/channel.py's module docstring): creates a
    real AgentDemand and dispatches it through demand.py's own
    _execute_dispatch, exactly like task.py's _dispatch_task_by_id does --
    the channel never re-implements dispatch or duplicates the audit
    trail, it only points at the resulting Message via
    triggered_demand_id. The result narration back into the channel
    happens in demand.py's _finalize_dispatch once the run completes
    (poll-driven, same as every other dispatch)."""
    from app.api.routes.demand import _execute_dispatch
    from app.core.agent_runs import AgentRunDispatchError
    from app.db.models.demand import AgentDemand
    from app.db.models.governance import AuditEvent

    channel = await _get_channel_or_404(db, channel_id)
    message = await db.get(ChatChannelMessage, message_id)
    if message is None or message.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel message not found")
    if message.triggered_demand_id is not None:
        raise HTTPException(status_code=400, detail="This message already triggered a dispatch")
    agent = await _get_agent_or_404(db, payload.agent_id)
    await _get_agent_member_or_404(db, channel_id, agent.id)

    sender_id = message.author_agent_id or channel.orchestrator_agent_id or agent.id
    sender = await db.get(Agent, sender_id)
    # The channel's explicit checkout wins. A project-backed channel may use
    # its Project checkout when the channel leaves this unset. Missing remains
    # missing, so demand.py can return a clear error instead of guessing.
    working_path = channel.working_directory_path
    if working_path is None and channel.project_id is not None:
        project = await db.get(Project, channel.project_id)
        working_path = project.working_directory_path if project is not None else None
    demand = AgentDemand(
        # AgentDemand.from_agent is a compact display snapshot (VARCHAR(50));
        # agent names themselves may legitimately be longer.
        from_agent=(sender.name if sender is not None else "forgehub")[:50],
        from_agent_id=sender_id,
        subject=f"#{channel.name}: {message.content}"[:255],
        body=message.content,
        status="new",
        target_agent_id=payload.agent_id,
        project_id=channel.project_id,
        working_path=working_path,
        # This explicit action creates executable work even when it is not
        # linked to a pre-existing ProjectTask. `origin_id` is optional;
        # classifying an ad-hoc handoff as incubation made dispatch reject it.
        origin_type="task",
        origin_id=payload.project_task_id,
        # Meio de comunicação = Workspace, com o canal como endereço de
        # retorno: quem pediu está olhando esta conversa, e é nela que o
        # resultado tem de aparecer (2026-08-13).
        channel="workspace",
        channel_ref=str(channel.id),
    )
    db.add(demand)
    await db.flush()

    try:
        demand = await _execute_dispatch(db, demand, payload.agent_id, None)
    except AgentRunDispatchError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Host-bridge dispatch failed: {exc}") from exc

    message.triggered_demand_id = demand.id
    db.add(AuditEvent(
        entity_type="chat_channel_message",
        entity_id=message.id,
        event_type="channel_message.dispatched",
        actor="forgehub",
        payload={"description": f"Channel #{channel.name} message dispatched to {agent.name} via Message #{demand.number}"},
    ))
    await db.commit()
    await db.refresh(message)
    return message


# --------------------------------------------------------------------------
# Lightweight channel tasks + promotion to a real ProjectTask
# --------------------------------------------------------------------------


async def _task_out(db: AsyncSession, task: ChatChannelTask) -> ChatChannelTaskOut:
    """Builds the response with approval_status filled from the real
    governance.Approval row (see ChatChannelTask.approval_id's docstring)
    -- never a second, potentially-diverging status field on this table."""
    approval_status = None
    if task.approval_id is not None:
        approval = await db.get(Approval, task.approval_id)
        approval_status = approval.status if approval is not None else None
    out = ChatChannelTaskOut.model_validate(task)
    out.approval_status = approval_status
    return out


@router.post("/{channel_id}/tasks", response_model=ChatChannelTaskOut, status_code=status.HTTP_201_CREATED)
async def create_channel_task(
    channel_id: uuid.UUID, payload: ChatChannelTaskCreate, db: AsyncSession = Depends(get_db)
) -> ChatChannelTaskOut:
    channel = await _get_channel_or_404(db, channel_id)
    if payload.assignee_agent_id is not None:
        await _get_agent_or_404(db, payload.assignee_agent_id)
        await _get_agent_member_or_404(db, channel_id, payload.assignee_agent_id)
    task = ChatChannelTask(
        channel_id=channel_id,
        title=payload.title.strip(),
        assignee_agent_id=payload.assignee_agent_id,
        created_message_id=payload.created_message_id,
    )
    db.add(task)
    await db.flush()

    if payload.promote_immediately:
        if channel.project_id is None:
            raise HTTPException(status_code=400, detail="Channel has no project attached; cannot promote yet")
        task.project_task_id, _ = await conversions.convert_to_quick_task(
            db, title=task.title, content=task.title, project_id=channel.project_id, item_type=conversions.DEFAULT_ITEM_TYPE
        )

    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


@router.get("/{channel_id}/tasks", response_model=list[ChatChannelTaskOut])
async def list_channel_tasks(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ChatChannelTaskOut]:
    await _get_channel_or_404(db, channel_id)
    result = await db.execute(
        select(ChatChannelTask).where(ChatChannelTask.channel_id == channel_id).order_by(ChatChannelTask.created_at.asc())
    )
    return [await _task_out(db, task) for task in result.scalars().all()]


async def _get_channel_task_or_404(db: AsyncSession, channel_id: uuid.UUID, task_id: uuid.UUID) -> ChatChannelTask:
    task = await db.get(ChatChannelTask, task_id)
    if task is None or task.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel task not found")
    return task


@router.patch("/{channel_id}/tasks/{task_id}", response_model=ChatChannelTaskOut)
async def update_channel_task(
    channel_id: uuid.UUID, task_id: uuid.UUID, payload: ChatChannelTaskUpdate, db: AsyncSession = Depends(get_db)
) -> ChatChannelTaskOut:
    task = await _get_channel_task_or_404(db, channel_id, task_id)
    if payload.title is not None:
        task.title = payload.title.strip()
    if payload.status is not None:
        if payload.status not in CHANNEL_TASK_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {CHANNEL_TASK_STATUSES}")
        task.status = payload.status
        # Once promoted, the real ProjectTask is the source of truth for
        # status (see db/models/channel.py's ChatChannelTask docstring) --
        # this row still accepts writes so the channel UI stays responsive,
        # but it's a mirror, not authoritative, from this point on. Keeping
        # both in sync bidirectionally is out of scope for this pass.
    if payload.assignee_agent_id is not None:
        await _get_agent_or_404(db, payload.assignee_agent_id)
        await _get_agent_member_or_404(db, channel_id, payload.assignee_agent_id)
        task.assignee_agent_id = payload.assignee_agent_id
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


@router.post("/{channel_id}/tasks/{task_id}:promote", response_model=ChatChannelTaskOut)
async def promote_channel_task(channel_id: uuid.UUID, task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChatChannelTaskOut:
    """Reuses core/conversions.py's existing "quick_task" target verbatim --
    no new task-creation logic, see db/models/channel.py's module
    docstring."""
    channel = await _get_channel_or_404(db, channel_id)
    task = await _get_channel_task_or_404(db, channel_id, task_id)
    if task.project_task_id is not None:
        raise HTTPException(status_code=400, detail="This task was already promoted")
    if channel.project_id is None:
        raise HTTPException(status_code=400, detail="Channel has no project attached; cannot promote")
    if task.approval_id is not None:
        approval = await db.get(Approval, task.approval_id)
        if approval is not None and approval.status != "approved":
            raise HTTPException(
                status_code=409,
                detail=f"This task's delegation approval is {approval.status}, not approved yet",
            )
    task.project_task_id, _ = await conversions.convert_to_quick_task(
        db, title=task.title, content=task.title, project_id=channel.project_id, item_type=conversions.DEFAULT_ITEM_TYPE
    )
    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)


@router.post("/{channel_id}/tasks/propose", response_model=ChatChannelTaskOut, status_code=status.HTTP_201_CREATED)
async def propose_channel_task(
    channel_id: uuid.UUID, payload: ChatChannelTaskProposeIn, db: AsyncSession = Depends(get_db)
) -> ChatChannelTaskOut:
    """Agent-facing counterpart to create_channel_task (see
    api/schemas/channel.py's ChatChannelTaskProposeIn and
    docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md). Reached
    either via the shared bridge token (main.py's dedicated bypass for this
    exact path) or an agent's own agt_ credential -- both already pass
    RequireAuthMiddleware before this handler runs, so no auth check is
    repeated here; acting_agent_slug is who the request claims to act as,
    resolved and validated as a real channel member below.

    This is the actual enforcement point ("não fazer a tarefa do outro"):
    self-assignment within one's own channel role needs no one's sign-off;
    delegating to a teammate always creates a real governance.Approval and
    blocks the task until someone with authority decides it.
    """
    from app.api.routes.demand import _get_agent_by_slug_or_404

    await _get_channel_or_404(db, channel_id)
    acting_agent = await _get_agent_by_slug_or_404(db, payload.acting_agent_slug)
    assignee_agent = await _get_agent_by_slug_or_404(db, payload.assignee_agent_slug)

    acting_member = (
        await db.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel_id, ChatChannelMember.agent_id == acting_agent.id
            )
        )
    ).scalar_one_or_none()
    if acting_member is None:
        raise HTTPException(status_code=403, detail=f"{acting_agent.name} is not a member of this channel")
    await _get_agent_member_or_404(db, channel_id, assignee_agent.id)

    if payload.role_required is not None and payload.role_required not in PROJECT_AGENT_ROLES:
        raise HTTPException(status_code=400, detail=f"role_required must be one of {PROJECT_AGENT_ROLES}")

    task = ChatChannelTask(
        channel_id=channel_id,
        title=payload.title.strip(),
        assignee_agent_id=assignee_agent.id,
        created_by_agent_id=acting_agent.id,
        role_required=payload.role_required,
    )
    db.add(task)
    await db.flush()

    self_assigning = assignee_agent.id == acting_agent.id
    role_matches = payload.role_required is None or acting_member.role == payload.role_required
    if not (self_assigning and role_matches):
        # Delegating to someone else (or claiming work outside one's own
        # role) always needs sign-off -- a real Approval, decided through
        # governance.py's existing routes, never a bespoke flag on this
        # table. Direct ORM insert (not an HTTP self-call into governance.py),
        # same pattern :dispatch-task already uses for AgentDemand.
        approval = Approval(
            entity_type="chat_channel_task",
            entity_id=task.id,
            approval_type="channel_task_delegation",
            status="pending",
            requested_by=acting_agent.name,
        )
        db.add(approval)
        await db.flush()
        task.approval_id = approval.id

    await db.commit()
    await db.refresh(task)
    return await _task_out(db, task)
