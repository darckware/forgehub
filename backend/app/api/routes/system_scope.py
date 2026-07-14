"""Planning APIs for conception, System Blueprint, and Project Scope."""
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.system_scope import (
    BlueprintDetailOut,
    BlueprintGraphOut,
    BlueprintRevisionCreate,
    BlueprintRevisionOut,
    BlueprintValidationOut,
    ConceptDecision,
    ConceptDetailOut,
    ConceptRevisionCreate,
    DeliveryPlanningAuthorizationOut,
    DevelopmentRequestOut,
    IdeaCreate,
    IdeaCreatedOut,
    ProjectScopeCreate,
    ProjectScopeItemCreate,
    ProjectScopeItemOut,
    ProjectScopeOut,
    SystemElementCreate,
    SystemElementRelationCreate,
    SystemElementRelationOut,
    ValidationIssue,
    AuthorizeDeliveryPlanning,
    AcceptanceCriterionOut,
    ElementRevisionOut,
    ElementWithRevisionOut,
    SystemElementOut,
)
from app.db.base import get_db
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.governed_approval import approved_concept_request, canonical_hash, request_concept_approval
from app.db.models.governance import AuditEvent
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import (
    BLUEPRINT_REVISION_STATUSES,
    ELEMENT_FAMILIES,
    ELEMENT_TYPES,
    RELATION_TYPES,
    DevelopmentRequest,
    ProductConcept,
    ProductConceptRevision,
    ProjectScope,
    ProjectScopeItem,
    ScopeItemAcceptanceCriterion,
    SystemBlueprint,
    SystemBlueprintRevision,
    SystemElement,
    SystemElementRelation,
    SystemElementRevision,
)

router = APIRouter(prefix="/api/v1", tags=["planning-scope"])

FAMILY_TYPES = {
    "business": {"capability", "module", "persona"},
    "process": {"journey", "process", "process_step", "use_case"},
    "experience": {"application", "channel", "route", "screen", "form", "report", "ui_component"},
    "interface": {"api", "endpoint", "command", "query", "event", "webhook", "integration"},
    "domain": {"domain_entity", "value_object", "business_rule", "authorization_rule"},
    "application": {"service", "handler", "class", "method", "workflow", "job"},
    "data": {"datastore", "schema", "table", "field", "index", "view", "procedure", "migration"},
    "runtime": {"runtime_component", "queue", "cache", "deployment_unit", "environment_target"},
    "assurance": {"test_scenario", "metric", "log_signal", "alert", "slo", "health_check"},
}


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _audit(entity_type: str, entity_id: uuid.UUID, event_type: str, actor: str | None, payload=None):
    return AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor=actor or "system",
        payload=payload,
    )


async def _concept(db: AsyncSession, concept_id: uuid.UUID) -> ProductConcept:
    row = await db.get(ProductConcept, concept_id)
    if row is None:
        raise HTTPException(404, "Product concept not found")
    return row


async def _blueprint_revision(db: AsyncSession, revision_id: uuid.UUID) -> SystemBlueprintRevision:
    row = await db.get(SystemBlueprintRevision, revision_id)
    if row is None:
        raise HTTPException(404, "Blueprint revision not found")
    return row


async def _draft_blueprint_revision(db: AsyncSession, revision_id: uuid.UUID) -> SystemBlueprintRevision:
    row = await _blueprint_revision(db, revision_id)
    if row.status != "draft":
        raise HTTPException(409, "Only a draft blueprint revision can be changed")
    return row


async def _graph(db: AsyncSession, revision: SystemBlueprintRevision) -> BlueprintGraphOut:
    element_revisions = list((await db.execute(
        select(SystemElementRevision)
        .where(SystemElementRevision.blueprint_revision_id == revision.id)
        .order_by(SystemElementRevision.created_at)
    )).scalars())
    elements = []
    for element_revision in element_revisions:
        element = await db.get(SystemElement, element_revision.system_element_id)
        if element is not None:
            elements.append(ElementWithRevisionOut(
                element=SystemElementOut.model_validate(element),
                revision=ElementRevisionOut.model_validate(element_revision),
            ))
    relations = list((await db.execute(
        select(SystemElementRelation)
        .where(SystemElementRelation.blueprint_revision_id == revision.id)
        .order_by(SystemElementRelation.created_at)
    )).scalars())
    return BlueprintGraphOut(
        revision=BlueprintRevisionOut.model_validate(revision),
        elements=elements,
        relations=[SystemElementRelationOut.model_validate(item) for item in relations],
    )


