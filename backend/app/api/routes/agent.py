"""Agent domain routes.

Owns: agents (primary, full CRUD + nested sub_agents/skills), sub_agents
(full CRUD), skills (full CRUD with governance rules), agent_skills /
sub_agent_skills (create/list/delete associations), agent_cost_rates and
agent_capacities (create/list, scoped under their parent agent).

Business rules enforced here (SPEC.md section 6.5 / 5.5):
  - Skill must have version/origin/risk_level/permissions (schema-level
    NOT NULL + choice validation).
  - A skill cannot be created already approved (no self-approval).
  - risk_level == "critical" skills require an explicit, separate
    approval action (PATCH .../approve) -- cannot be approved as part of
    a generic field update.
  - origin == "third_party" skills require security_reviewed=True before
    is_approved can be set True.
  - Approved skills are immutable except for the approval/review flags
    themselves; any other field change on an approved skill is rejected
    with 409, directing the caller to create a new Skill version instead.
  - Sub-agents may only be granted a skill explicitly (sub_agent_skills)
    or use a skill inherited from the parent agent when the parent's
    agent_skills row has inheritable=True. Creating a sub_agent_skills
    row for a skill that is neither explicitly nor inheritably available
    from the parent agent is rejected with 409.

Also owns POST /sync/hermes-foundation, which upserts Agent/SubAgent/
Skill/AgentSkill rows from the Hermes Foundation canonical docs (parsing
lives in app/core/hermes_sync.py, kept DB-free/pure there).

And GET/PUT /{agent_id}/profile-files[/{filename}], the per-agent view of
the SOUL.md / IDENTITY.md / TOOLS.md / ... set that defines an agent.
Directory resolution (Hermes profile vs external CLI runtime home) and the
filename allow-list live in app/core/agent_profile_files.py.

Plus GET/PUT/DELETE /{agent_id}/mcp-servers[/{name}], the per-agent view of
the MCP servers that runtime loads. Each of the five runtimes stores those in
its own file and format; reading and editing them lives in
app/core/agent_mcp.py. ForgeHub keeps no copy of that configuration -- it
edits the runtime's own file, which is what the runtime actually reads.
"""
import asyncio
import hashlib
import json
import secrets
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.agent import (
    AgentCapacityCreate,
    AgentCapacityOut,
    AgentCapacityUpdate,
    AgentCostRateCreate,
    AgentCostRateOut,
    AgentCreate,
    AgentDetailOut,
    AgentListItemOut,
    AgentMcpOverviewItem,
    AgentMcpOverviewOut,
    AgentMcpServerIn,
    AgentMcpServerOut,
    AgentMcpServersOut,
    AgentOut,
    AgentProfileFileInfo,
    AgentProfileFileOut,
    AgentProfileFilesOut,
    AgentProfileFileUpdateIn,
    AgentRuntimeSyncAgentOut,
    AgentRuntimeSyncOut,
    AgentServiceCredentialCreateIn,
    AgentServiceCredentialOut,
    AgentSkillCreate,
    AgentSkillOut,
    AgentTelegramStatusListOut,
    AgentTelegramStatusOut,
    AgentTelegramConversationOut,
    AgentUpdate,
    ForgeRouterKeyImportOut,
    ForgeRouterKeySyncAgentOut,
    ForgeRouterKeySyncOut,
    ForgeRouterServiceKeyOut,
    ForgeRouterServiceOut,
    HermesSyncResultOut,
    SkillAgentRef,
    SkillCreate,
    SkillOut,
    SkillUpdate,
    SkillWithAgentsOut,
    SubAgentCreate,
    SubAgentOut,
    SubAgentSkillCreate,
    SubAgentSkillOut,
    SubAgentUpdate,
    SyncCounts,
)
from app.api.routes.chat import _call_bridge_images, _call_bridge_text
from app.api.schemas.prompt_technique import ImprovePromptRequest
from app.core import agent_mcp, agent_profile_files, agent_runtime_sync, agent_telegram, forgerouter_sync, hermes_sync
from app.core.mcp_catalog_apply import apply_global_servers_to_agent
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.prompt_improvement import build_prompt_improvement_request, get_prompt_technique
from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.db.models.user import User
from app.db.models.agent import (
    Agent,
    AgentCapacity,
    AgentCostRate,
    AgentServiceCredential,
    AgentSkill,
    Skill,
    SubAgent,
    SubAgentSkill,
)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def _get_agent_detail_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.sub_agents),
            selectinload(Agent.agent_skills),
            selectinload(Agent.cost_rates),
            selectinload(Agent.capacities),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def _get_sub_agent_or_404(
    db: AsyncSession, agent_id: uuid.UUID, sub_agent_id: uuid.UUID
) -> SubAgent:
    sub_agent = await db.get(SubAgent, sub_agent_id)
    if sub_agent is None or sub_agent.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sub-agent not found"
        )
    return sub_agent


async def _get_skill_or_404(db: AsyncSession, skill_id: uuid.UUID) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return skill


# ---------------------------------------------------------------------------
# Agents (primary entity)
# ---------------------------------------------------------------------------


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db)) -> Agent:
    data = payload.model_dump()
    api_key = data.pop("forgerouter_api_key", None)
    agent = Agent(**data)
    if api_key:
        agent.forgerouter_api_key_encrypted = encrypt_secret(api_key)
    db.add(agent)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An agent with this name already exists",
        ) from None
    await db.refresh(agent)
    # "apply_to_all_agents" (MCP catalog) must reach agents registered after
    # the flag was set, not just the ones that existed at the time -- see
    # core/mcp_catalog_apply.py's module docstring.
    if await apply_global_servers_to_agent(db, agent):
        await db.commit()
        await db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentListItemOut])
