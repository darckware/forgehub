# ForgeHub — Banco de Dados

## Decisão

O ForgeHub usa uma instância PostgreSQL dedicada. Os dados internos do ForgeRouter e do Hindsight/Foundation ficam em instâncias separadas.

| Campo | Valor |
|---|---|
| Instância | `forgehub_postgres` |
| Host / Porta | `localhost:5433` (container expõe `5433->5432`) |
| Database | `forgehub` |
| Schema da aplicação | `company` |
| Owner | `foundation` |
| Imagem | `pgvector/pgvector:pg16` |

As demais instâncias são `forgerouter_postgres` (`localhost:5434`, database `forgerouter`) e `hindsight_postgres` (`localhost:5432`, database `foundation`, schema `hindsight`). O banco descontinuado `kanboard` não faz parte da nova topologia.

Fonte de verdade da topologia completa: `/root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md`.

## Separação por responsabilidade

Dados de negócio do ForgeHub ficam em `forgehub_postgres`; roteamento de LLM fica em `forgerouter_postgres`; memória e dados canônicos do Foundation ficam em `hindsight_postgres`.

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

## Estado conhecido (validado em 03/09/2026)

- `database/docker-compose.yml` gerencia as três instâncias e seus volumes Docker dedicados.
- Os databases `forgehub`, `forgerouter` e `foundation` foram migrados por `pg_dump`/`pg_restore`.
- Os containers antigos permanecem parados apenas durante a janela de rollback; seus bind mounts não são usados pela nova topologia.

## Regras

- Não criar databases ou schemas adicionais sem atualizar este arquivo e `/root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md` + `/root/.hermes/foundation/services/inventory.md`.
- Não usar o database administrativo `postgres` para dados de aplicação.
- Não duplicar o mesmo domínio entre as três instâncias.
