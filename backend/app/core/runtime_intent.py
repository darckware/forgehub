"""Resolve runtime skill descriptors from canonical requirements and live grants."""
from sqlalchemy import select

from app.api.schemas.runtime_intent import RuntimeIntent
from app.db.models.agent import AgentSkill, Skill, SubAgent, SubAgentSkill
from app.db.models.task import TaskRequiredSkill


async def resolve_runtime_intent(db, task_id, agent_id, requested=None, *, sub_agent_id=None):
    intent = RuntimeIntent.model_validate(requested or {})
    descriptors = {s.name: s.model_dump() for s in intent.skills}
    rows = (await db.execute(select(Skill, TaskRequiredSkill.is_mandatory).join(
        TaskRequiredSkill, TaskRequiredSkill.skill_id == Skill.id
    ).where(TaskRequiredSkill.task_id == task_id).order_by(Skill.name, Skill.version))).all()
    mandatory_versions = {}
    for skill, mandatory in rows:
        if mandatory:
            prior = mandatory_versions.get(skill.name)
            if prior is not None and prior != skill.version:
                raise ValueError(f"Conflicting mandatory versions for runtime skill {skill.name}")
            mandatory_versions[skill.name] = skill.version
        if mandatory or skill.name not in descriptors:
            descriptors[skill.name] = {'name': skill.name, 'version': skill.version, 'required': mandatory}
    if sub_agent_id is not None:
        sub_agent = await db.get(SubAgent, sub_agent_id)
        if sub_agent is None or sub_agent.agent_id != agent_id:
            raise ValueError('Sub-agent skill owner does not match the assigned runtime')
        explicit = select(SubAgentSkill.skill_id).join(
            Skill, Skill.id == SubAgentSkill.skill_id).where(
                SubAgentSkill.sub_agent_id == sub_agent_id, Skill.is_approved.is_(True))
        inherited = select(AgentSkill.skill_id).join(
            Skill, Skill.id == AgentSkill.skill_id).where(
                AgentSkill.agent_id == agent_id, AgentSkill.inheritable.is_(True),
                Skill.is_approved.is_(True))
        grants = set((await db.scalars(explicit)).all()) | set((await db.scalars(inherited)).all())
    else:
        grants = set((await db.scalars(select(AgentSkill.skill_id).where(
            AgentSkill.agent_id == agent_id))).all())
    granted_descriptors = []
    for descriptor in descriptors.values():
        skill = await db.scalar(select(Skill).where(Skill.name == descriptor['name'], Skill.version == descriptor['version']))
        if not skill or not skill.is_approved or skill.id not in grants:
            if descriptor['required']:
                raise ValueError(f"Mandatory runtime skill {descriptor['name']} is not approved and granted")
            continue
        granted_descriptors.append(descriptor)
    return RuntimeIntent.model_validate({**intent.model_dump(), 'skills': granted_descriptors}).model_dump()
