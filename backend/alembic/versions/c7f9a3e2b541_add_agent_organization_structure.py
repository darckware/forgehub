"""add agent organization structure

Revision ID: c7f9a3e2b541
Revises: b6e8f2d1a430
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7f9a3e2b541"
down_revision: Union[str, Sequence[str], None] = "b6e8f2d1a430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STRUCTURE = {
    "athos": ("Executive Orchestration", "Portfolio & Delivery Orchestration", None),
    "atlas": ("Product & Planning", "Demand Engineering", "athos"),
    "nomos": ("Product & Planning", "Business Rules & State Design", "atlas"),
    "daedalus": ("Engineering", "Engineering Leadership", "athos"),
    "archimedes": ("Engineering", "Architecture & Integration Design", "daedalus"),
    "datalus": ("Engineering", "Data Engineering", "daedalus"),
    "hermes-ux": ("Engineering", "Product Design & UX", "daedalus"),
    "koios": ("Engineering", "AI & Retrieval Engineering", "daedalus"),
    "forge": ("Engineering", "Implementation & Maintenance", "daedalus"),
    "mnemosyne": ("Knowledge & Context", "Context Governance & Handoffs", "athos"),
    "mnemon": ("Knowledge & Context", "Runtime Memory", "mnemosyne"),
    "scriba": ("Documentation", "Technical Documentation", "athos"),
    "themis": ("Governance & Compliance", "Privacy & Regulatory Governance", "athos"),
    "prometheus": ("Governance & Compliance", "Integration Governance", "themis"),
    "hephaestus": ("Platform & Operations", "Platform Operations", "athos"),
    "hermod": ("Platform & Operations", "FinOps & Model Operations", "hephaestus"),
    "iris": ("Platform & Operations", "Release & Feature Management", "hephaestus"),
    "soteria": ("Platform & Operations", "Reliability & Disaster Recovery", "hephaestus"),
    "talos": ("Platform & Operations", "Workflow Automation", "hephaestus"),
    "aegis": ("Security & Assurance", "Security Leadership", "athos"),
    "argus": ("Security & Assurance", "Code Quality", "aegis"),
    "chronos": ("Security & Assurance", "Regression & Performance", "aegis"),
    "oracle": ("Security & Assurance", "Acceptance & Evidence", "aegis"),
}


def upgrade() -> None:
    op.add_column("agents", sa.Column("department", sa.String(length=100)), schema="company")
    op.add_column("agents", sa.Column("sector", sa.String(length=120)), schema="company")
    op.add_column("agents", sa.Column("reports_to_profile_slug", sa.String(length=50)), schema="company")
    connection = op.get_bind()
    for slug, (department, sector, manager) in STRUCTURE.items():
        connection.execute(
            sa.text("UPDATE company.agents SET department=:department, sector=:sector, reports_to_profile_slug=:manager WHERE profile_slug=:slug"),
            {"department": department, "sector": sector, "manager": manager, "slug": slug},
        )


def downgrade() -> None:
    op.drop_column("agents", "reports_to_profile_slug", schema="company")
    op.drop_column("agents", "sector", schema="company")
    op.drop_column("agents", "department", schema="company")