async def list_agents(
    status_filter: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[Agent]:
    # sub_agents is eager-loaded (not just agent_skills/cost_rates/capacities,
    # which AgentDetailOut also carries) so the list view can render each
    # agent's sub-agents nested underneath it without an extra round trip
    # per row.
    query = (
        select(Agent).options(selectinload(Agent.sub_agents)).order_by(Agent.created_at)
    )
    if status_filter is not None:
        query = query.where(Agent.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Telegram channel status
#
# Registered before /{agent_id} so the literal path segment wins over the
# UUID converter. Whole-roster in one call: the systemd check is a single
# host-bridge round trip for every agent, not one per row.
# ---------------------------------------------------------------------------


async def _active_gateway_services(services: list[str]) -> tuple[set[str] | None, str | None]:
    """Which of `services` systemd reports as active, via the host-bridge
    (`/v1/exec` -- the backend container has no systemd of its own).

    Returns (None, error) rather than raising: a Telegram badge that cannot
    be computed must degrade to "unknown", never take down the Agents page."""
    if not services:
        return set(), None
    command = "systemctl show --no-pager --property=Id --property=ActiveState " + " ".join(
        shlex.quote(service) for service in services
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/exec",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"command": command},
            )
    except httpx.HTTPError as e:
        return None, f"Host-bridge unreachable: {e}"
    if resp.status_code != 200:
        return None, f"Host-bridge error: {resp.text[:200]}"
    data = resp.json()
    # A non-zero exit is normal here: systemctl show returns non-zero when any
    # named unit does not exist, while still printing the ones that do.
    return agent_telegram.parse_active_services(data.get("stdout") or ""), None


@router.post("/sync/runtimes", response_model=AgentRuntimeSyncOut)
async def sync_agent_runtimes(db: AsyncSession = Depends(get_db)) -> AgentRuntimeSyncOut:
    """Reconcile the registry with what is actually installed on this host.

    The companion to /sync/hermes-foundation, which reads the canonical *docs*
    and therefore cannot know what an agent runs -- nothing in a contract says
    "this is a Hermes profile". That is why Kairos sat registered with a NULL
    `runtime_type` while its profile directory, gateway unit and MCP config all
    existed: the doc sync had nothing to copy, so every MCP screen reported it
    as an agent no runtime would ever load a server for.

    Detection is by evidence on disk (see core/agent_runtime_sync.py) and only
    ever *fills in* a missing runtime: a registered value is never overwritten,
    because it decides the real command line used to execute the agent. A
    registry that contradicts the disk, an unreachable home, or a profile
    directory nobody claims are reported for a human to judge."""
    result = await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))
    agents = list(result.scalars().all())

    rows: list[AgentRuntimeSyncAgentOut] = []
    updated = 0
    for agent in agents:
        plan = agent_runtime_sync.plan_for_agent(
            agent_id=str(agent.id),
            agent_name=agent.name,
            profile_slug=agent.profile_slug,
            runtime_type=agent.runtime_type,
            home_path=agent.home_path,
        )
        applied = False
        if plan.fill_runtime_type:
            agent.runtime_type = plan.fill_runtime_type
            applied = True
            updated += 1
            # Same "global reaches agents registered/typed later" rule as
            # create_agent above -- this agent just became MCP-eligible for
            # the first time, so global catalog servers apply now too.
            await apply_global_servers_to_agent(db, agent)
        rows.append(
            AgentRuntimeSyncAgentOut(
                agent_id=agent.id,
                agent_name=agent.name,
                profile_slug=agent.profile_slug,
                runtime_type=agent.runtime_type,
                detected_runtime_type=plan.detected.runtime_type,
                evidence=plan.detected.evidence,
                home_path=plan.detected.home_path,
                home_resolved=plan.detected.home_resolved,
                mcp_config_path=plan.detected.mcp_config_path,
                mcp_config_exists=plan.detected.mcp_config_exists,
                applied=applied,
                issues=plan.issues,
            )
        )
    if updated:
        await db.commit()

    return AgentRuntimeSyncOut(
        checked=len(agents),
        updated=updated,
        agents=rows,
        unregistered_profiles=agent_runtime_sync.unregistered_profiles(
            {a.profile_slug for a in agents if a.profile_slug}
        ),
    )


def _forgerouter_key_unchanged(agent: Agent, api_key: str) -> bool:
    """True when the agent's stored (encrypted) key already decrypts to this
    exact plaintext -- ciphertext can't be compared directly, Fernet
    encryption is nondeterministic (fresh IV/timestamp on every call)."""
    if not agent.forgerouter_api_key_encrypted:
        return False
    try:
        return decrypt_secret(agent.forgerouter_api_key_encrypted) == api_key
    except ValueError:
        return False


