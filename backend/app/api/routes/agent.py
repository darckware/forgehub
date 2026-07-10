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
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
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
    AgentOut,
    AgentSkillCreate,
    AgentSkillOut,
    AgentUpdate,
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
from app.core import hermes_sync
from app.db.base import get_db
from app.db.models.agent import (
    Agent,
    AgentCapacity,
    AgentCostRate,
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
    agent = Agent(**payload.model_dump())
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

    The roster is sourced from the real, provisioned profile directories
    under /root/.hermes/profiles/ (`hermes_sync.list_provisioned_profiles`)
    -- NOT from the registry docs (ECOSYSTEM_AGENTS.md etc.), which can
    list agents that are only planned/documented and not actually
    provisioned (e.g. `forgenet`), or go stale. A registry entry is used
    only to enrich a provisioned profile's metadata (name, layer, role,
    telegram, runtime tier) when one exists; a profile with no matching
    entry is still registered, just without that metadata.
    """
    warnings: list[str] = []
    agents_created = agents_updated = 0
    sub_agents_created = sub_agents_updated = 0
    skills_created = skills_updated = 0
    agent_skills_created = 0

    # 1. Agent roster.
    registry_by_slug = {e["profile_slug"]: e for e in hermes_sync.parse_agent_registry()}
    agent_by_slug: dict[str, Agent] = {}
    for slug in hermes_sync.list_provisioned_profiles():
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
            )
            db.add(agent)
            agents_created += 1
        else:
            # Only refresh the registry-mirrored fields when this run actually
            # found registry data for the slug -- a transient/empty read of
            # ECOSYSTEM_AGENTS.md must never wipe an existing agent's real
            # layer/runtime_tier/telegram_required back to defaults.
            if has_registry_entry:
                agent.layer = entry["layer"]
                agent.runtime_tier = entry["runtime_tier"]
                agent.telegram_required = entry["telegram_required"]
            agent.has_profile = True
            agent.mission = mission
            agent.source_path = source_path
            agents_updated += 1
        await db.flush()
        agent_by_slug[slug] = agent

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
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Agent:
    return await _get_agent_detail_or_404(db, agent_id)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID, payload: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> Agent:
    agent = await _get_agent_or_404(db, agent_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(agent, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An agent with this name already exists",
        ) from None
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    agent = await _get_agent_or_404(db, agent_id)
    await db.delete(agent)
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