def _has_cycle(edges: list[tuple[uuid.UUID, uuid.UUID]]) -> bool:
    graph: dict[uuid.UUID, list[uuid.UUID]] = {}
    for source, target in edges:
        graph.setdefault(source, []).append(target)
    visiting: set[uuid.UUID] = set()
    visited: set[uuid.UUID] = set()

    def visit(node: uuid.UUID) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


async def _validate_blueprint(db: AsyncSession, revision: SystemBlueprintRevision) -> BlueprintValidationOut:
    graph = await _graph(db, revision)
    issues: list[ValidationIssue] = []
    if not graph.elements:
        issues.append(ValidationIssue(severity="error", code="empty_blueprint", message="Add at least one system element"))
    element_ids = {item.element.id for item in graph.elements}
    families = {item.element.family for item in graph.elements}
    for item in graph.elements:
        if item.element.element_type not in FAMILY_TYPES.get(item.element.family, set()):
            issues.append(ValidationIssue(
                severity="error", code="family_type_mismatch",
                message=f"{item.element.element_type} does not belong to {item.element.family}",
                element_id=item.element.id,
            ))
        if item.element.parent_id and item.element.parent_id not in element_ids:
            issues.append(ValidationIssue(
                severity="error", code="missing_parent",
                message="The parent is not present in this blueprint revision", element_id=item.element.id,
            ))
    for relation in graph.relations:
        if relation.from_element_id not in element_ids or relation.to_element_id not in element_ids:
            issues.append(ValidationIssue(
                severity="error", code="dangling_relation", message="A relation references an absent element"
            ))
    for relation_type in ("contains", "precedes"):
        edges = [(r.from_element_id, r.to_element_id) for r in graph.relations if r.relation_type == relation_type]
        if _has_cycle(edges):
            issues.append(ValidationIssue(
                severity="error", code=f"cyclic_{relation_type}", message=f"{relation_type} relations cannot form a cycle"
            ))
    expected = {"business", "process", "experience", "interface", "domain", "application", "data", "runtime", "assurance"}
    for family in sorted(expected - families):
        issues.append(ValidationIssue(
            severity="warning", code="uncovered_family", message=f"No {family} element has been mapped"
        ))
    return BlueprintValidationOut(valid=not any(i.severity == "error" for i in issues), issues=issues)