@router.post("/{agent_id}/forgerouter-key/import", response_model=ForgeRouterKeyImportOut)
async def import_forgerouter_key(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ForgeRouterKeyImportOut:
    """Import this one agent's already-issued ForgeRouter API key straight
    from ForgeRouter's own registry (ai_router.agents, see
    core/forgerouter_sync.py) into forgerouter_api_key_encrypted -- the
    per-agent "Import" button next to the manual paste-and-save field
    (2026-07-29, Marcelo: "seria melhor criar um botão de importação do
    api key do agente"). See /sync/forgerouter-keys below for the "all
    agents at once" counterpart ("adiciona opção de todos e para cada
    agente") -- both share the matching/overwrite rule documented there."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    keys_by_name = {k.name.strip().lower(): k.api_key for k in await forgerouter_sync.read_forgerouter_agent_keys()}
    api_key = keys_by_name.get(agent.name.strip().lower())
    if api_key is None:
        return ForgeRouterKeyImportOut(matched=False, updated=False, forgerouter_api_key_configured=agent.forgerouter_api_key_configured)

    updated = not _forgerouter_key_unchanged(agent, api_key)
    if updated:
        agent.forgerouter_api_key_encrypted = encrypt_secret(api_key)
        await db.commit()
    return ForgeRouterKeyImportOut(matched=True, updated=updated, forgerouter_api_key_configured=True)


@router.post("/sync/forgerouter-keys", response_model=ForgeRouterKeySyncOut)
async def sync_forgerouter_keys(db: AsyncSession = Depends(get_db)) -> ForgeRouterKeySyncOut:
    """Bulk counterpart of POST /{agent_id}/forgerouter-key/import above:
    imports every active agent's already-issued ForgeRouter key in one
    pass, for every agent registered in ForgeRouter -- not just the
    Hermes-profile ones /sync/hermes-foundation already covers via
    config.yaml (2026-07-29, Marcelo: "tem que gravar no campo forgerouter
    api key de todos os agentes cadastrado no forgerouter").

    Matched by exact agent name (case-insensitive) -- ai_router.agents has
    no FK back to ForgeHub, name is the only shared key. Always overwrites
    on a match: ai_router.agents is the authoritative, currently-live
    value (ForgeRouter itself issued it and wrote it into that agent's own
    config), so a stale ForgeHub copy should lose to it, unlike the
    fill-only rule /sync/hermes-foundation and /sync/runtimes use for
    fields a human might have hand-edited."""
    result = await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))
    agents = list(result.scalars().all())
    keys_by_name = {k.name.strip().lower(): k.api_key for k in await forgerouter_sync.read_forgerouter_agent_keys()}

    rows: list[ForgeRouterKeySyncAgentOut] = []
    matched = updated = 0
    for agent in agents:
        api_key = keys_by_name.pop(agent.name.strip().lower(), None)
        if api_key is None:
            rows.append(ForgeRouterKeySyncAgentOut(agent_id=agent.id, agent_name=agent.name))
            continue
        matched += 1
        changed = not _forgerouter_key_unchanged(agent, api_key)
        if changed:
            agent.forgerouter_api_key_encrypted = encrypt_secret(api_key)
            updated += 1
        rows.append(
            ForgeRouterKeySyncAgentOut(agent_id=agent.id, agent_name=agent.name, matched=True, updated=changed)
        )
    if updated:
        await db.commit()

    return ForgeRouterKeySyncOut(
        checked=len(agents),
        matched=matched,
        updated=updated,
        agents=rows,
        unmatched_forgerouter_agents=sorted(keys_by_name),
    )


@router.get("/forgerouter-services", response_model=list[ForgeRouterServiceOut])
async def list_forgerouter_services(_admin: User = Depends(get_current_admin)) -> list[ForgeRouterServiceOut]:
    """Service-kind entries in ForgeRouter's own registry (ai_router.agents,
    kind='service' -- e.g. "Hindsight") for Settings' "Default agent for
    project API keys" picker (2026-07-29, Marcelo: "eu adicionei agente do
    tipo serviço no forgerouter, filtra somente esses"). Distinct from the
    Agent roster: a service has no ForgeHub Agent row of its own, so this
    reads straight from ForgeRouter. Declared before /{agent_id} so this
    literal path is never parsed as an agent UUID. Name only -- see
    /forgerouter-services/{name} for the key itself, same
    never-in-a-list-response pattern as every other secret in this module."""
    services = await forgerouter_sync.read_forgerouter_service_keys()
    return [ForgeRouterServiceOut(name=s.name) for s in services]


@router.get("/forgerouter-services/{name}", response_model=ForgeRouterServiceKeyOut)
async def get_forgerouter_service_key(name: str, _admin: User = Depends(get_current_admin)) -> ForgeRouterServiceKeyOut:
    """One service's plaintext key -- backs the Dashboard's
    ProjectsForgeRouterCard prompt pre-fill. Declared before /{agent_id} for
    the same literal-path reason as above."""
    services = await forgerouter_sync.read_forgerouter_service_keys()
    match = next((s for s in services if s.name == name), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Service '{name}' not found in ForgeRouter's registry")
@router.get("/by-slug/{slug}", response_model=AgentDetailOut)
async def get_agent_by_slug(
    slug: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_admin)
) -> AgentDetailOut:
    """Retrieve agent details by profile slug."""
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.sub_agents),
            selectinload(Agent.agent_skills),
            selectinload(Agent.cost_rates),
            selectinload(Agent.capacities),
        )
        .where(Agent.profile_slug == slug.lower())
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with profile_slug '{slug}' not found")
    out = AgentDetailOut.model_validate(agent)
    if agent.forgerouter_api_key_encrypted:
        try:
            out.forgerouter_api_key = decrypt_secret(agent.forgerouter_api_key_encrypted)
        except ValueError:
            out.forgerouter_api_key = None
    return out


@router.get("/mcp-servers", response_model=AgentMcpOverviewOut)
async def get_agents_mcp_overview(db: AsyncSession = Depends(get_db)) -> AgentMcpOverviewOut:
    """Every agent's MCP servers in one payload, for the ecosystem-wide MCP
    screen. Declared before /{agent_id} so this literal path is not parsed as
    an agent UUID.

    Agents whose runtime cannot load MCP servers are included with
    `supported=False` and an empty list: the point of this screen is comparing
    who has which server, and silently dropping an agent would read as "it has
    none configured" rather than "it cannot have any".

    Retired agents (`is_active=False`) are excluded, though: this screen is a
    coverage matrix, one column per agent, and an agent nobody runs anymore
    adds a permanently empty column that reads as a gap to close."""
    result = await db.execute(select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name))
    items: list[AgentMcpOverviewItem] = []
    for agent in result.scalars().all():
        fmt = agent_mcp.format_for(agent.runtime_type)
        host_path = agent_mcp.config_host_path(agent.effective_home_path, fmt) if fmt else None
        resolved = agent_mcp.resolve_host_file(host_path) if host_path else None
        servers: list[AgentMcpServerOut] = []
        error: str | None = None
        if fmt and host_path and resolved is not None:
            try:
                servers = [
                    AgentMcpServerOut(**info.__dict__)
                    for info in agent_mcp.read_servers(host_path, fmt)
                ]
            except agent_mcp.McpConfigError as e:
                error = str(e)
        items.append(
            AgentMcpOverviewItem(
                agent_id=agent.id,
                agent_name=agent.name,
                profile_slug=agent.profile_slug,
                runtime_type=agent.runtime_type,
                config_path=host_path,
                config_exists=resolved is not None,
                supported=fmt is not None,
                supports_toggle=bool(fmt and fmt.toggle_field),
                error=error,
                servers=servers,
            )
        )
    return AgentMcpOverviewOut(agents=items)


@router.get("/telegram-status", response_model=AgentTelegramStatusListOut)
async def get_agents_telegram_status(
    db: AsyncSession = Depends(get_db),
) -> AgentTelegramStatusListOut:
    """Telegram channel health for every registered agent: whether the
    channel is installed (bot token + home channel in the profile's own .env)
    and whether the gateway daemon that serves it is running."""
    result = await db.execute(select(Agent).order_by(Agent.name))
    agents = list(result.scalars().all())
    services = sorted(
        {
            service
            for agent in agents
            if (
                service := agent_telegram.gateway_service_name(
                    agent.profile_slug, agent.runtime_type
                )
            )
        }
    )
    active, check_error = await _active_gateway_services(services)
    return AgentTelegramStatusListOut(
        agents=[
            AgentTelegramStatusOut(
                agent_id=agent.id,
                agent_name=agent.name,
                **vars(
                    agent_telegram.build_status(
                        profile_slug=agent.profile_slug,
                        required=agent.telegram_required,
                        home_path=agent.effective_home_path,
                        runtime_type=agent.runtime_type,
                        active_services=active,
                    )
                ),
            )
            for agent in agents
        ],
        check_error=check_error,
    )


async def _telegram_conversation(agent: Agent) -> AgentTelegramConversationOut:
    if not agent.profile_slug:
        raise HTTPException(status_code=400, detail="This agent has no Hermes profile")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/telegram/{agent.profile_slug}/messages",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Telegram bridge error: {response.text[:500]}",
        )
    payload = response.json()
    return AgentTelegramConversationOut(
        agent_id=agent.id,
        agent_name=agent.name,
        profile_slug=agent.profile_slug,
        session_id=payload.get("session_id"),
        chat_id=payload.get("chat_id"),
        messages=payload.get("messages") or [],
    )


@router.get("/{agent_id}/telegram/messages", response_model=AgentTelegramConversationOut)
async def get_agent_telegram_messages(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AgentTelegramConversationOut:
    """Visible transcript from the agent's latest real Telegram session."""
    return await _telegram_conversation(await _get_agent_or_404(db, agent_id))


@router.post("/{agent_id}/telegram/messages", response_model=AgentTelegramConversationOut)
async def send_agent_telegram_message(
    agent_id: uuid.UUID,
    message: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
) -> AgentTelegramConversationOut:
    """Continue the agent's Telegram context from ForgeHub and relay its reply.

    Telegram does not let a bot impersonate an inbound human message. The
    operator prompt is therefore appended by resuming Hermes' actual Telegram
    session, and the agent's answer is delivered to that same Telegram chat
    through the agent's own bot.

    Attachments (2026-08-15, parity with chat.py's send_chat_message, whose
    image/text-file split this mirrors exactly): an image goes through
    `_call_bridge_images` (the same vision-capable bridge call the
    Conversations composer uses); a text file is decoded and pasted inline
    into the prompt, never uploaded as a binary the agent would need a tool
    to fetch. Both still resume the same real `conversation.session_id`
    (never `None`, unlike the improve-prompt route below) so the attachment
    lands in the actual ongoing Telegram thread, not a throwaway one.
    """
    agent = await _get_agent_or_404(db, agent_id)
    conversation = await _telegram_conversation(agent)
    if not conversation.session_id or not conversation.chat_id:
        raise HTTPException(
            status_code=409,
            detail="No Telegram conversation exists yet. Send the agent's bot a message first.",
        )
    if not message.strip() and not files:
        raise HTTPException(status_code=400, detail="message or file is required")

    if files:
        images: list[tuple[str, bytes]] = []
        text_blocks: list[str] = []
        for f in files:
            content = await f.read()
            if (f.content_type or "").startswith("image/"):
                images.append((f.filename or "image.png", content))
            else:
                try:
                    text_content = content.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=400, detail="Attached file must be a text file or an image"
                    ) from None
                text_blocks.append(f'Content of file "{f.filename}" pasted below:\n---\n{text_content}\n---')
        if images:
            combined_message = "\n\n".join([*text_blocks, message]).strip()
            bridge_result = await _call_bridge_images(
                conversation.profile_slug,
                combined_message or "See the attached images.",
                conversation.session_id,
                images,
            )
        else:
            outgoing_message = "\n\n".join([*text_blocks, message]).strip()
            bridge_result = await _call_bridge_text(
                conversation.profile_slug, outgoing_message, conversation.session_id
            )
    else:
        bridge_result = await _call_bridge_text(conversation.profile_slug, message, conversation.session_id)

    reply = (bridge_result.get("reply") or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail="Agent returned an empty Telegram reply")
    bridge_headers = {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
    async with httpx.AsyncClient(timeout=660.0) as client:
        sent = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/messages/send",
            json={
                "target": f"telegram:{conversation.chat_id}",
                "message": reply,
                "profile": conversation.profile_slug,
            },
            headers=bridge_headers,
        )
        if sent.status_code != 200:
            # The Hermes turn has already been committed to the real session.
            # Returning a normal transcript with a delivery warning prevents
            # the UI from retrying the whole prompt and generating a duplicate
            # answer merely because Telegram delivery failed afterward.
            refreshed = await _telegram_conversation(agent)
            refreshed.delivery_error = f"Telegram delivery error: {sent.text[:500]}"
            return refreshed
    return await _telegram_conversation(agent)


@router.post("/{agent_id}/telegram/improve-prompt/stream")
async def stream_telegram_improve_prompt(
    agent_id: uuid.UUID, payload: ImprovePromptRequest, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Same private rewrite-only call as chat.py's stream_improve_prompt
    (2026-08-15, parity with the Conversations/Channels composer) -- that
    one resolves its agent from a ForgeHub chat session, which the
    Telegram pane doesn't have; this resolves it directly from the agent
    id already in the URL, since a Telegram tab only ever means one agent.
    Never touches the agent's real Telegram session
    (`hermes_session_id=None`, a fresh bridge call every time) so drafting
    can never leak a stray turn into the actual conversation."""
    agent = await _get_agent_or_404(db, agent_id)
    technique = await get_prompt_technique(db, payload.technique_code)
    prompt = build_prompt_improvement_request(
        actor_context=(
            f'Você é o agente "{agent.name}" no ForgeHub. O usuário está rascunhando uma mensagem '
            "para enviar via Telegram e pediu sua ajuda para melhorá-la."
        ),
        draft=payload.draft,
        instruction=payload.instruction,
        technique=technique,
    )

    async def _events() -> AsyncIterator[str]:
        try:
            task = asyncio.ensure_future(_call_bridge_text(agent.profile_slug, prompt, None))
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


# ---------------------------------------------------------------------------
# Hermes Foundation sync
# ---------------------------------------------------------------------------


@router.post("/sync/hermes-foundation", response_model=HermesSyncResultOut)
async def sync_hermes_foundation(db: AsyncSession = Depends(get_db)) -> HermesSyncResultOut:
    """Upsert Agent/SubAgent/Skill/AgentSkill rows from the Hermes
    Foundation canonical docs (app/core/hermes_sync.py).

    Safe to re-run: an agent that already exists (matched by
    profile_slug) only gets its Hermes-mirrored fields refreshed (layer,
    runtime_tier, telegram_required, has_profile, mission, source_path).
    name/status/is_active/agent_type/description are set once at first
    creation and never touched again, so manual edits made in ForgeHub
    survive a re-sync.

    A Hermes profile is roster-eligible only when it is both provisioned
    under /root/.hermes/profiles/ and present in the active Foundation
    registry.  Directory presence alone cannot reactivate an archived role.

    name/layer/mission are read from each profile's own IDENTITY.md first
    (`hermes_sync.parse_profile_identity` -- the agent's live self-declared
    configuration) and only fall back to the Foundation docs
    (ECOSYSTEM_AGENTS.md / <NAME>.md) when IDENTITY.md is missing that
    field (2026-07-29, Marcelo: "a sincronização vem da documentação que
    pode estar desatualizada. E não da configuração dos agentes"). Only
    runtime_tier and telegram_required stay doc-only -- no profile-folder
    equivalent exists for either. A profile with no matching registry entry
    and no IDENTITY.md is still registered, just without that metadata.
    """
    warnings: list[str] = []
    agents_created = agents_updated = 0
    sub_agents_created = sub_agents_updated = 0
    skills_created = skills_updated = 0
    agent_skills_created = 0

    # 1. Agent roster.
    registry_by_slug = {e["profile_slug"]: e for e in hermes_sync.parse_agent_registry()}
    agent_by_slug: dict[str, Agent] = {}
    active_profile_slugs = hermes_sync.list_active_provisioned_profiles()
    for slug in active_profile_slugs:
        has_registry_entry = slug in registry_by_slug
        entry = registry_by_slug.get(slug)
        if entry is None:
            warnings.append(
                f"Profile '{slug}' has no ECOSYSTEM_AGENTS.md entry; registered with defaults."
            )
            entry = {
                "profile_slug": slug,
                "name": slug,
                "layer": None,
                "telegram_required": False,
                "runtime_tier": None,
            }
        mission, source_path = hermes_sync.parse_agent_mission(slug)
        # The profile's own IDENTITY.md (live agent configuration) wins over
        # ECOSYSTEM_AGENTS.md/<NAME>.md (Foundation documentation, which can
        # go stale) for name/layer/mission -- 2026-07-29, Marcelo: "a
        # sincronização vem da documentação que pode estar desatualizada. E
        # não da configuração dos agentes" (docs still consulted as
        # fallback when IDENTITY.md doesn't have a field, per "você pode
        # até consultar algumas coisas da documentação"). Crons/scripts
        # already read live from the profile folder (AgentEcosystemHierarchy.tsx,
        # useFoundationCrons/useFoundationAllScripts) and sub-agents are
        # intentionally catalog-only WORKER/ROLE entries with no profile of
        # their own (SUBAGENTS_CATALOG.md's own text) -- neither needed a
        # source change here.
        identity = hermes_sync.parse_profile_identity(slug)
        if identity.get("name"):
            entry["name"] = identity["name"]
        if identity.get("layer"):
            entry["layer"] = identity["layer"]
        if identity.get("mission"):
            mission = identity["mission"]
            source_path = f"/root/.hermes/profiles/{slug}/IDENTITY.md"
        forge_router_api_key = hermes_sync.read_profile_forgerouter_api_key(slug)
        department, sector, reports_to_profile_slug = hermes_sync.organization_for_profile(slug)

        result = await db.execute(select(Agent).where(Agent.profile_slug == slug))
        agent = result.scalar_one_or_none()
        if agent is None:
            agent = Agent(
                name=entry["name"],
                description=mission,
                agent_type="coordinator" if entry["runtime_tier"] == "A" else "executor",
                status="active",
                is_active=True,
                profile_slug=slug,
                layer=entry["layer"],
                runtime_tier=entry["runtime_tier"],
                telegram_required=entry["telegram_required"],
                has_profile=True,
                mission=mission,
                source_path=source_path,
                department=department,
                sector=sector,
                reports_to_profile_slug=reports_to_profile_slug,
                forgerouter_api_key_encrypted=(
                    encrypt_secret(forge_router_api_key) if forge_router_api_key else None
                ),
            )
            db.add(agent)
            agents_created += 1
        else:
            # Only refresh a field when this run actually found real data
            # for it -- a transient/empty doc read must never wipe an
            # existing agent's real value back to defaults. `layer` has two
            # possible sources now (IDENTITY.md above, or the registry doc),
            # so it refreshes when either produced something; runtime_tier/
            # telegram_required have no profile-folder equivalent, so they
            # stay strictly registry-doc-gated.
            if identity.get("layer") or has_registry_entry:
                agent.layer = entry["layer"]
            if has_registry_entry:
                agent.runtime_tier = entry["runtime_tier"]
                agent.telegram_required = entry["telegram_required"]
            agent.has_profile = True
            agent.mission = mission
            agent.source_path = source_path
            agent.department = department
            agent.sector = sector
            agent.reports_to_profile_slug = reports_to_profile_slug
            if forge_router_api_key and not agent.forgerouter_api_key_encrypted:
                agent.forgerouter_api_key_encrypted = encrypt_secret(forge_router_api_key)
            agents_updated += 1
        await db.flush()
        agent_by_slug[slug] = agent

    # A restored directory is not a lifecycle promotion. Preserve the row for
    # audit and references, but stop presenting a previously synced Hermes
    # identity as active when the canonical registry no longer contains it.
    # If the registry read itself failed, do not mass-retire anything: an
    # empty active set is treated as unavailable evidence, not as an empty
    # ecosystem.
    if active_profile_slugs:
        stale_result = await db.execute(
            select(Agent).where(
                Agent.runtime_type == "hermes",
                Agent.has_profile.is_(True),
                Agent.profile_slug.not_in(active_profile_slugs),
                Agent.is_active.is_(True),
            )
        )
        for stale_agent in stale_result.scalars().all():
            stale_agent.is_active = False
            stale_agent.status = "retired"
            agents_updated += 1
            warnings.append(
                f"Profile '{stale_agent.profile_slug}' is not in the active Foundation registry; retired."
            )

    # 2. Sub-agent WORKER/ROLE catalog, per owning agent.
    for slug, roles in hermes_sync.parse_subagent_catalog().items():
        agent = agent_by_slug.get(slug)
        if agent is None:
            warnings.append(f"Sub-agent roles found for unknown profile '{slug}'; skipped.")
            continue
        for role in roles:
            result = await db.execute(
                select(SubAgent).where(
                    SubAgent.agent_id == agent.id, SubAgent.name == role["name"]
                )
            )
            sub_agent = result.scalar_one_or_none()
            if sub_agent is None:
                db.add(
                    SubAgent(
                        agent_id=agent.id,
                        name=role["name"],
                        description=role["description"],
                        status="active",
                        is_active=True,
                    )
                )
                sub_agents_created += 1
            else:
                sub_agent.description = role["description"]
                sub_agents_updated += 1
        await db.flush()

    # 3. Skills (deduped by name+version) and their agent grants.
    skill_cache: dict[tuple[str, str], Skill] = {}
    for slug, agent in agent_by_slug.items():
        for skill_data in hermes_sync.parse_profile_skills(slug):
            key = (skill_data["name"], skill_data["version"])
            skill = skill_cache.get(key)
            if skill is None:
                result = await db.execute(
                    select(Skill).where(Skill.name == key[0], Skill.version == key[1])
                )
                skill = result.scalar_one_or_none()
                if skill is None:
                    skill = Skill(
                        name=skill_data["name"],
                        version=skill_data["version"],
                        description=skill_data["description"],
                        origin=skill_data["origin"],
                        risk_level=skill_data["risk_level"],
                        permissions=skill_data["permissions"],
                        is_approved=False,
                        security_reviewed=False,
                    )
                    db.add(skill)
                    await db.flush()
                    skills_created += 1
                else:
                    skills_updated += 1
                skill_cache[key] = skill

            result = await db.execute(
                select(AgentSkill).where(
                    AgentSkill.agent_id == agent.id, AgentSkill.skill_id == skill.id
                )
            )
            if result.scalar_one_or_none() is None:
                db.add(AgentSkill(agent_id=agent.id, skill_id=skill.id, inheritable=True))
                agent_skills_created += 1

    await db.commit()

    return HermesSyncResultOut(
        agents=SyncCounts(created=agents_created, updated=agents_updated),
        sub_agents=SyncCounts(created=sub_agents_created, updated=sub_agents_updated),
        skills=SyncCounts(created=skills_created, updated=skills_updated),
        agent_skills=SyncCounts(created=agent_skills_created),
        warnings=warnings,
    )


# NOTE: the literal-segment routes below (/skills, /skills/{skill_id})
# are intentionally registered BEFORE the parameterized
# "/{agent_id}" routes. Starlette matches routes in registration
# order, so without this ordering "GET /api/v1/agents/skills" would be
# swallowed by "GET /api/v1/agents/{agent_id}" (agent_id="skills") and
# 404/422 instead of listing skills.


# ---------------------------------------------------------------------------
# Skills (top-level governed catalogue)
# ---------------------------------------------------------------------------


@router.post("/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, db: AsyncSession = Depends(get_db)) -> Skill:
    # SPEC 6.5 rule 5/6: a skill can never be created already-approved --
    # approval is a distinct governance action (see update_skill below).
    skill = Skill(**payload.model_dump(), is_approved=False, security_reviewed=False)
    db.add(skill)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A skill with this name and version already exists",
        ) from None
    await db.refresh(skill)
    return skill


@router.get("/skills", response_model=list[SkillWithAgentsOut])
async def list_skills(
    risk_level: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[SkillWithAgentsOut]:
    """List every skill with the agents it is granted to (agent_skills),
    so the Skills page can show and filter by holder in one request."""
    query = (
        select(Skill)
        .options(selectinload(Skill.agent_skills).selectinload(AgentSkill.agent))
        .order_by(Skill.name, Skill.version)
    )
    if risk_level is not None:
        query = query.where(Skill.risk_level == risk_level)
    result = await db.execute(query)
    return [
        SkillWithAgentsOut(
            **SkillOut.model_validate(skill).model_dump(),
            agents=sorted(
                (
                    SkillAgentRef(agent_id=grant.agent.id, agent_name=grant.agent.name)
                    for grant in skill.agent_skills
                ),
                key=lambda ref: ref.agent_name.lower(),
            ),
        )
        for skill in result.scalars().all()
    ]


@router.get("/skills/{skill_id}", response_model=SkillOut)
async def get_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Skill:
    return await _get_skill_or_404(db, skill_id)


@router.patch("/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: uuid.UUID, payload: SkillUpdate, db: AsyncSession = Depends(get_db)
) -> Skill:
    skill = await _get_skill_or_404(db, skill_id)
    updates = payload.model_dump(exclude_unset=True)

    # SPEC 6.5 rule 8: approved skills must not change without a new
    # version. Once approved, only the approval/review flags themselves
    # may still move (e.g. to revoke security_reviewed); any descriptive
    # or risk-relevant field is frozen.
    if skill.is_approved:
        mutable_fields = {"is_approved", "security_reviewed"}
        frozen_changes = set(updates) - mutable_fields
        if frozen_changes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Skill is approved and immutable except for approval/review "
                    "flags; create a new Skill row with an incremented version "
                    f"instead. Rejected fields: {sorted(frozen_changes)}"
                ),
            )

    target_is_approved = updates.get("is_approved", skill.is_approved)
    target_origin = updates.get("origin", skill.origin)
    target_security_reviewed = updates.get(
        "security_reviewed", skill.security_reviewed
    )
    if target_is_approved and target_origin == "third_party" and not target_security_reviewed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Third-party skills require security_reviewed=True before approval",
        )

    for field, value in updates.items():
        setattr(skill, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A skill with this name and version already exists",
        ) from None
    await db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    skill = await _get_skill_or_404(db, skill_id)
    await db.delete(skill)
    await db.commit()


@router.get("/{agent_id}", response_model=AgentDetailOut)
async def get_agent(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_admin)
) -> AgentDetailOut:
    """Admin-gated (2026-07-29, was open to any authenticated caller before):
    this is the one place forgerouter_api_key_encrypted is ever decrypted
    back out to the response, so it needed the same admin gate the field's
    own write side (PATCH .../forgerouter_api_key) already implicitly
    relies on -- see AgentDetailOut.forgerouter_api_key's docstring."""
    agent = await _get_agent_detail_or_404(db, agent_id)
    out = AgentDetailOut.model_validate(agent)
    if agent.forgerouter_api_key_encrypted:
        try:
            out.forgerouter_api_key = decrypt_secret(agent.forgerouter_api_key_encrypted)
        except ValueError:
            out.forgerouter_api_key = None
    return out


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID, payload: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> Agent:
    agent = await _get_agent_or_404(db, agent_id)
    updates = payload.model_dump(exclude_unset=True)
    api_key = updates.pop("forgerouter_api_key", None)
    clear_api_key = updates.pop("clear_forgerouter_api_key", False)
    if api_key:
        agent.forgerouter_api_key_encrypted = encrypt_secret(api_key)
    elif clear_api_key:
        agent.forgerouter_api_key_encrypted = None
    runtime_eligibility_touched = "runtime_type" in updates or "home_path" in updates
    for field, value in updates.items():
        setattr(agent, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Two unique constraints can land here now that profile_slug is
        # editable (uq_agents_profile_slug alongside agents_name_key) --
        # naming only the first would send someone hunting for a duplicate
        # name that doesn't exist.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another agent already uses this name or profile_slug",
        ) from None
    await db.refresh(agent)
    # AgentCreate has no runtime_type/home_path fields at all (an agent is
    # always created bare, then typed later here or by sync_agent_runtimes)
    # -- this PATCH, not creation, is where an agent actually becomes
    # MCP-eligible for the first time, so this is where "apply_to_all_agents"
    # must also reach it.
    if runtime_eligibility_touched and await apply_global_servers_to_agent(db, agent):
        await db.commit()
        await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    agent = await _get_agent_or_404(db, agent_id)
    await db.delete(agent)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This agent has related operational history. "
                "Retire it instead of deleting it."
            ),
        ) from None


# ---------------------------------------------------------------------------
# Profile Markdown files (SOUL.md, IDENTITY.md, TOOLS.md, ...)
#
# Keyed by agent, not by Hermes profile: foundation.py's
# /profiles/{profile}/files/{filename} can only ever reach the eight agents
# that have a directory under /root/.hermes/profiles, which left the four
# external CLI runtimes (Porthus/claude, Aramis/codex, Dartan/agy,
# Vector/openclaw) with no way to show their own identity files. Directory
# resolution and the filename allow-list live in core/agent_profile_files.py.
# ---------------------------------------------------------------------------


def _resolve_profile_home(agent: Agent) -> tuple[str | None, Path | None]:
    host_home = agent.effective_home_path
    return host_home, agent_profile_files.resolve_home_dir(host_home)


def _require_profile_file(agent: Agent, filename: str) -> tuple[str, Path]:
    """Resolve one profile file for an agent, or raise. Both the allow-list
    check and the "stays inside the home directory" check happen here --
    `filename` comes straight from the URL."""
    host_home, home_dir = _resolve_profile_home(agent)
    if host_home is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This agent has no profile directory. Register one in "
                "'Profile directory' on the agent page."
            ),
        )
    if home_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile directory not reachable from the backend: {host_home}",
        )
    allowed = agent_profile_files.allowed_filenames(agent.runtime_type, agent.profile_slug)
    path = agent_profile_files.resolve_file(home_dir, filename, allowed)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown profile file")
    return host_home, path


