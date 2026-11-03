"""Fictitious, reproducible seed for the isolated test database (Plano Integrado T.2).

    ENVIRONMENT=test python -m app.scripts.seed_test_database
    ./test-env/reset.sh --seed        # reset to Alembic head, then this

Products, versions, projects, planning items, tasks, agents, users (one
admin), clients and machines -- all invented. Nothing here names a real
person, client, phone, address or secret:

- IPs come only from the documentation ranges (RFC 5737: 192.0.2.0/24,
  198.51.100.0/24, 203.0.113.0/24), which route nowhere;
- e-mails use the reserved `.test` TLD (RFC 2606);
- clients exist only as the Darckware id/name snapshot ForgeHub keeps on
  products, projects and machines (the CRM itself lives in Darckware, which a
  test process never reaches), with ids derived here, not copied;
- no key, password or token is stored, except the test admin's own password
  hash, whose plain value (TEST_ADMIN_PASSWORD) is public by design: it only
  opens the localhost-only test database.

Every id is uuid5(SEED_NAMESPACE, "<table>:<natural key>") and task numbers
are fixed, so two seeds -- on two fresh resets, or twice on the same
database -- produce exactly the same rows. Re-running on a seeded database
merges by primary key instead of duplicating.

Same guard as reset_test_database.py: refuses before connecting unless
ENVIRONMENT=test and the target is on the test allowlist, and refuses after
connecting unless the server is the test instance.
"""
import asyncio
import hashlib
import uuid
from datetime import date

SEED_NAMESPACE = uuid.UUID("5e7d0f2a-7c1b-4e0a-9b6d-0f0f7e57da7a")

TEST_ADMIN_USERNAME = "admin.teste"
TEST_ADMIN_PASSWORD = "teste-admin-forgehub"
TEST_OPERATOR_USERNAME = "operador.teste"
TEST_OPERATOR_PASSWORD = "teste-operador-forgehub"

# Tables the reproducibility check compares (T.2 acceptance).
REPORT_TABLES = ("products", "product_versions", "projects", "planning_items", "project_tasks",
                 "agents", "users", "servers")


def seed_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"{kind}:{key}")


CLIENTS = (
    ("cliente-alfa", "Cliente Fictício Alfa Ltda"),
    ("cliente-beta", "Cooperativa Fictícia Beta"),
)

PROFILES = (
    ("Administrador", "Acesso total a todos os módulos", True),
    ("Padrão", "Visualização e consulta sem alterações", False),
)

USERS = (
    # username, password, full name, e-mail, is_admin, profile
    (TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD, "Admin de Teste", "admin@forgehub.test", True, "Administrador"),
    (TEST_OPERATOR_USERNAME, TEST_OPERATOR_PASSWORD, "Operador de Teste", "operador@forgehub.test", False, "Padrão"),
)

AGENTS = (
    # name, slug, type, runtime, layer, description
    ("Orion Teste", "orion-teste", "coordinator", "hermes", "Orquestração", "Coordenador fictício do ambiente de teste."),
    ("Vega Teste", "vega-teste", "executor", "claude", "Análise e Arquitetura", "Executor fictício (runtime claude)."),
    ("Lyra Teste", "lyra-teste", "executor", "codex", "Desenvolvimento", "Executor fictício (runtime codex)."),
    ("Draco Teste", "draco-teste", "executor", "agy", "Interface", "Executor fictício (runtime agy)."),
)

# product name, description, client key or None, versions [(version, status)]
PRODUCTS = (
    ("Produto Fictício Andes", "Portal interno inventado para testes.", None,
     (("1.0.0", "published"), ("1.1.0", "in_development"))),
    ("Produto Fictício Boreal", "Aplicativo inventado de um cliente fictício.", "cliente-alfa",
     (("0.1.0", "in_development"),)),
    ("Produto Fictício Cirro", "API inventada de um cliente fictício.", "cliente-beta",
     (("2.0.0", "planned"),)),
)

