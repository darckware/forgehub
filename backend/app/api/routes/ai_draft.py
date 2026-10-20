"""Cross-phase "Gerar via IA" draft endpoint.

One SSE route shared by all 5 Software Factory phases -- see
core/ai_draft.py's module docstring for the governance boundary this
follows (agent proposes, human applies through each domain's own existing
endpoints). This router owns no table: `subject_id` optionally loads
existing state from another domain's models read-only (e.g. a
ProductConcept for target_kind="review"), never writes anything.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.chat import _call_bridge_text, _get_chattable_agent_or_404
from app.api.schemas.ai_draft import AiDraftRequest, AiDraftTargetKind
from app.core.ai_draft import build_ai_draft_prompt, get_prompt_instructions, parse_ai_draft_reply
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.db.base import get_db
from app.db.models.system_scope import ProductConcept, ProductConceptRevision, TechStackOption


router = APIRouter(prefix="/api/v1/ai-draft", tags=["ai-draft"])


@router.get("/prompt-template")
async def get_ai_draft_prompt_template(target_kind: AiDraftTargetKind) -> dict:
    """Read-only preview of the instructions build_ai_draft_prompt embeds
    for this target_kind -- backs the "Copiar prompt" button so a human can
    see/copy exactly what the agent is told to expect from the context,
    without having to actually fire a generation."""
    return {"target_kind": target_kind, "instructions": get_prompt_instructions(target_kind)}


async def _load_tech_stack_catalog_context(db: AsyncSession) -> str | None:
    """The current `tech_stack_options` catalog (org_standard + custom rows),
    grouped by layer -- fed to target_kind="tech_stack" as <estado_atual> so
    the agent reuses an existing option's exact name instead of paraphrasing
    the same tool (see core/ai_draft.py's "tech_stack" instructions). Not
    subject_id-scoped: the catalog isn't tied to one concept."""
    result = await db.execute(select(TechStackOption).order_by(TechStackOption.layer, TechStackOption.name))
    options = result.scalars().all()
    if not options:
        return None
    by_layer: dict[str, list[TechStackOption]] = {}
    for option in options:
        by_layer.setdefault(option.layer, []).append(option)
    lines = ["Catálogo atual de tecnologias aprovadas (por camada):"]
    for layer, layer_options in by_layer.items():
        lines.append(f"- {layer}:")
        for option in layer_options:
            suffix = f" -- {option.description}" if option.description else ""
            lines.append(f"  - {option.name}{suffix}")
    return "\n".join(lines)


async def _load_subject_context(db: AsyncSession, target_kind: str, subject_id: uuid.UUID | None) -> str | None:
    """Only target_kind="review" resolves subject_id -- it's the one draft
    kind meant to critique real, already-recorded state rather than a
    context blob the human just typed. subject_id is a ProductConcept id
    there. target_kind="tech_stack" always loads the current catalog (see
    _load_tech_stack_catalog_context), regardless of subject_id. Other kinds
    ignore subject_id for now; extend here as more phases wire in their own
    review subject."""
    if target_kind == "tech_stack":
        return await _load_tech_stack_catalog_context(db)
    if target_kind != "review" or subject_id is None:
        return None
    concept = await db.get(ProductConcept, subject_id)
    if concept is None or concept.current_revision_id is None:
        return None
    revision = await db.get(ProductConceptRevision, concept.current_revision_id)
    if revision is None:
        return None
    lines = [f"Status da concepção: {concept.status}"]
    if revision.problem_statement:
        lines.append(f"Problem statement: {revision.problem_statement}")
    if revision.vision:
        lines.append(f"Vision: {revision.vision}")
    if revision.scope_summary:
        lines.append(f"Scope: {revision.scope_summary}")
    if revision.project_description:
        lines.append(f"Project description: {revision.project_description}")
    if revision.tech_stack_decisions:
        lines.append(f"Tech stack: {json.dumps(revision.tech_stack_decisions, ensure_ascii=False)}")
    return "\n".join(lines)


@router.post("/stream")
async def stream_ai_draft(
    payload: AiDraftRequest, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> StreamingResponse:
    """Same SSE shape as chat.py's stream_improve_prompt: `: ping` keepalive
    comments while the bridge call is in flight (a single non-streaming call
    can take up to ~650s), then either `data: {"draft": {...}}` (already
    parsed/validated against target_kind's schema) or `event: error`, always
    closed by `event: done`. Nothing is persisted by this call."""
    await authorize_action(db, principal, "planning.ai_draft.generate")
    agent = await _get_chattable_agent_or_404(db, payload.agent_id)
    subject_context = await _load_subject_context(db, payload.target_kind, payload.subject_id)
    prompt = build_ai_draft_prompt(
        target_kind=payload.target_kind, context=payload.context,
        extra_instruction=payload.extra_instruction, subject_context=subject_context,
    )

    async def _events():
        try:
            task = asyncio.ensure_future(_call_bridge_text(agent.profile_slug, prompt, None))
            while True:
                done, _pending = await asyncio.wait([task], timeout=15)
                if done:
                    break
                yield ": ping\n\n"
            bridge_result = await task
            reply = (bridge_result.get("reply") or "").strip()
            draft = parse_ai_draft_reply(reply, payload.target_kind)
            yield f"data: {json.dumps({'draft': draft})}\n\n"
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield f"event: error\ndata: {json.dumps({'detail': str(detail)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")