@router.get("/{agent_id}/profile-files", response_model=AgentProfileFilesOut)
async def list_agent_profile_files(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AgentProfileFilesOut:
    """List every profile file this agent may have, present or not. Missing
    files are returned with exists=False rather than omitted -- "SOUL.md was
    never written" is exactly what an operator needs to see."""
    agent = await _get_agent_or_404(db, agent_id)
    host_home, home_dir = _resolve_profile_home(agent)
    allowed = agent_profile_files.allowed_filenames(agent.runtime_type, agent.profile_slug)
    files: list[AgentProfileFileInfo] = []
    for filename in allowed:
        if home_dir is None:
            files.append(
                AgentProfileFileInfo(
                    filename=filename,
                    path=f"{(host_home or '').rstrip('/')}/{filename}",
                    exists=False,
                )
            )
            continue
        info = agent_profile_files.stat_file(home_dir / filename, filename, host_home or "")
        files.append(AgentProfileFileInfo(**info.__dict__))
    return AgentProfileFilesOut(
        agent_id=agent.id,
        home_path=host_home,
        home_resolved=home_dir is not None,
        files=files,
    )


@router.get("/{agent_id}/profile-files/{filename}", response_model=AgentProfileFileOut)
async def get_agent_profile_file(
    agent_id: uuid.UUID, filename: str, db: AsyncSession = Depends(get_db)
) -> AgentProfileFileOut:
    agent = await _get_agent_or_404(db, agent_id)
    host_home, path = _require_profile_file(agent, filename)
    try:
        content: str | None = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = None
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read {filename}: {e}",
        ) from e
    return AgentProfileFileOut(
        agent_id=agent.id,
        filename=filename,
        path=f"{host_home.rstrip('/')}/{filename}",
        content=content,
    )


