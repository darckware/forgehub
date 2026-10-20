"""update tech stack options catalog layers and technologies

Revision ID: 1a2b3c4d5e6f
Revises: e8a91c2b3d4f
Create Date: 2026-08-31

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'e8a91c2b3d4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_LAYERS = (
    "frontend",
    "mobile",
    "backend",
    "database",
    "cache",
    "messaging",
    "auth",
    "storage",
    "search",
    "api_gateway",
    "deploy_infra",
    "cicd",
    "observability",
    "testing",
    "documentation",
)

SEED_CATALOG: list[tuple[str, str, str | None]] = [
    # Frontend
    ("frontend", "React + TypeScript + Vite + Tailwind CSS + shadcn/ui", None),
    ("frontend", "React + TypeScript + Vite + MUI", None),
    ("frontend", "React + TypeScript + Vite + Ant Design", None),
    ("frontend", "React + TypeScript + Vite + PrimeReact", None),
    ("frontend", "Next.js + TypeScript + Tailwind CSS + shadcn/ui", None),
    ("frontend", "Vue 3 + TypeScript + Vite + Tailwind CSS", None),
    ("frontend", "Nuxt + TypeScript + Tailwind CSS", None),
    ("frontend", "Angular + TypeScript + Angular Material", None),
    ("frontend", "Astro + TypeScript + Tailwind CSS", None),
    ("frontend", "HTML + CSS + JavaScript", None),

    # Mobile
    ("mobile", "React Native + Expo + TypeScript + NativeWind", None),
    ("mobile", "React Native + Expo + Tamagui", None),
    ("mobile", "Flutter + Dart", None),

    # Backend
    ("backend", "Python + FastAPI + SQLAlchemy async", None),
    ("backend", "Python + FastAPI + SQLModel", None),
    ("backend", "Node.js + TypeScript + NestJS", None),
    ("backend", "Node.js + TypeScript + Fastify", None),
    ("backend", "Node.js + TypeScript + Express", None),
    ("backend", "C# + ASP.NET Core Web API", None),
    ("backend", "Java + Spring Boot", None),

    # Database
    ("database", "PostgreSQL", None),
    ("database", "MySQL", None),
    ("database", "SQL Server", None),
    ("database", "MongoDB", None),
    ("database", "SQLite", None),
    ("database", "DynamoDB", None),

    # Cache
    ("cache", "Redis", None),
    ("cache", "Valkey", None),

    # Messaging / Event Bus
    ("messaging", "RabbitMQ", None),
    ("messaging", "Apache Kafka", None),
    ("messaging", "AWS SQS + SNS", None),
    ("messaging", "Azure Service Bus", None),

    # Authentication / Identity
    ("auth", "Keycloak", None),
    ("auth", "Auth0", None),
    ("auth", "Microsoft Entra ID", None),
    ("auth", "AWS Cognito", None),
    ("auth", "Clerk", None),
    ("auth", "Supabase Auth", None),

    # Storage
    ("storage", "AWS S3", None),
    ("storage", "Azure Blob Storage", None),
    ("storage", "Google Cloud Storage", None),
    ("storage", "MinIO", None),

    # Search
    ("search", "Elasticsearch", None),
    ("search", "OpenSearch", None),
    ("search", "Meilisearch", None),

    # API / Gateway
    ("api_gateway", "REST API", None),
    ("api_gateway", "GraphQL", None),
    ("api_gateway", "gRPC", None),
    ("api_gateway", "Kong Gateway", None),
    ("api_gateway", "AWS API Gateway", None),

    # Deploy / Infrastructure
    ("deploy_infra", "Docker", None),
    ("deploy_infra", "Docker Compose", None),
    ("deploy_infra", "Kubernetes", None),
    ("deploy_infra", "Helm", None),
    ("deploy_infra", "Terraform", None),
    ("deploy_infra", "AWS ECS / Fargate", None),
    ("deploy_infra", "AWS EKS", None),
    ("deploy_infra", "Azure Container Apps", None),
    ("deploy_infra", "Azure AKS", None),
    ("deploy_infra", "Vercel", None),
    ("deploy_infra", "Cloudflare Pages", None),

    # CI/CD
    ("cicd", "GitHub Actions", None),
    ("cicd", "GitLab CI/CD", None),
    ("cicd", "Azure DevOps Pipelines", None),
    ("cicd", "Jenkins", None),

    # Observability
    ("observability", "OpenTelemetry", None),
    ("observability", "Prometheus + Grafana", None),
    ("observability", "Grafana Loki", None),
    ("observability", "Datadog", None),
    ("observability", "Sentry", None),

    # Testing
    ("testing", "Vitest + Testing Library", None),
    ("testing", "Jest + Testing Library", None),
    ("testing", "Playwright", None),
    ("testing", "Cypress", None),
    ("testing", "Pytest", None),
    ("testing", "xUnit", None),

    # Documentation
    ("documentation", "OpenAPI / Swagger", None),
    ("documentation", "Storybook", None),
    ("documentation", "Docusaurus", None),
]

tech_stack_options_table = sa.table(
    'tech_stack_options',
    sa.column('id', sa.UUID()),
    sa.column('layer', sa.String()),
    sa.column('name', sa.String()),
    sa.column('description', sa.Text()),
    sa.column('source', sa.String()),
    sa.column('platform', sa.String()),
    schema='company',
)


def upgrade() -> None:
    # 1. Update check constraint on layer
    op.drop_constraint('ck_tech_stack_options_layer', 'tech_stack_options', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tech_stack_options_layer',
        'tech_stack_options',
        f"layer IN {NEW_LAYERS!r}",
        schema='company'
    )

    # 2. Clear old org_standard options to replace with the complete standardized list
    op.execute("DELETE FROM company.tech_stack_options WHERE source = 'org_standard'")

    # 3. Insert all new options
    op.bulk_insert(tech_stack_options_table, [
        {
            "id": uuid.uuid4(),
            "layer": layer,
            "name": name,
            "description": description,
            "source": "org_standard",
            "platform": None,
        }
        for layer, name, description in SEED_CATALOG
    ])


def downgrade() -> None:
    old_layers = ('frontend', 'backend', 'database', 'deploy_infra')
    op.execute("DELETE FROM company.tech_stack_options WHERE source = 'org_standard'")
    op.drop_constraint('ck_tech_stack_options_layer', 'tech_stack_options', schema='company', type_='check')
    op.create_check_constraint(
        'ck_tech_stack_options_layer',
        'tech_stack_options',
        f"layer IN {old_layers!r}",
        schema='company'
    )
