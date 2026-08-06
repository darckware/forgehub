"""ChatChannel domain routes -- a real-time, shared-context room for the
logged-in human + N Agent members. See db/models/channel.py's module
docstring for the design decisions (member choice is always explicit,
project attachment is mutable, turn_policy="mention_only" only, tasks are
lightweight until promoted).

Deliberate scope note on streaming: unlike chat.py's stream_chat_message
(token-by-token SSE proxy of a single agent), a channel turn can wake
several agents sequentially. GET .../messages/stream here streams one SSE
event per completed message (human echo, then each mentioned agent's full
reply as it finishes) rather than per-token -- real, functional real-time
updates without re-implementing chat.py's incremental token relay for an
N-agent fan-out. Token-level streaming per agent is a reasonable future
enhancement, not required for the room to function.
"""
import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.chat import _call_bridge_text, _get_chattable_agent_or_404, _with_language_note
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
from app.core import conversions
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal, get_current_username
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.channel import (
    CHANNEL_TASK_STATUSES,
    ChatChannel,
    ChatChannelMember,
    ChatChannelMessage,
    ChatChannelTask,
)
from app.db.models.governance import Approval
from app.db.models.orchestration import PROJECT_AGENT_ROLES, ProjectAgentMembership
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])

# Safety cap referenced in the plan's risk section -- a message with more
# mentions than this only wakes the first N (in text order); the rest are
# left un-woken rather than silently truncating the message itself.
MAX_MENTIONS_PER_MESSAGE = 5
# How much prior transcript is folded into each woken agent's prompt --
# same "bounded window, not full history" trade-off chat.py's voice mode
# already accepts (chat.py:642-650) generalized to N authors.
CONTEXT_WINDOW_MESSAGES = 30


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
    Condensed from docs/guides/FORGEHUB_CHANNELS_AGENT_GUIDE.md -- keep
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
        f'uma resposta real quando alguém escreve #SeuNome na mensagem (turn_policy=mention_only) '
        f'-- nunca reaja a mensagens de outros agentes por conta própria. Ferramentas MCP '
        f'disponíveis (servidor forgehub-messages): list_channel_members (quem está aqui e a '
        f'função de cada um), propose_channel_task (propor tarefa para você mesmo -- livre dentro '
        f'da sua função -- ou para um colega -- sempre cria uma Approval pendente em Governança), '
        f'list_agent_skills (conferir skills antes de propor/aceitar uma tarefa). Não existe '
        f'comando de mensagem para adicionar/remover membro, mudar função de outro membro ou '
        f'decidir uma aprovação -- essas ações exigem autoridade delegada por Marcelo via '
        f'Governança > Delegações de Autoridade, mesmo para o orquestrador do canal. Este canal '
        f'faz parte do módulo Software Factory do ForgeHub (Product -> Project -> Planejamento -> '
        f'Task, com Cockpit, Pipeline e Governança) -- se precisar entender o pipeline completo '
        f'além do canal em si, consulte docs/guides/MANUAL.md (seção Software Factory). Guia do '
        f'canal em si: docs/guides/FORGEHUB_CHANNELS_AGENT_GUIDE.md. Antes de responder à '
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


async def _wake_agent_turn(
    db: AsyncSession, channel: ChatChannel, member: ChatChannelMember, agent: Agent
) -> ChatChannelMessage:
    """One agent-member's real turn: builds the shared-context prompt,
    calls the bridge (the same call chat.py uses for a single-agent
    session), persists the reply, and updates this member's own Hermes
    session continuity -- independent of any other member's."""
    context = await _build_shared_context(db, channel)
    # Onboarding fires exactly once per member: hermes_session_id is only
    # None before this member's first real turn ever happens (set right
    # below from the bridge's response and never cleared afterwards), so a
    # later mention never repeats it.
    if member.hermes_session_id is None:
        context = await _onboarding_note(db, channel, member) + context
    bridge_result = await _call_bridge_text(agent.profile_slug, _with_language_note(context), member.hermes_session_id)
    member.hermes_session_id = bridge_result.get("session_id") or member.hermes_session_id
    reply = ChatChannelMessage(
        channel_id=channel.id,
        author_type="agent",
        author_agent_id=agent.id,
        author_label=agent.name,
        content=bridge_result["reply"],
    )
    db.add(reply)
    await db.flush()
    return reply


async def _process_channel_turn(
    db: AsyncSession, channel: ChatChannel, content: str, attachment_names: str | None
) -> list[ChatChannelMessage]:
    """turn_policy="mention_only" enforced here: only #-mentioned members
    (capped at MAX_MENTIONS_PER_MESSAGE, in text order -- except an
    explicit "#all" broadcast, which is never truncated) get a real turn,
    sequentially -- never in parallel, and never triggered by another
    agent's own reply (no re-scan of agent-authored content for mentions
    in this call chain -- see module docstring on why autonomous
    agent-to-agent turns aren't implemented yet)."""
    human_message = await _post_human_message(db, channel, content, attachment_names)
    produced = [human_message]

    members = await _list_members(db, channel.id)
    agent_members = {m.agent_id: m for m in members if not m.is_human and not m.muted}
    if not agent_members:
        return produced
    agents = [await db.get(Agent, agent_id) for agent_id in agent_members]
    agents = [a for a in agents if a is not None]

    mentioned = _extract_mentions(content, agents)
    if not _mentions_everyone(content):
        mentioned = mentioned[:MAX_MENTIONS_PER_MESSAGE]
    for agent in mentioned:
        member = agent_members[agent.id]
        reply = await _wake_agent_turn(db, channel, member, agent)
        produced.append(reply)
    return produced