@router.put("/{agent_id}/profile-files/{filename}", response_model=AgentProfileFileOut)
async def update_agent_profile_file(
    agent_id: uuid.UUID,
    filename: str,
    payload: AgentProfileFileUpdateIn,
    db: AsyncSession = Depends(get_db),
) -> AgentProfileFileOut:
    """Write a profile file, creating it if absent. These files are what the
    agent loads at session start, so a write here changes real agent behaviour
    on its next run -- same contract as foundation.py's profile-file writer."""
    agent = await _get_agent_or_404(db, agent_id)
    host_home, path = _require_profile_file(agent, filename)
    try:
        path.write_text(payload.content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write {filename}: {e}",
        ) from e
    return AgentProfileFileOut(
        agent_id=agent.id,
        filename=filename,
        path=f"{host_home.rstrip('/')}/{filename}",
        content=payload.content,
    )


# ---------------------------------------------------------------------------
# MCP servers
#
# Each runtime keeps its MCP servers in its own file and format (see
# core/agent_mcp.py); these routes read and edit that file in place. There is
# deliberately no ForgeHub-side table: a copy would drift the moment someone
# ran `claude mcp add` in a terminal, and the runtime reads the file, not us.
# ---------------------------------------------------------------------------


def _require_mcp_target(agent: Agent) -> tuple[agent_mcp.McpConfigFormat, str]:
    """The MCP config format and host file path for an agent, or 400/404.

    An agent with no `runtime_type` is not an error in the registry (Kairos is
    registered without one), but it has no runtime that could load an MCP
    server -- so it gets an explicit 400 rather than an empty list that would
    read as "configured, none yet"."""
    fmt = agent_mcp.format_for(agent.runtime_type)
    if fmt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Agent {agent.name} has no runtime that loads MCP servers"
                + (f" (runtime_type={agent.runtime_type!r})." if agent.runtime_type else ".")
            ),
        )
    host_path = agent_mcp.config_host_path(agent.effective_home_path, fmt)
    if not host_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This agent has no home directory on file, so its MCP config "
                "cannot be located. Set 'Profile directory' on the agent page."
            ),
        )
    return fmt, host_path