@router.post("/conception/ideas", response_model=IdeaCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_idea(
    payload: IdeaCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "planning.concept.edit")
    actor = principal.display_name
    product = Product(name=payload.name, description=payload.scope_summary or payload.problem_statement, status="concept")
    db.add(product)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A product with this name already exists") from None
    request = DevelopmentRequest(
        product_id=product.id, request_type="new_product", title=payload.name,
        description=payload.problem_statement, requested_by=actor,
        priority=payload.priority, status="accepted",
    )
    concept = ProductConcept(product_id=product.id, created_by=actor)
    blueprint = SystemBlueprint(product_id=product.id, name=f"{payload.name} System Map")
    db.add_all([request, concept, blueprint])
    await db.flush()
    revision = ProductConceptRevision(
        concept_id=concept.id, revision=1, problem_statement=payload.problem_statement,
        vision=payload.vision, scope_summary=payload.scope_summary,
        content_hash=_hash(payload.model_dump(exclude={"requested_by"}) | {"created_by": actor}), created_by=actor,
    )
    db.add(revision)
    await db.flush()
    blueprint_revision = SystemBlueprintRevision(
        blueprint_id=blueprint.id, revision=1, concept_revision_id=revision.id,
        created_by=actor,
    )
    db.add(blueprint_revision)
    await db.flush()
    concept.current_revision_id = revision.id
    blueprint.current_revision_id = blueprint_revision.id
    db.add(_audit("product_concept", concept.id, "created", actor, {"product_id": str(product.id), "principal_id": str(principal.principal_id)}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A product with this name already exists") from None
    for row in (request, concept, revision, blueprint, blueprint_revision):
        await db.refresh(row)
    return IdeaCreatedOut(
        product_id=product.id, request=request, concept=concept, concept_revision=revision,
        blueprint=blueprint, blueprint_revision=blueprint_revision,
    )


@router.get("/conception/requests", response_model=list[DevelopmentRequestOut])
async def list_development_requests(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DevelopmentRequest).order_by(DevelopmentRequest.created_at.desc()))
    return list(result.scalars())


@router.get("/products/{product_id}/concept", response_model=ConceptDetailOut)
async def get_product_concept(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    concept = (await db.execute(select(ProductConcept).where(ProductConcept.product_id == product_id))).scalar_one_or_none()
    if concept is None:
        raise HTTPException(404, "Product concept not found")
    revisions = list((await db.execute(
        select(ProductConceptRevision).where(ProductConceptRevision.concept_id == concept.id)
        .order_by(ProductConceptRevision.revision.desc())
    )).scalars())
    current = next((item for item in revisions if item.id == concept.current_revision_id), None)
    return ConceptDetailOut(concept=concept, current_revision=current, revisions=revisions)


@router.post("/product-concepts/{concept_id}/revisions", response_model=ConceptDetailOut)
async def revise_concept(
    concept_id: uuid.UUID, payload: ConceptRevisionCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    concept = await _concept(db, concept_id)
    await authorize_action(db, principal, "planning.concept.edit", product_id=concept.product_id)
    if concept.status not in {"draft", "rework"}:
        raise HTTPException(409, "Only draft or rework concepts can be revised")
    number = (await db.scalar(select(func.max(ProductConceptRevision.revision)).where(
        ProductConceptRevision.concept_id == concept.id
    )) or 0) + 1
    data = payload.model_dump(exclude={"created_by"})
    revision = ProductConceptRevision(
        concept_id=concept.id, revision=number, content_hash=_hash(data),
        created_by=principal.display_name, **data,
    )
    concept.current_revision_id = revision.id
    concept.status = "draft"
    db.add(revision)
    db.add(_audit("product_concept", concept.id, "revised", principal.display_name, {"revision": number}))
    await db.commit()
    return await get_product_concept(concept.product_id, db)


@router.post("/product-concepts/{concept_id}:submit", response_model=ConceptDetailOut)
async def submit_concept(
    concept_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    concept = await _concept(db, concept_id)
    blueprint = (await db.execute(select(SystemBlueprint).where(SystemBlueprint.product_id == concept.product_id))).scalar_one_or_none()
    if concept.status not in {"draft", "rework"} or not concept.current_revision_id or not blueprint or not blueprint.current_revision_id:
        raise HTTPException(409, "Concept and System Map must have current revisions")
    blueprint_revision = await _blueprint_revision(db, blueprint.current_revision_id)
    validation = await _validate_blueprint(db, blueprint_revision)
    if not validation.valid:
        raise HTTPException(422, {"message": "System Map validation failed", "issues": [i.model_dump(mode="json") for i in validation.issues]})
    graph = await _graph(db, blueprint_revision)
    blueprint_revision.content_hash = canonical_hash(graph.model_dump(mode="json"))
    concept_revision = await db.get(ProductConceptRevision, concept.current_revision_id)
    target_hash = canonical_hash({
        "concept_revision_id": str(concept_revision.id), "concept_hash": concept_revision.content_hash,
        "blueprint_revision_id": str(blueprint_revision.id), "blueprint_hash": blueprint_revision.content_hash,
    })
    concept.status = "in_review"
    blueprint_revision.status = "in_review"
    await request_concept_approval(db, principal, concept, target_hash)
    db.add(_audit("product_concept", concept.id, "submitted", principal.display_name, {"target_hash": target_hash}))
    await db.commit()
    return await get_product_concept(concept.product_id, db)


@router.post("/product-concepts/{concept_id}:decide", response_model=ConceptDetailOut)
async def decide_concept(concept_id: uuid.UUID, payload: ConceptDecision, db: AsyncSession = Depends(get_db)):
    raise HTTPException(409, "Direct decisions are disabled; use /api/v1/governed/approval-requests/{id}:decide")


@router.get("/products/{product_id}/system-blueprint", response_model=BlueprintDetailOut)
async def get_system_blueprint(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    blueprint = (await db.execute(select(SystemBlueprint).where(SystemBlueprint.product_id == product_id))).scalar_one_or_none()
    if blueprint is None:
        raise HTTPException(404, "System Map not found")
    revisions = list((await db.execute(
        select(SystemBlueprintRevision).where(SystemBlueprintRevision.blueprint_id == blueprint.id)
        .order_by(SystemBlueprintRevision.revision.desc())
    )).scalars())
    current = next((item for item in revisions if item.id == blueprint.current_revision_id), None)
    return BlueprintDetailOut(blueprint=blueprint, current_revision=current, revisions=revisions)


@router.post("/products/{product_id}/system-blueprint/revisions", response_model=BlueprintRevisionOut)
async def create_blueprint_revision(
    product_id: uuid.UUID, payload: BlueprintRevisionCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await authorize_action(db, principal, "planning.blueprint.edit", product_id=product_id)
    blueprint = (await db.execute(select(SystemBlueprint).where(SystemBlueprint.product_id == product_id))).scalar_one_or_none()
    if blueprint is None:
        raise HTTPException(404, "System Map not found")
    number = (await db.scalar(select(func.max(SystemBlueprintRevision.revision)).where(
        SystemBlueprintRevision.blueprint_id == blueprint.id
    )) or 0) + 1
    concept = (await db.execute(select(ProductConcept).where(ProductConcept.product_id == product_id))).scalar_one_or_none()
    revision = SystemBlueprintRevision(
        blueprint_id=blueprint.id, revision=number,
        concept_revision_id=concept.current_revision_id if concept else None, created_by=principal.display_name,
    )
    db.add(revision)
    await db.flush()
    source_id = payload.clone_from_revision_id or blueprint.current_revision_id
    if source_id:
        source = await _blueprint_revision(db, source_id)
        if source.blueprint_id != blueprint.id:
            raise HTTPException(422, "Clone source belongs to another System Map")
        source_elements = list((await db.execute(select(SystemElementRevision).where(
            SystemElementRevision.blueprint_revision_id == source.id
        ))).scalars())
        source_relations = list((await db.execute(select(SystemElementRelation).where(
            SystemElementRelation.blueprint_revision_id == source.id
        ))).scalars())
        db.add_all([SystemElementRevision(
            system_element_id=item.system_element_id, blueprint_revision_id=revision.id,
            spec_snapshot=item.spec_snapshot, source_ref=item.source_ref,
            content_hash=item.content_hash, status="draft",
        ) for item in source_elements])
        db.add_all([SystemElementRelation(
            blueprint_revision_id=revision.id, from_element_id=item.from_element_id,
            to_element_id=item.to_element_id, relation_type=item.relation_type, attributes=item.attributes,
        ) for item in source_relations])
    blueprint.current_revision_id = revision.id
    await db.commit()
    await db.refresh(revision)
    return revision


@router.get("/blueprint-revisions/{revision_id}/graph", response_model=BlueprintGraphOut)
async def get_blueprint_graph(revision_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _graph(db, await _blueprint_revision(db, revision_id))


@router.post("/blueprint-revisions/{revision_id}/elements", response_model=ElementWithRevisionOut, status_code=201)
async def add_system_element(
    revision_id: uuid.UUID, payload: SystemElementCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    revision = await _draft_blueprint_revision(db, revision_id)
    blueprint = await db.get(SystemBlueprint, revision.blueprint_id)
    await authorize_action(db, principal, "planning.blueprint.edit", product_id=blueprint.product_id)
    if payload.family not in ELEMENT_FAMILIES or payload.element_type not in ELEMENT_TYPES:
        raise HTTPException(422, "Unknown family or element type")
    if payload.element_type not in FAMILY_TYPES[payload.family]:
        raise HTTPException(422, f"{payload.element_type} does not belong to {payload.family}")
    if payload.parent_id:
        parent = await db.get(SystemElement, payload.parent_id)
        if not parent or parent.product_id != blueprint.product_id:
            raise HTTPException(422, "Parent must belong to the same product")
    element_data = payload.model_dump(exclude={"spec_snapshot", "source_ref"})
    element = SystemElement(product_id=blueprint.product_id, **element_data)
    db.add(element)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "The stable key already exists for this product") from None
    element_revision = SystemElementRevision(
        system_element_id=element.id, blueprint_revision_id=revision.id,
        spec_snapshot=payload.spec_snapshot, source_ref=payload.source_ref,
        content_hash=_hash(payload.spec_snapshot),
    )
    db.add(element_revision)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "The stable key already exists for this product") from None
    await db.refresh(element)
    await db.refresh(element_revision)
    return ElementWithRevisionOut(element=element, revision=element_revision)


@router.post("/blueprint-revisions/{revision_id}/relations", response_model=SystemElementRelationOut, status_code=201)
async def add_system_relation(
    revision_id: uuid.UUID, payload: SystemElementRelationCreate, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    await _draft_blueprint_revision(db, revision_id)
    revision = await _blueprint_revision(db, revision_id)
    blueprint = await db.get(SystemBlueprint, revision.blueprint_id)
    await authorize_action(db, principal, "planning.blueprint.edit", product_id=blueprint.product_id)
    if payload.relation_type not in RELATION_TYPES or payload.from_element_id == payload.to_element_id:
        raise HTTPException(422, "Invalid relation")
    revision_ids = set((await db.execute(select(SystemElementRevision.system_element_id).where(
        SystemElementRevision.blueprint_revision_id == revision_id,
        SystemElementRevision.system_element_id.in_([payload.from_element_id, payload.to_element_id]),
    ))).scalars())
    if revision_ids != {payload.from_element_id, payload.to_element_id}:
        raise HTTPException(422, "Both elements must be present in the blueprint revision")
    relation = SystemElementRelation(blueprint_revision_id=revision_id, **payload.model_dump())
    db.add(relation)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "This relation already exists") from None
    await db.refresh(relation)
    return relation


@router.delete("/blueprint-revisions/{revision_id}/relations/{relation_id}", status_code=204)
async def delete_system_relation(revision_id: uuid.UUID, relation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _draft_blueprint_revision(db, revision_id)
    relation = await db.get(SystemElementRelation, relation_id)
    if not relation or relation.blueprint_revision_id != revision_id:
        raise HTTPException(404, "Relation not found")
    await db.delete(relation)
    await db.commit()


@router.post("/blueprint-revisions/{revision_id}:validate", response_model=BlueprintValidationOut)
async def validate_blueprint(revision_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _validate_blueprint(db, await _blueprint_revision(db, revision_id))


@router.post("/product-concepts/{concept_id}:authorize-delivery-planning", response_model=DeliveryPlanningAuthorizationOut)
async def authorize_delivery_planning(
    concept_id: uuid.UUID, payload: AuthorizeDeliveryPlanning, db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    concept = await _concept(db, concept_id)
    await authorize_action(db, principal, "planning.delivery.authorize", product_id=concept.product_id)
    if concept.status != "approved":
        raise HTTPException(409, "Concept approval is required")
    blueprint = (await db.execute(select(SystemBlueprint).where(SystemBlueprint.product_id == concept.product_id))).scalar_one()
    revision = await _blueprint_revision(db, blueprint.current_revision_id)
    if revision.status != "approved":
        raise HTTPException(409, "System Map approval is required")
    concept_revision = await db.get(ProductConceptRevision, concept.current_revision_id)
    target_hash = canonical_hash({
        "concept_revision_id": str(concept_revision.id), "concept_hash": concept_revision.content_hash,
        "blueprint_revision_id": str(revision.id), "blueprint_hash": revision.content_hash,
    })
    if not await approved_concept_request(db, concept, target_hash):
        raise HTTPException(409, "A current governed approval decision is required")
    existing_version = (await db.execute(select(ProductVersion).where(
        ProductVersion.product_id == concept.product_id, ProductVersion.version == payload.version
    ))).scalar_one_or_none()
    if existing_version:
        existing_project = (await db.execute(select(Project).where(
            Project.product_version_id == existing_version.id
        ).order_by(Project.created_at))).scalars().first()
        if revision.product_version_id == existing_version.id and existing_project:
            existing_scope = (await db.execute(select(ProjectScope).where(
                ProjectScope.project_id == existing_project.id,
                ProjectScope.blueprint_base_revision_id == revision.id,
            ).order_by(ProjectScope.revision))).scalars().first()
            if existing_scope:
                return DeliveryPlanningAuthorizationOut(
                    product_id=concept.product_id, product_version_id=existing_version.id,
                    project_id=existing_project.id, project_scope_id=existing_scope.id,
                    blueprint_revision_id=revision.id,
                )
        raise HTTPException(409, "This product version already exists")
    product_version = ProductVersion(product_id=concept.product_id, version=payload.version, status="planned")
    db.add(product_version)
    await db.flush()
    project = Project(
        name=payload.project_name, description=payload.project_description,
        product_version_id=product_version.id, owner=payload.owner, status="planned",
        working_directory_path=payload.working_directory_path,
    )
    db.add(project)
    await db.flush()
    project_scope = ProjectScope(
        project_id=project.id, blueprint_base_revision_id=revision.id,
        revision=1, created_by=principal.display_name,
    )
    product = await db.get(Product, concept.product_id)
    product.status = "active"
    revision.product_version_id = product_version.id
    requests = list((await db.execute(select(DevelopmentRequest).where(
        DevelopmentRequest.product_id == concept.product_id,
        DevelopmentRequest.status.in_(["received", "triaging", "accepted"]),
    ))).scalars())
    for request in requests:
        request.status = "converted"
    db.add(project_scope)
    db.add(_audit("product_concept", concept.id, "delivery_planning_authorized", principal.display_name, {"project_id": str(project.id), "approval_hash": target_hash}))
    await db.commit()
    return DeliveryPlanningAuthorizationOut(
        product_id=concept.product_id, product_version_id=product_version.id,
        project_id=project.id, project_scope_id=project_scope.id, blueprint_revision_id=revision.id,
    )


@router.get("/projects/{project_id}/scopes", response_model=list[ProjectScopeOut])
async def list_project_scopes(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectScope).where(ProjectScope.project_id == project_id).order_by(ProjectScope.revision.desc()))
    return list(result.scalars())


@router.post("/projects/{project_id}/scopes", response_model=ProjectScopeOut, status_code=201)
async def create_project_scope(project_id: uuid.UUID, payload: ProjectScopeCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    blueprint_revision = await _blueprint_revision(db, payload.blueprint_base_revision_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if blueprint_revision.status != "approved":
        raise HTTPException(409, "Project Scope must be based on an approved System Map")
    version = await db.get(ProductVersion, project.product_version_id)
    blueprint = await db.get(SystemBlueprint, blueprint_revision.blueprint_id)
    if not version or version.product_id != blueprint.product_id:
        raise HTTPException(422, "System Map and project belong to different products")
    number = (await db.scalar(select(func.max(ProjectScope.revision)).where(ProjectScope.project_id == project_id)) or 0) + 1
    scope = ProjectScope(project_id=project_id, revision=number, **payload.model_dump())
    db.add(scope)
    await db.commit()
    await db.refresh(scope)
    return scope


async def _scope_item_out(db: AsyncSession, item: ProjectScopeItem) -> ProjectScopeItemOut:
    criteria = list((await db.execute(select(ScopeItemAcceptanceCriterion).where(
        ScopeItemAcceptanceCriterion.project_scope_item_id == item.id
    ).order_by(ScopeItemAcceptanceCriterion.order_index))).scalars())
    return ProjectScopeItemOut(
        **{key: value for key, value in item.__dict__.items() if not key.startswith("_")},
        acceptance_criteria=[AcceptanceCriterionOut.model_validate(row) for row in criteria],
    )


@router.get("/project-scopes/{scope_id}/items", response_model=list[ProjectScopeItemOut])
async def list_project_scope_items(scope_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if not await db.get(ProjectScope, scope_id):
        raise HTTPException(404, "Project Scope not found")
    items = list((await db.execute(select(ProjectScopeItem).where(
        ProjectScopeItem.project_scope_id == scope_id
    ).order_by(ProjectScopeItem.created_at))).scalars())
    return [await _scope_item_out(db, item) for item in items]


@router.post("/project-scopes/{scope_id}/items", response_model=ProjectScopeItemOut, status_code=201)
async def add_project_scope_item(scope_id: uuid.UUID, payload: ProjectScopeItemCreate, db: AsyncSession = Depends(get_db)):
    scope = await db.get(ProjectScope, scope_id)
    if not scope:
        raise HTTPException(404, "Project Scope not found")
    if scope.status != "draft":
        raise HTTPException(409, "Only a draft Project Scope can be changed")
    element_revision = (await db.execute(select(SystemElementRevision).where(
        SystemElementRevision.blueprint_revision_id == scope.blueprint_base_revision_id,
        SystemElementRevision.system_element_id == payload.system_element_id,
    ))).scalar_one_or_none()
    if element_revision is None:
        raise HTTPException(422, "The element is not present in the baseline System Map")
    item_data = payload.model_dump(exclude={"acceptance_criteria"})
    item = ProjectScopeItem(project_scope_id=scope_id, **item_data)
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "The element is already part of this Project Scope") from None
    db.add_all([ScopeItemAcceptanceCriterion(project_scope_item_id=item.id, **criterion.model_dump())
                for criterion in payload.acceptance_criteria])
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "The element is already part of this Project Scope") from None
    await db.refresh(item)
    return await _scope_item_out(db, item)
