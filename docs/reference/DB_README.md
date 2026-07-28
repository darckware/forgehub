# ForgeHub — Banco de Dados

## Decisão

O ForgeHub **não roda um PostgreSQL próprio**. Ele conecta na instância compartilhada `company_postgres`, que já existe e já hospeda o Kanboard oficial.

| Campo | Valor |
|---|---|
| Instância | `company_postgres` |
| Host / Porta | `localhost:5433` (container expõe `5433->5432`) |
| Database | `forgehub` |
| Schema da aplicação | `company` |
| Owner | `foundation` |
| Imagem | `pgvector/pgvector:pg16` |

A outra instância, `foundation_postgres` (porta `5432`), é exclusiva de dados internos do ecossistema Hermes/Foundation (memória, roteamento do ForgeRouter, auditoria) e **não deve ser usada pelo ForgeHub**.

Fonte de verdade da topologia completa: `/root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md`.

## Por que `company_postgres`

Regra de posicionamento do Foundation: dados de negócio/aplicação vão em `company_postgres`; dados canônicos do próprio ecossistema Hermes vão em `foundation_postgres`. O ForgeHub é uma aplicação de negócio (controle de produtos/projetos/pipelines), então cai em `company_postgres`.

## Configuração local

Variáveis em `.env` (raiz do repo):
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=foundation
POSTGRES_PASSWORD=foundation_local_dev_password
POSTGRES_DB=forgehub
POSTGRES_SCHEMA=company
```

String de conexão (SQLAlchemy + asyncpg, por `docs/reference/TECHNOLOGY.md`):
```
DATABASE_URL=postgresql+asyncpg://foundation:foundation_local_dev_password@localhost:5433/forgehub
```

Migrations (Alembic) devem criar as tabelas do domínio dentro do schema `company`, nunca em `public`.

## Estado conhecido (validado em 18/06/2026)

- Schema `company` já existe no banco `forgehub`, ainda sem tabelas.
- `database/postgres-company/docker-compose.yml` (neste repo) gerencia o container `company_postgres`. Ele estava órfão (compose original perdido no rename ForgeCompany→Forgehub) e foi readotado via `docker compose up -d` em 18/06/2026 — o Docker recriou o container por uma pequena diferença de hash de config, mas os dados (bind mount) ficaram intactos: `forgehub`/`company` e `kanboard` (tasks) verificados depois.

## Regras

- Não criar databases ou schemas adicionais sem atualizar este arquivo e `/root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md` + `/root/.hermes/foundation/services/inventory.md`.
- Não usar o database administrativo `postgres` para dados de aplicação.
- Não duplicar o mesmo domínio de negócio em `foundation_postgres`.