@router.get("/{agent_id}/mcp-servers", response_model=AgentMcpServersOut)
async def list_agent_mcp_servers(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AgentMcpServersOut:
    """The MCP servers this agent's runtime will load on its next run.

    A config file that exists but cannot be parsed is reported through `error`
    with an empty server list, never as a 500: a hand-edited config with a
    syntax error is exactly the situation an operator opens this screen to
    diagnose, and a failing screen would hide it."""
    agent = await _get_agent_or_404(db, agent_id)
    fmt, host_path = _require_mcp_target(agent)
    resolved = agent_mcp.resolve_host_file(host_path)
    servers: list[AgentMcpServerOut] = []
    error: str | None = None
    if resolved is not None:
        try:
            servers = [
                AgentMcpServerOut(**info.__dict__)
                for info in agent_mcp.read_servers(host_path, fmt)
            ]
        except agent_mcp.McpConfigError as e:
            error = str(e)
    return AgentMcpServersOut(
        agent_id=agent.id,
        runtime_type=agent.runtime_type,
        config_path=host_path,
        config_exists=resolved is not None,
        supports_toggle=fmt.toggle_field is not None,
        error=error,
        servers=servers,
    )


@router.put("/{agent_id}/mcp-servers/{name}", response_model=AgentMcpServersOut)
async def upsert_agent_mcp_server(
    agent_id: uuid.UUID,
    name: str,
    payload: AgentMcpServerIn,
    db: AsyncSession = Depends(get_db),
) -> AgentMcpServersOut:
    """Add or update one MCP server in the runtime's own config file.

    This changes what the agent can do on its next run -- for the Hermes
    profiles and OpenClaw that also means their persistent gateway daemon
    keeps the old set until it is restarted, while a one-shot dispatch picks
    the change up immediately."""
    agent = await _get_agent_or_404(db, agent_id)
    fmt, host_path = _require_mcp_target(agent)
    if bool(payload.command) == bool(payload.url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either a command (stdio server) or a url (HTTP server), not both.",
        )
    if not payload.enabled and fmt.toggle_field is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The {agent.runtime_type} runtime has no enable/disable flag for MCP servers — "
                "remove the server instead."
            ),
        )
    server = agent_mcp.McpServerInfo(
        name=name,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        url=payload.url,
        enabled=payload.enabled,
    )
    try:
        agent_mcp.write_server(host_path, fmt, name, server)
    except agent_mcp.McpConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await list_agent_mcp_servers(agent_id, db)


