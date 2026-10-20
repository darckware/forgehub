"""Read-only catalog consumed by Aegis's prompt-improvement selector.

The trusted ``instruction_template`` deliberately stays server-side.  The UI
needs the explanatory metadata, compatibility rules and stable code, but must
not become the source of truth for instructions sent to an agent.
"""
import unicodedata

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.prompt_technique import (
    PromptTechniqueOut,
    PromptTechniqueRecommendationOut,
    PromptTechniqueRecommendRequest,
)
from app.db.base import get_db
from app.db.models.prompt_technique import (
    PROMPT_TECHNIQUE_CATEGORIES,
    PROMPT_TECHNIQUE_SELECTION_MODES,
    PromptTechnique,
)

router = APIRouter(prefix="/api/v1/prompt-techniques", tags=["prompt-techniques"])


def _searchable(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    stop_words = {"a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da"}
    return " ".join(word for word in plain.split() if word not in stop_words)


@router.get("", response_model=list[PromptTechniqueOut])
async def list_prompt_techniques(
    category: str | None = Query(default=None),
    selection_mode: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[PromptTechnique]:
    """Return the ordered catalog, optionally narrowed for one selector."""
    query = select(PromptTechnique)
    if category is not None:
        if category not in PROMPT_TECHNIQUE_CATEGORIES:
            return []
        query = query.where(PromptTechnique.category == category)
    if selection_mode is not None:
        if selection_mode not in PROMPT_TECHNIQUE_SELECTION_MODES:
            return []
        query = query.where(
            PromptTechnique.selection_mode.in_((selection_mode, "both"))
            if selection_mode != "both"
            else PromptTechnique.selection_mode == "both"
        )
    if not include_inactive:
        query = query.where(PromptTechnique.is_active.is_(True))
    return list(
        (
            await db.execute(
                query.order_by(PromptTechnique.category, PromptTechnique.sort_order, PromptTechnique.name)
            )
        ).scalars().all()
    )


@router.post("/recommend", response_model=list[PromptTechniqueRecommendationOut])
async def recommend_prompt_techniques(
    payload: PromptTechniqueRecommendRequest,
    db: AsyncSession = Depends(get_db),
) -> list[PromptTechniqueRecommendationOut]:
    """Rank techniques from catalog-owned context terms.

    This is deterministic and cheap enough to run while drafting. It never
    sends the user's text to an LLM merely to populate a selector.
    """
    draft = _searchable(payload.draft)
    rows = list(
        (
            await db.execute(select(PromptTechnique).where(PromptTechnique.is_active.is_(True)))
        ).scalars().all()
    )
    ranked: list[PromptTechniqueRecommendationOut] = []
    for technique in rows:
        matched = [term for term in technique.match_terms if _searchable(term) in draft]
        if matched:
            ranked.append(PromptTechniqueRecommendationOut(
                technique_code=technique.code,
                score=sum(max(1, len(term.split())) for term in matched),
                matched_terms=matched,
            ))
    ranked.sort(key=lambda item: (-item.score, item.technique_code))
    if ranked:
        return ranked[:5]
    fallback = "structured_prompt" if len(payload.draft.split()) >= 20 else "clarity_objectivity"
    return [PromptTechniqueRecommendationOut(
        technique_code=fallback,
        score=0,
        matched_terms=[],
    )]
