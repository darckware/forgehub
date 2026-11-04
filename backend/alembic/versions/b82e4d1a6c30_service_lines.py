"""Create the service-line catalog and assign existing projects.

Revision ID: b82e4d1a6c30
Revises: a91f3c2e7d40
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b82e4d1a6c30"
down_revision = "a91f3c2e7d40"
branch_labels = None
depends_on = None

# Stages, evidence and agents follow the initial catalog in the integrated plan.
LINES = [
    ("software", "Desenvolvimento de software", ["Concepção e Contexto", "Telas e Regras de Negócio", "Banco de Dados e ERD", "Central de Projetos e Backlog", "Gate de Governança", "Fechamento de Versão", "Homologação de design"], ["git:", "CI", "documento"], ["porthus", "aramis", "dartan"], "desenvolvimento"),
    ("sustentacao", "Sustentação de sistemas", ["Triagem", "Correção", "Verificação", "Registro"], ["git:", "host_execution"], ["daedalus", "aramis"], "suporte_horas"),
    ("manutencao", "Manutenção de estações e servidores", ["Pedido", "Autorização (máquinas/scripts)", "Execução", "Verificação", "Registro de atendimento"], ["host_execution", "horas"], ["hephaestus", "aegis"], "suporte_horas"),
    ("suporte", "Suporte ao cliente", ["Triagem", "Atendimento", "Resposta aprovada", "Encerramento"], ["e-mail aprovado", "horas"], ["lara"], "suporte_horas"),
    ("infraestrutura", "Infraestrutura e operação", ["Detecção", "Ação", "Verificação", "Runbook"], ["host_execution", "db:", "runbook"], ["hephaestus", "aegis"], "interno"),
    ("documentacao", "Documentação e conhecimento", ["Rascunho", "Revisão", "Publicação"], ["file:", "artefato"], ["scriba", "mnemosyne", "athos"], "interno"),
    ("marketing", "Marketing e captação", ["Proposta", "Aprovação", "Execução", "Medição pelo funil"], ["artefato", "métrica do funil"], ["kairos", "lara"], "interno"),
    ("missoes", "Missões", ["Planejamento", "Fases", "Consolidação"], ["resultado consolidado"], ["athos"], None),
    ("incidentes", "Incidentes", ["Detecção", "Contenção", "Correção", "Pós-incidente"], ["evidência", "relatório"], ["hephaestus"], None),
]


def upgrade():
    op.create_table(
        "service_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("stages", postgresql.JSONB(), nullable=False),
        sa.Column("required_documents", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_types", postgresql.JSONB(), nullable=False),
        sa.Column("default_agents", postgresql.JSONB(), nullable=False),
        sa.Column("sla_hours", sa.Integer()),
        sa.Column("darckware_contract_type", sa.Text()),
        sa.Column("client_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="company",
    )
    table = sa.table("service_lines", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("slug", sa.String()),
                     sa.column("name", sa.String()), sa.column("stages", postgresql.JSONB()),
                     sa.column("required_documents", postgresql.JSONB()), sa.column("evidence_types", postgresql.JSONB()),
                     sa.column("default_agents", postgresql.JSONB()), sa.column("darckware_contract_type", sa.Text()),
                     schema="company")
    op.bulk_insert(table, [dict(id=uuid.uuid4(), slug=slug, name=name, stages=stages,
                                required_documents=[], evidence_types=evidence, default_agents=agents,
                                darckware_contract_type=contract)
                           for slug, name, stages, evidence, agents, contract in LINES])
    op.add_column("projects", sa.Column("service_line_id", postgresql.UUID(as_uuid=True)), schema="company")
    op.execute("""UPDATE company.projects p SET service_line_id = s.id FROM company.service_lines s
                  WHERE s.slug = CASE p.project_type WHEN 'maintenance' THEN 'sustentacao'
                                 WHEN 'mission' THEN 'missoes' ELSE 'software' END""")
    op.alter_column("projects", "service_line_id", nullable=False, schema="company")
    op.create_foreign_key("fk_projects_service_line_id", "projects", "service_lines", ["service_line_id"], ["id"],
                          source_schema="company", referent_schema="company")


def downgrade():
    op.drop_constraint("fk_projects_service_line_id", "projects", schema="company", type_="foreignkey")
    op.drop_column("projects", "service_line_id", schema="company")
    op.drop_table("service_lines", schema="company")