@router.delete("/{agent_id}/mcp-servers/{name}", response_model=AgentMcpServersOut)
async def delete_agent_mcp_server(
    agent_id: uuid.UUID, name: str, db: AsyncSession = Depends(get_db)
) -> AgentMcpServersOut:
    """Remove one MCP server from the runtime's own config file."""
    agent = await _get_agent_or_404(db, agent_id)
    fmt, host_path = _require_mcp_target(agent)
    try:
        agent_mcp.write_server(host_path, fmt, name, None)
    except agent_mcp.McpConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await list_agent_mcp_servers(agent_id, db)


# ---------------------------------------------------------------------------
# Agent Service Credentials (Tokens for MCP and automated API access)
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/credentials",
    response_model=AgentServiceCredentialOut,
    status_code=status.HTTP_201_CREATED,
)
async def issue_agent_service_credential(
    agent_id: uuid.UUID,
    payload: AgentServiceCredentialCreateIn = AgentServiceCredentialCreateIn(),
    db: AsyncSession = Depends(get_db),
) -> AgentServiceCredentialOut:
    """Generate and issue a fresh, active Service Credential (agt_...) for an agent."""
    agent = await _get_agent_or_404(db, agent_id)
    raw_token = f"agt_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    credential = AgentServiceCredential(
        agent_id=agent.id,
        label=payload.label,
        token_hash=token_hash,
        expires_at=payload.expires_at,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)

    return AgentServiceCredentialOut(
        id=credential.id,
        agent_id=credential.agent_id,
        label=credential.label,
        token=raw_token,
        expires_at=credential.expires_at,
        created_at=credential.created_at,
    )


@router.get(
    "/{agent_id}/credentials",
    response_model=list[AgentServiceCredentialOut],
)
async def list_agent_service_credentials(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AgentServiceCredentialOut]:
    """List active service credentials for an agent (tokens themselves are not stored in plaintext)."""
    agent = await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(AgentServiceCredential)
        .where(
            AgentServiceCredential.agent_id == agent.id,
            AgentServiceCredential.revoked_at.is_(None),
        )
        .order_by(AgentServiceCredential.created_at.desc())
    )
    return [
        AgentServiceCredentialOut(
            id=c.id,
            agent_id=c.agent_id,
            label=c.label,
            token=None,
            expires_at=c.expires_at,
            created_at=c.created_at,
        )
        for c in result.scalars().all()
    ]


@router.delete(
    "/{agent_id}/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_agent_service_credential(
    agent_id: uuid.UUID,
    credential_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke an agent's service credential."""
    agent = await _get_agent_or_404(db, agent_id)
    credential = await db.get(AgentServiceCredential, credential_id)
    if not credential or credential.agent_id != agent.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    credential.revoked_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# Sub-agents (nested under an agent)
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/sub-agents",
    response_model=SubAgentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_sub_agent(
    agent_id: uuid.UUID, payload: SubAgentCreate, db: AsyncSession = Depends(get_db)
) -> SubAgent:
    await _get_agent_or_404(db, agent_id)

    data = payload.model_dump(exclude={"skill_ids"})
    sub_agent = SubAgent(agent_id=agent_id, **data)
    db.add(sub_agent)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sub-agent with this name already exists for this agent",
        ) from None

    # Explicit skill grants at creation time must obey the same
    # explicit-or-inherited boundary as the dedicated endpoint.
    for skill_id in payload.skill_ids:
        await _assert_skill_grantable_to_sub_agent(db, agent_id, skill_id)
        db.add(SubAgentSkill(sub_agent_id=sub_agent.id, skill_id=skill_id))

    await db.commit()
    await db.refresh(sub_agent)
    return sub_agent


@router.get("/{agent_id}/sub-agents", response_model=list[SubAgentOut])
async def list_sub_agents(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[SubAgent]:
    await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(SubAgent)
        .where(SubAgent.agent_id == agent_id)
        .order_by(SubAgent.created_at)
    )
    return list(result.scalars().all())