# project name, (product, version), solution type, status, owner agent
PROJECTS = (
    ("Andes 1.1 - Painel", ("Produto Fictício Andes", "1.1.0"), "web_app", "active", "Orion Teste"),
    ("Andes 1.1 - API", ("Produto Fictício Andes", "1.1.0"), "api_service", "planned", "Lyra Teste"),
    ("Boreal 0.1 - App", ("Produto Fictício Boreal", "0.1.0"), "mobile_app", "active", "Draco Teste"),
    ("Cirro 2.0 - Serviço", ("Produto Fictício Cirro", "2.0.0"), "api_service", "planned", "Vega Teste"),
)

# planning title, project, type, status, priority, tasks [(number, title, status)]
PLANNING = (
    ("Tela de login fictícia", "Andes 1.1 - Painel", "feature", "in_progress", "high",
     ((9001, "Formulário de login", "done"), (9002, "Mensagens de erro do login", "in_progress"))),
    ("Corrigir filtro da lista", "Andes 1.1 - Painel", "bug", "triaged", "medium",
     ((9003, "Reproduzir o filtro quebrado", "ready"),)),
    ("Endpoint de pedidos", "Andes 1.1 - API", "feature", "scoped", "medium",
     ((9004, "Modelo de pedido", "planned"), (9005, "Rota de listagem de pedidos", "planned"))),
    ("Cadastro offline", "Boreal 0.1 - App", "feature", "in_progress", "high",
     ((9006, "Fila local de cadastros", "in_progress"), (9007, "Sincronizar ao reconectar", "blocked"))),
    ("Documentar contrato da API", "Cirro 2.0 - Serviço", "documentation", "new", "low",
     ((9008, "Rascunho do contrato", "planned"),)),
)

# name, kind, os, ip (RFC 5737 only), remote user, client key or None, location
MACHINES = (
    ("srv-teste-01", "server", "linux", "192.0.2.10", "operador", None, "Datacenter fictício"),
    ("srv-teste-02", "server", "linux", "192.0.2.11", "operador", "cliente-alfa", "Sala técnica fictícia"),
    ("est-alfa-01", "workstation", "windows", "198.51.100.21", "suporte", "cliente-alfa", "Recepção fictícia"),
    ("est-beta-01", "workstation", "linux", "203.0.113.31", "suporte", "cliente-beta", "Escritório fictício"),
)


