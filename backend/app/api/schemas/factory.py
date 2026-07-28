"""Pydantic read schemas for the Software Factory cockpit.

Read-only projections. The Factory domain owns no table of its own — it
aggregates state that already lives in the product, system_scope, backlog,
task and governance domains (see app/api/routes/factory.py).

The tree is Product -> Project -> phases, matching the domain's own
granularity: a product is durable, and every evolution of it becomes a
project that walks the five phases. Making the product the root (rather
than returning a flat project list) is what lets the cockpit stand in for
the Products and Projects screens: a product with no project yet is still
a row, instead of being invisible until someone creates a project for it.
"""
import uuid

from pydantic import BaseModel

# The five development phases, in order.
PHASE_KEYS = ("conception", "designer", "procedures", "execution", "quality")

# State of one phase. Deliberately a small, closed vocabulary that maps
# to the spec's colour legend (§5.1) rather than re-exposing each source
# domain's own status string:
#   approved    -> green,  the phase is locked and the next one can start
#   in_progress -> amber,  work started but not approved
#   pending     -> grey,   nothing recorded yet
#   blocked     -> red,    the source domain reports rework/rejected
PHASE_STATES = ("approved", "in_progress", "pending", "blocked")


class PhaseStatus(BaseModel):
    """One phase's state for one project."""

    key: str
    state: str
    # The originating domain's own status string ("in_review", "baselined",
    # ...), kept so the UI can show the real word on hover instead of only
    # the reduced traffic-light state. None when nothing exists yet.
    detail: str | None = None
    # Progress counters, when the phase has countable children (phases 3
    # and 4). None for the phases whose state is a single approval.
    total: int | None = None
    done: int | None = None


class ProjectCockpitRow(BaseModel):
    """A project and the state of its five phases.

    A project — not a product — is the unit of *work*: every evolution of a
    product becomes a project, and it is the project that carries the
    description of what will be built and walks the five phases.
    """

    project_id: uuid.UUID
    project_name: str
    project_status: str
    project_description: str | None = None

    version_id: uuid.UUID
    version_number: str
    version_status: str

    phases: list[PhaseStatus]

    # Count of planning groups (PlanningItem) under this project, and of
    # tasks under those groups: Product -> Project -> Planning -> Task.
    planning_count: int = 0
    task_count: int = 0


class ProductVersionRow(BaseModel):
    version_id: uuid.UUID
    version_number: str
    version_status: str


class ProductCockpitRow(BaseModel):
    """A product with everything the cockpit needs to stand in for the
    Products screen: its own registration fields, its versions (so "New
    project" can offer a version to attach to), and its projects."""

    product_id: uuid.UUID
    product_name: str
    product_status: str
    product_description: str | None = None
    application_url: str | None = None
    application_url_dev: str | None = None

    # Phase 1 is recorded at product level (product_concepts holds a UNIQUE
    # FK to products), so it is reported here as well as inside each
    # project's phase list.
    concept_status: str | None = None

    versions: list[ProductVersionRow]
    projects: list[ProjectCockpitRow]


class CockpitOut(BaseModel):
    products: list[ProductCockpitRow]