@router.post("/{channel_id}/messages", response_model=list[ChatChannelMessageOut])
async def post_channel_message(
    channel_id: uuid.UUID, payload: ChatChannelMessageCreate, db: AsyncSession = Depends(get_db)
) -> list[ChatChannelMessage]:
    channel = await _get_channel_or_404(db, channel_id)
    try:
        produced = await _process_channel_turn(db, channel, payload.content, payload.attachment_names)
    except httpx.HTTPError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"Chat bridge error: {exc}") from exc
    await db.commit()
    for message in produced:
        await db.refresh(message)
    return produced


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


@router.get("/{channel_id}/messages/stream")
async def stream_channel_message(
    channel_id: uuid.UUID, content: str, attachment_names: str | None = None, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """One SSE event per completed message (see module docstring for why
    this isn't token-level streaming): the human echo lands first, then
    each #-mentioned agent's full reply as its bridge call returns."""
    channel = await _get_channel_or_404(db, channel_id)

    async def _events() -> AsyncIterator[str]:
        try:
            human_message = await _post_human_message(db, channel, content, attachment_names)
            await db.commit()
            await db.refresh(human_message)
            yield f"data: {json.dumps(ChatChannelMessageOut.model_validate(human_message).model_dump(mode='json'))}\n\n"

            members = await _list_members(db, channel.id)
            agent_members = {m.agent_id: m for m in members if not m.is_human and not m.muted}
            agents = [a for a in [await db.get(Agent, aid) for aid in agent_members] if a is not None]
            mentioned = _extract_mentions(content, agents)
            if not _mentions_everyone(content):
                mentioned = mentioned[:MAX_MENTIONS_PER_MESSAGE]
            for agent in mentioned:
                member = agent_members[agent.id]
                # _wake_agent_turn's bridge call is a single non-streaming
                # POST with up to a ~650s timeout (see _call_bridge_text in
                # chat.py) -- unlike chat.py's own token-level stream_chat_
                # message, there's no natural keepalive from the bridge
                # during that single await. Proxies kill a byte-silent SSE
                # connection around ~100s (same note as chat.py's own
                # streaming docstring), so a real agent turn that thinks
                # for longer than that would otherwise die with nothing
                # ever reaching the browser -- shield the call in a task
                # and interleave `: ping` every 15s while it's in flight
                # (2026-08-06, root cause of "enviei a mensagem e não foi
                # feito nada. Não apareceu ele trabalhando").
                task = asyncio.ensure_future(_wake_agent_turn(db, channel, member, agent))
                while True:
                    done, _pending = await asyncio.wait([task], timeout=15)
                    if done:
                        break
                    yield ": ping\n\n"
                reply = await task
                await db.commit()
                await db.refresh(reply)
                yield f"data: {json.dumps(ChatChannelMessageOut.model_validate(reply).model_dump(mode='json'))}\n\n"
                yield ": ping\n\n"
        except Exception as exc:
            # Broad on purpose -- _call_bridge_text raises a plain
            # HTTPException (not httpx.HTTPError) on a non-200 bridge
            # response, which an `except httpx.HTTPError` alone silently
            # let escape this generator (StreamingResponse then just ends
            # the connection with nothing sent, the exact silent-failure
            # symptom this fixes). Every failure now reaches the browser
            # as a real `event: error`, never a dead connection.
            await db.rollback()
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield f"event: error\ndata: {json.dumps({'detail': str(detail)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/{channel_id}/improve-prompt/stream")
async def stream_improve_prompt(
    channel_id: uuid.UUID, draft: str, instruction: str, db: AsyncSession = Depends(get_db)
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

    prompt = (
        f"Você é o orquestrador do canal \"#{channel.name}\" do ForgeHub. Marcelo está rascunhando uma "
        f"mensagem para o canal e pediu sua ajuda para melhorá-la.\n\n"
        f"Rascunho atual:\n---\n{draft}\n---\n\n"
        f"Instrução de melhoria: {instruction}\n\n"
        f"Responda APENAS com o texto melhorado da mensagem, pronto para ser enviado -- sem comentários, "
        f"sem explicações, sem aspas ao redor do texto."
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

    demand = AgentDemand(
        from_agent="forgehub",
        subject=f"#{channel.name}: {message.content}"[:255],
        body=message.content,
        status="new",
        target_agent_id=payload.agent_id,
        project_id=channel.project_id,
        origin_type="task" if payload.project_task_id is not None else "backlog",
        origin_id=payload.project_task_id,
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

    channel = await _get_channel_or_404(db, channel_id)
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