def build_rows() -> list:
    """Every seeded ORM object, parents before children. Pure: no I/O."""
    from app.core.security import hash_password
    from app.db.models.agent import Agent
    from app.db.models.backlog import PlanningItem
    from app.db.models.product import Product, ProductVersion
    from app.db.models.profile import MODULES, Profile, ProfilePermission
    from app.db.models.project import Project
    from app.db.models.server import Server
    from app.db.models.task import ProjectTask
    from app.db.models.user import User

    clients = {key: (seed_id("client", key), name) for key, name in CLIENTS}
    rows: list = []

    for name, description, full in PROFILES:
        profile_id = seed_id("profiles", name)
        rows.append(Profile(id=profile_id, name=name, description=description))
        for module in MODULES:
            rows.append(ProfilePermission(
                id=seed_id("profile_permissions", f"{name}:{module}"), profile_id=profile_id, module=module,
                can_view=True, can_query=True, can_write=full, can_delete=full,
            ))

    for username, password, full_name, email, is_admin, profile in USERS:
        rows.append(User(
            id=seed_id("users", username), username=username, hashed_password=hash_password(password),
            full_name=full_name, email=email, is_admin=is_admin, is_active=True,
            profile_id=seed_id("profiles", profile), ui_language="pt-BR",
        ))

    for name, slug, agent_type, runtime, layer, description in AGENTS:
        rows.append(Agent(
            id=seed_id("agents", slug), name=name, profile_slug=slug, agent_type=agent_type,
            runtime_type=runtime, layer=layer, description=description, status="active", is_active=True,
        ))

    for name, description, client_key, versions in PRODUCTS:
        client_id, client_name = clients[client_key] if client_key else (None, None)
        product_id = seed_id("products", name)
        rows.append(Product(
            id=product_id, name=name, description=description, status="active",
            darckware_client_id=client_id, darckware_client_name=client_name,
        ))
        for version, status in versions:
            rows.append(ProductVersion(
                id=seed_id("product_versions", f"{name}:{version}"), product_id=product_id,
                version=version, status=status,
            ))

    client_by_product = {name: client_key for name, _, client_key, _ in PRODUCTS}
    for name, (product, version), solution_type, status, owner in PROJECTS:
        client_key = client_by_product[product]
        rows.append(Project(
            id=seed_id("projects", name), name=name, product_version_id=seed_id("product_versions", f"{product}:{version}"),
            solution_type=solution_type, status=status, owner=owner, project_type="creation",
            darckware_client_id=clients[client_key][0] if client_key else None,
            start_date=date(2026, 10, 1), target_end_date=date(2026, 12, 15),
        ))

    version_by_project = {name: seed_id("product_versions", f"{p}:{v}") for name, (p, v), *_ in PROJECTS}
    for title, project, item_type, status, priority, tasks in PLANNING:
        item_id = seed_id("planning_items", title)
        rows.append(PlanningItem(
            id=item_id, title=title, item_type=item_type, status=status, priority=priority,
            project_id=seed_id("projects", project), target_version_id=version_by_project[project],
        ))
        for number, task_title, task_status in tasks:
            rows.append(ProjectTask(
                id=seed_id("project_tasks", str(number)), number=number, title=task_title,
                planning_item_id=item_id, status=task_status, priority=priority,
                task_type=item_type,
            ))

    for name, kind, os_family, ip, remote_user, client_key, location in MACHINES:
        client_id, client_name = clients[client_key] if client_key else (None, None)
        rows.append(Server(
            id=seed_id("servers", name), name=name, kind=kind, os_family=os_family, ip_address=ip,
            remote_user=remote_user, environment="teste", location=location,
            darckware_client_id=client_id, darckware_client_name=client_name,
            description="Máquina fictícia do ambiente de teste (endereço de documentação, não roteável).",
        ))

    return rows


async def report(conn) -> dict[str, tuple[int, str]]:
    """Row count and sha256 of the sorted ids, per REPORT_TABLES."""
    from sqlalchemy import text

    out = {}
    for table in REPORT_TABLES:
        ids = (await conn.execute(text(f"SELECT id::text FROM company.{table} ORDER BY id"))).scalars().all()
        out[table] = (len(ids), hashlib.sha256("\n".join(ids).encode()).hexdigest()[:16])
    return out


async def seed(settings) -> dict[str, tuple[int, str]]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.scripts.reset_test_database import assert_test_server

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await assert_test_server(conn)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            for row in build_rows():
                await session.merge(row)
                # Flush per row so parents exist before children (merge has no
                # unit-of-work ordering across separately merged objects).
                await session.flush()
            # Task numbers are explicit; move the identity past them so a task
            # created later through the API doesn't collide with the seed.
            await session.execute(text(
                "SELECT setval(pg_get_serial_sequence('company.project_tasks', 'number'), "
                "GREATEST((SELECT max(number) FROM company.project_tasks), 1))"
            ))
            await session.commit()
        async with engine.connect() as conn:
            return await report(conn)
    finally:
        await engine.dispose()


def main() -> None:
    from app.scripts.reset_test_database import _load_settings

    settings = _load_settings()
    result = asyncio.run(seed(settings))
    print("seed done (fictitious data):")
    for table, (count, digest) in result.items():
        print(f"  {table:<18} {count:>3} rows  ids sha256:{digest}")
    print(f"  test admin: {TEST_ADMIN_USERNAME} / {TEST_ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
