"""add platform to tech stack options

Revision ID: 0fdf831eade6
Revises: abea36ac8d3e
Create Date: 2026-08-16 01:51:11.800033

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fdf831eade6'
down_revision: Union[str, Sequence[str], None] = 'abea36ac8d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Only meaningful within layer="frontend" -- these are different frontend
# scenarios/toolchains, not different layers. Named and scoped from
# Marcelo directly (2026-08-16): "web app, landing page, site institucional,
# PWA, mobile" -- a plain web/mobile split (this migration's first draft)
# was too coarse, mobile alone wasn't the only thing missing visibility.
PLATFORMS = ("web_app", "landing_page", "institutional_site", "pwa", "mobile")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tech_stack_options', sa.Column('platform', sa.String(length=20), nullable=True), schema='company',
    )
    op.create_check_constraint(
        'ck_tech_stack_options_platform', 'tech_stack_options',
        f"platform IS NULL OR platform IN {PLATFORMS!r}", schema='company',
    )

    tech_stack_options = sa.table(
        'tech_stack_options',
        sa.column('id', sa.UUID()), sa.column('layer', sa.String()), sa.column('name', sa.String()),
        sa.column('description', sa.Text()), sa.column('source', sa.String()),
        sa.column('platform', sa.String()),
        schema='company',
    )

    # Reclassify the org_standard frontend rows seeded by migration
    # 9823e7890ae4 -- backend/database/deploy_infra stay NULL (platform
    # doesn't apply outside frontend).
    RECLASSIFY = {
        "React + TypeScript + Vite + Tailwind CSS + shadcn/ui": "web_app",
        "React + TypeScript + PrimeReact, MUI ou Ant Design": "web_app",
        "Next.js + TypeScript + Tailwind CSS + shadcn/ui": "institutional_site",
        "React Native + Expo + TypeScript + NativeWind": "mobile",
        "React Native + Expo + Tamagui": "mobile",
    }
    for name, platform in RECLASSIFY.items():
        op.execute(
            sa.update(tech_stack_options)
            .where(tech_stack_options.c.layer == "frontend", tech_stack_options.c.name == name)
            .values(platform=platform)
        )

    # New entries for the two scenarios the seed catalog had no option for
    # at all -- landing_page (no framework needed) and pwa (reuses the
    # already-approved web_app baseline, adds the plugin, per Marcelo:
    # "stack web_app existente + Vite PWA plugin").
    op.bulk_insert(tech_stack_options, [
        {
            "id": uuid.uuid4(), "layer": "frontend", "platform": "landing_page",
            "name": "HTML + CSS + JS puro",
            "description": "Página única, sem build step nem framework -- landing page simples.",
            "source": "org_standard",
        },
        {
            "id": uuid.uuid4(), "layer": "frontend", "platform": "pwa",
            "name": "React + TypeScript + Vite + Tailwind CSS + shadcn/ui + vite-plugin-pwa",
            "description": "Baseline web_app já aprovado, com vite-plugin-pwa (service worker/manifest) para instalar como PWA.",
            "source": "org_standard",
        },
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM company.tech_stack_options WHERE layer = 'frontend' "
        "AND name IN ('HTML + CSS + JS puro', "
        "'React + TypeScript + Vite + Tailwind CSS + shadcn/ui + vite-plugin-pwa')"
    )
    op.drop_constraint('ck_tech_stack_options_platform', 'tech_stack_options', schema='company', type_='check')
    op.drop_column('tech_stack_options', 'platform', schema='company')