@router.get("/{agent_id}/sub-agents/{sub_agent_id}", response_model=SubAgentOut)
async def get_sub_agent(
    agent_id: uuid.UUID, sub_agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> SubAgent:
    return await _get_sub_agent_or_404(db, agent_id, sub_agent_id)


@router.patch("/{agent_id}/sub-agents/{sub_agent_id}", response_model=SubAgentOut)
async def update_sub_agent(
    agent_id: uuid.UUID,
    sub_agent_id: uuid.UUID,
    payload: SubAgentUpdate,
    db: AsyncSession = Depends(get_db),
) -> SubAgent:
    sub_agent = await _get_sub_agent_or_404(db, agent_id, sub_agent_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(sub_agent, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sub-agent with this name already exists for this agent",
        ) from None
    await db.refresh(sub_agent)
    return sub_agent


@router.delete(
    "/{agent_id}/sub-agents/{sub_agent_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_sub_agent(
    agent_id: uuid.UUID, sub_agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    sub_agent = await _get_sub_agent_or_404(db, agent_id, sub_agent_id)
    await db.delete(sub_agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Agent <-> Skill associations
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/skills",
    response_model=AgentSkillOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_agent_skill(
    agent_id: uuid.UUID, payload: AgentSkillCreate, db: AsyncSession = Depends(get_db)
) -> AgentSkill:
    await _get_agent_or_404(db, agent_id)
    await _get_skill_or_404(db, payload.skill_id)

    agent_skill = AgentSkill(agent_id=agent_id, **payload.model_dump())
    db.add(agent_skill)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This skill is already granted to this agent",
        ) from None
    await db.refresh(agent_skill)
    return agent_skill


@router.get("/{agent_id}/skills", response_model=list[AgentSkillOut])
async def list_agent_skills(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[AgentSkill]:
    await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id)
    )
    return list(result.scalars().all())


@router.delete(
    "/{agent_id}/skills/{agent_skill_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_agent_skill(
    agent_id: uuid.UUID, agent_skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    agent_skill = await db.get(AgentSkill, agent_skill_id)
    if agent_skill is None or agent_skill.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent skill grant not found"
        )
    await db.delete(agent_skill)
    await db.commit()


# ---------------------------------------------------------------------------
# Sub-agent <-> Skill associations
# ---------------------------------------------------------------------------


async def _assert_skill_grantable_to_sub_agent(
    db: AsyncSession, agent_id: uuid.UUID, skill_id: uuid.UUID
) -> None:
    """SPEC 6.5 rule 7: a sub-agent may only use a skill that is either
    explicitly granted to it, or inherited from its parent agent's
    agent_skills grant when that grant has inheritable=True. Since this
    function is only ever called right before creating the explicit
    grant, it really validates that the *parent agent* itself has access
    to the skill at all (explicit grant on the agent) -- a sub-agent
    cannot be given a skill its parent agent does not also hold.
    """
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Skill is not granted to the parent agent; a sub-agent cannot "
                "hold a skill its parent agent does not also hold"
            ),
        )


@router.post(
    "/{agent_id}/sub-agents/{sub_agent_id}/skills",
    response_model=SubAgentSkillOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_sub_agent_skill(
    agent_id: uuid.UUID,
    sub_agent_id: uuid.UUID,
    payload: SubAgentSkillCreate,
    db: AsyncSession = Depends(get_db),
) -> SubAgentSkill:
    await _get_sub_agent_or_404(db, agent_id, sub_agent_id)
    await _get_skill_or_404(db, payload.skill_id)
    await _assert_skill_grantable_to_sub_agent(db, agent_id, payload.skill_id)

    sub_agent_skill = SubAgentSkill(sub_agent_id=sub_agent_id, skill_id=payload.skill_id)
    db.add(sub_agent_skill)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This skill is already granted to this sub-agent",
        ) from None
    await db.refresh(sub_agent_skill)
    return sub_agent_skill


@router.get(
    "/{agent_id}/sub-agents/{sub_agent_id}/skills",
    response_model=list[SubAgentSkillOut],
)
async def list_sub_agent_skills(
    agent_id: uuid.UUID, sub_agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[SubAgentSkill]:
    await _get_sub_agent_or_404(db, agent_id, sub_agent_id)
    result = await db.execute(
        select(SubAgentSkill).where(SubAgentSkill.sub_agent_id == sub_agent_id)
    )
    return list(result.scalars().all())


@router.delete(
    "/{agent_id}/sub-agents/{sub_agent_id}/skills/{sub_agent_skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_sub_agent_skill(
    agent_id: uuid.UUID,
    sub_agent_id: uuid.UUID,
    sub_agent_skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    sub_agent_skill = await db.get(SubAgentSkill, sub_agent_skill_id)
    if sub_agent_skill is None or sub_agent_skill.sub_agent_id != sub_agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sub-agent skill grant not found",
        )
    await db.delete(sub_agent_skill)
    await db.commit()


# ---------------------------------------------------------------------------
# Agent cost rates (nested under an agent)
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/cost-rates",
    response_model=AgentCostRateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_cost_rate(
    agent_id: uuid.UUID, payload: AgentCostRateCreate, db: AsyncSession = Depends(get_db)
) -> AgentCostRate:
    await _get_agent_or_404(db, agent_id)
    cost_rate = AgentCostRate(agent_id=agent_id, **payload.model_dump())
    db.add(cost_rate)
    await db.commit()
    await db.refresh(cost_rate)
    return cost_rate


@router.get("/{agent_id}/cost-rates", response_model=list[AgentCostRateOut])
async def list_agent_cost_rates(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[AgentCostRate]:
    await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(AgentCostRate).where(AgentCostRate.agent_id == agent_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Agent capacities (nested under an agent, one row per agent)
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_id}/capacity",
    response_model=AgentCapacityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_capacity(
    agent_id: uuid.UUID, payload: AgentCapacityCreate, db: AsyncSession = Depends(get_db)
) -> AgentCapacity:
    await _get_agent_or_404(db, agent_id)
    capacity = AgentCapacity(agent_id=agent_id, **payload.model_dump())
    db.add(capacity)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capacity already defined for this agent; use PATCH to update it",
        ) from None
    await db.refresh(capacity)
    return capacity


@router.get("/{agent_id}/capacity", response_model=AgentCapacityOut)
async def get_agent_capacity(
    agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> AgentCapacity:
    await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(AgentCapacity).where(AgentCapacity.agent_id == agent_id)
    )
    capacity = result.scalar_one_or_none()
    if capacity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capacity not set for this agent"
        )
    return capacity


@router.patch("/{agent_id}/capacity", response_model=AgentCapacityOut)
async def update_agent_capacity(
    agent_id: uuid.UUID, payload: AgentCapacityUpdate, db: AsyncSession = Depends(get_db)
) -> AgentCapacity:
    await _get_agent_or_404(db, agent_id)
    result = await db.execute(
        select(AgentCapacity).where(AgentCapacity.agent_id == agent_id)
    )
    capacity = result.scalar_one_or_none()
    if capacity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capacity not set for this agent"
        )
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(capacity, field, value)
    await db.commit()
    await db.refresh(capacity)
    return capacity
