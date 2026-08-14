"""Database introspection and query execution.

Endpoints:
  GET  /api/v1/database/instances           – list known PostgreSQL instances + databases
  GET  /api/v1/database/schemas             – schemas in a given instance+db
  GET  /api/v1/database/tables              – list tables with row counts
  GET  /api/v1/database/tables/{table}      – columns, indexes, FK for one table
  GET  /api/v1/database/schema              – full schema (tables + FKs) for ER diagram
  POST /api/v1/database/query               – execute a safe SELECT and return results
"""
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import get_db

# ---------------------------------------------------------------------------
# Known PostgreSQL instances (Docker-internal hostnames + databases)
# ---------------------------------------------------------------------------

_INSTANCES: dict[str, dict] = {
    "company_postgres": {
        "label": "company_postgres",
        "host": settings.POSTGRES_HOST,   # overridden to "company_postgres" in docker-compose
        "port": int(settings.POSTGRES_PORT),
        "databases": ["forgehub"],
        "default_db": "forgehub",
    },
    "foundation_postgres": {
        "label": "foundation_postgres",
        "host": settings.FOUNDATION_POSTGRES_HOST,
        "port": settings.FOUNDATION_POSTGRES_PORT,
        # "hermes_control" was a standalone database (schema git_control, 1
        # table) folded into foundation's own git_control schema on
        # 2026-07-09 -- see docs/governance/POSTGRESQL_TOPOLOGY.md.
        "databases": ["foundation", "forgerouter"],
        "default_db": "foundation",
    },
}

# Lazy engine / session-factory cache keyed by (host, port, db)
_session_cache: dict[tuple, async_sessionmaker] = {}


def _get_session_factory(instance: str, db: str) -> async_sessionmaker:
    """Return (creating if needed) a session factory for the given instance+db."""
    if instance not in _INSTANCES:
        raise HTTPException(status_code=400, detail=f"Unknown instance: {instance}")
    cfg = _INSTANCES[instance]
    key = (cfg["host"], cfg["port"], db)
    if key not in _session_cache:
        url = settings.db_url_for(cfg["host"], cfg["port"], db)
        engine = create_async_engine(url, future=True, pool_pre_ping=True, pool_size=2, max_overflow=3)
        _session_cache[key] = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
    return _session_cache[key]


async def _get_dynamic_db(
    instance: str = Query(default="company_postgres"),
    db: str = Query(default="forgehub"),
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session for any configured instance+database."""
    factory = _get_session_factory(instance, db)
    async with factory() as session:
        yield session

router = APIRouter(prefix="/api/v1/database", tags=["database"])

SCHEMA = settings.POSTGRES_SCHEMA  # "company"

# Only allow read statements to prevent accidental mutations
_ALLOWED_STARTS = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)
_MAX_ROWS = 1000

# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------

class InstanceInfo(BaseModel):
    key: str
    label: str
    databases: list[str]
    default_db: str


@router.get("/instances", response_model=list[InstanceInfo])
async def list_instances():
    """Return all configured PostgreSQL instances with their known databases."""
    return [
        InstanceInfo(key=k, label=v["label"], databases=v["databases"], default_db=v["default_db"])
        for k, v in _INSTANCES.items()
    ]


# ---------------------------------------------------------------------------
# Schema listing (supports instance + db)
# ---------------------------------------------------------------------------

@router.get("/schemas", response_model=list[str])
async def list_schemas(db: AsyncSession = Depends(_get_dynamic_db)):
    """Return all non-system schemas for the selected instance+database.

    Excludes pg_toast%% and pg_temp_%%/pg_toast_temp_%% -- the latter are
    per-session temporary schemas Postgres creates on demand (e.g. a
    client running CREATE TEMP TABLE); they aren't real user schemas and
    normally disappear when their owning session disconnects, so surfacing
    them in the schema picker is just noise, not something to "clean up"
    by hand.
    """
    q = text("""
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name NOT LIKE 'pg_toast%'
          AND schema_name NOT LIKE 'pg_temp_%'
          AND schema_name NOT LIKE 'pg_toast_temp_%'
          AND schema_name NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schema_name
    """)
    rows = (await db.execute(q)).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    column_default: str | None
    is_primary_key: bool
    is_foreign_key: bool
    references: str | None  # "other_table.column"


class IndexInfo(BaseModel):
    name: str
    columns: list[str]
    is_unique: bool
    is_primary: bool


class TableDetail(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnInfo]
    indexes: list[IndexInfo]
    foreign_keys: list[dict]


class TableSummary(BaseModel):
    name: str
    row_count: int
    column_count: int


class SchemaTable(BaseModel):
    name: str
    columns: list[dict]  # {name, type, nullable, pk, fk_to}
    foreign_keys: list[dict]  # {column, ref_table, ref_column}


class SchemaOut(BaseModel):
    tables: list[SchemaTable]


class QueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sql: str
    limit: int = 1000
    offset: int = 0
    instance: str = "company_postgres"
    db: str = "forgehub"
    database_schema: str = Field(default=SCHEMA, alias="schema")


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    elapsed_ms: float
    truncated: bool


class ValidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sql: str
    instance: str = "company_postgres"
    db: str = "forgehub"
    database_schema: str = Field(default=SCHEMA, alias="schema")


class ValidateResult(BaseModel):
    valid: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _table_row_count(db: AsyncSession, table: str, schema: str = SCHEMA) -> int:
    try:
        r = await db.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"'))
        return r.scalar() or 0
    except Exception:
        return -1


async def _get_fk_map(db: AsyncSession, schema: str = SCHEMA) -> dict[str, list[dict]]:
    """Return FK info keyed by table_name."""
    q = text("""
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name  AS ref_table,
            ccu.column_name AS ref_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema   = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = :schema
        ORDER BY tc.table_name, kcu.column_name
    """)
    rows = (await db.execute(q, {"schema": schema})).fetchall()
    result: dict[str, list[dict]] = {}
    for table, col, ref_table, ref_col in rows:
        result.setdefault(table, []).append(
            {"column": col, "ref_table": ref_table, "ref_column": ref_col}
        )
    return result


async def _get_pk_set(db: AsyncSession, schema: str = SCHEMA) -> dict[str, set[str]]:
    """Return set of PK columns keyed by table_name."""
    q = text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = :schema
    """)
    rows = (await db.execute(q, {"schema": schema})).fetchall()
    result: dict[str, set[str]] = {}
    for table, col in rows:
        result.setdefault(table, set()).add(col)
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/tables", response_model=list[TableSummary])
async def list_tables(
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """List all tables in the given schema with row counts."""
    q = text("""
        SELECT table_name, COUNT(*) OVER () AS total
        FROM information_schema.tables
        WHERE table_schema = :schema
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    rows = (await db.execute(q, {"schema": schema})).fetchall()
    tables = [r[0] for r in rows]

    col_q = text("""
        SELECT table_name, COUNT(*) AS col_count
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = ANY(:tables)
        GROUP BY table_name
    """)
    col_rows = (await db.execute(col_q, {"schema": schema, "tables": tables})).fetchall()
    col_counts = {r[0]: r[1] for r in col_rows}

    result = []
    for table in tables:
        cnt = await _table_row_count(db, table, schema)
        result.append(TableSummary(
            name=table,
            row_count=cnt,
            column_count=col_counts.get(table, 0),
        ))
    return result


@router.get("/tables/{table}", response_model=TableDetail)
async def get_table_detail(
    table: str,
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """Return column details, indexes, and foreign keys for one table."""
    col_q = text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
    """)
    col_rows = (await db.execute(col_q, {"schema": schema, "table": table})).fetchall()
    if not col_rows:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found in schema '{schema}'")

    pk_map = await _get_pk_set(db, schema)
    fk_map = await _get_fk_map(db, schema)
    pk_cols = pk_map.get(table, set())
    fk_list = fk_map.get(table, [])
    fk_col_map = {fk["column"]: f"{fk['ref_table']}.{fk['ref_column']}" for fk in fk_list}

    columns = [
        ColumnInfo(
            name=r[0],
            data_type=r[1],
            is_nullable=r[2] == "YES",
            column_default=r[3],
            is_primary_key=r[0] in pk_cols,
            is_foreign_key=r[0] in fk_col_map,
            references=fk_col_map.get(r[0]),
        )
        for r in col_rows
    ]

    idx_q = text("""
        SELECT
            i.relname AS index_name,
            ix.indisunique,
            ix.indisprimary,
            array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) AS cols
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE t.relname = :table AND n.nspname = :schema
        GROUP BY i.relname, ix.indisunique, ix.indisprimary
        ORDER BY i.relname
    """)
    idx_rows = (await db.execute(idx_q, {"schema": schema, "table": table})).fetchall()
    indexes = [
        IndexInfo(name=r[0], is_unique=r[1], is_primary=r[2], columns=list(r[3]))
        for r in idx_rows
    ]

    row_count = await _table_row_count(db, table, schema)
    return TableDetail(name=table, row_count=row_count, columns=columns, indexes=indexes, foreign_keys=fk_list)


@router.get("/schema", response_model=SchemaOut)
async def get_schema(
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """Return full schema (tables + columns + FKs) for ER diagram generation."""
    tbl_q = text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = :schema AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = [r[0] for r in (await db.execute(tbl_q, {"schema": schema})).fetchall()]

    col_q = text("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = :schema
        ORDER BY table_name, ordinal_position
    """)
    col_rows = (await db.execute(col_q, {"schema": schema})).fetchall()

    pk_map = await _get_pk_set(db, schema)
    fk_map = await _get_fk_map(db, schema)

    cols_by_table: dict[str, list[dict]] = {}
    for tbl, col, dtype, nullable in col_rows:
        pk_cols = pk_map.get(tbl, set())
        fk_col_map = {fk["column"]: fk["ref_table"] for fk in fk_map.get(tbl, [])}
        cols_by_table.setdefault(tbl, []).append({
            "name": col,
            "type": dtype,
            "nullable": nullable == "YES",
            "pk": col in pk_cols,
            "fk_to": fk_col_map.get(col),
        })

    result = []
    for tbl in tables:
        result.append(SchemaTable(
            name=tbl,
            columns=cols_by_table.get(tbl, []),
            foreign_keys=fk_map.get(tbl, []),
        ))
    return SchemaOut(tables=result)


@router.post("/validate", response_model=ValidateResult)
async def validate_query(payload: ValidateRequest) -> ValidateResult:
    """Parse-check SQL using EXPLAIN — never executes, returns {valid, error}.

    Always returns HTTP 200 so the frontend can consume the result directly.
    """
    sql = payload.sql.strip()
    if not sql:
        return ValidateResult(valid=False, error="Query vazia")
    if not _ALLOWED_STARTS.match(sql):
        return ValidateResult(valid=False, error="Only SELECT, WITH and EXPLAIN are allowed")

    factory = _get_session_factory(payload.instance, payload.db)
    # If the user already typed EXPLAIN, run as-is; otherwise prepend it.
    if re.match(r"^\s*explain\b", sql, re.IGNORECASE):
        explain_sql = sql
    else:
        explain_sql = f"EXPLAIN (FORMAT TEXT) {sql}"

    try:
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {payload.database_schema}, public"))
            await session.execute(text(explain_sql))
        return ValidateResult(valid=True)
    except Exception as exc:
        # Walk to the root asyncpg exception which has a clean .message attr
        cause: BaseException = exc
        while getattr(cause, "__cause__", None):
            cause = cause.__cause__  # type: ignore[assignment]
        msg = str(getattr(cause, "message", None) or cause)
        # Strip SQLAlchemy boilerplate prefix if present
        msg = re.sub(r"^\(.*?\) ", "", msg).strip()
        return ValidateResult(valid=False, error=msg or "Syntax error")


@router.post("/query", response_model=QueryResult)
async def execute_query(payload: QueryRequest):
    """Execute a read-only SQL query and return columns + rows.

    Only SELECT, WITH, and EXPLAIN statements are allowed (§ safety rule).
    Results are capped at 500 rows to protect against accidental full-table dumps.
    Instance and database are specified in the request body.
    """
    factory = _get_session_factory(payload.instance, payload.db)
    sql = payload.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="Query is empty")
    if not _ALLOWED_STARTS.match(sql):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT, WITH, and EXPLAIN statements are allowed",
        )

    limit = min(payload.limit, _MAX_ROWS)
    offset = max(0, payload.offset)

    # Wrap in a subquery with LIMIT/OFFSET to cap rows without breaking CTEs
    safe_sql = f"SELECT * FROM ({sql}) __q LIMIT {limit + 1} OFFSET {offset}"

    try:
        t0 = time.perf_counter()
        async with factory() as session:
            await session.execute(text(f"SET search_path TO {payload.database_schema}, public"))
            result = await session.execute(text(safe_sql))
        elapsed = (time.perf_counter() - t0) * 1000

        columns = list(result.keys())
        raw_rows = result.fetchall()
        truncated = len(raw_rows) > limit
        rows = [list(r) for r in raw_rows[:limit]]

        # Serialise non-JSON-native types
        serialised = []
        for row in rows:
            serialised.append([
                str(v) if v is not None and not isinstance(v, (str, int, float, bool)) else v
                for v in row
            ])

        return QueryResult(
            columns=columns,
            rows=serialised,
            row_count=len(serialised),
            elapsed_ms=round(elapsed, 2),
            truncated=truncated,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Functions / Procedures
# ---------------------------------------------------------------------------

class FunctionSummary(BaseModel):
    name: str
    return_type: str
    language: str
    kind: str  # "function" or "procedure"
    arg_types: str


class FunctionDetail(FunctionSummary):
    source: str


class FunctionCreate(BaseModel):
    source: str  # Full CREATE OR REPLACE FUNCTION … body


@router.get("/functions", response_model=list[FunctionSummary])
async def list_functions(
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """List all user-defined functions and procedures in the given schema."""
    q = text("""
        SELECT
            p.proname                                      AS name,
            pg_catalog.pg_get_function_result(p.oid)      AS return_type,
            l.lanname                                      AS language,
            CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END AS kind,
            pg_catalog.pg_get_function_arguments(p.oid)   AS arg_types
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE n.nspname = :schema
          AND p.prokind IN ('f', 'p')
        ORDER BY p.proname
    """)
    rows = (await db.execute(q, {"schema": schema})).fetchall()
    return [FunctionSummary(name=r[0], return_type=r[1] or "", language=r[2], kind=r[3], arg_types=r[4] or "") for r in rows]


@router.get("/functions/{name}", response_model=FunctionDetail)
async def get_function(
    name: str,
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """Return the full source definition of a function/procedure."""
    q = text("""
        SELECT
            p.proname,
            pg_catalog.pg_get_function_result(p.oid),
            l.lanname,
            CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END,
            pg_catalog.pg_get_function_arguments(p.oid),
            pg_catalog.pg_get_functiondef(p.oid)
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE n.nspname = :schema AND p.proname = :name
        LIMIT 1
    """)
    row = (await db.execute(q, {"schema": schema, "name": name})).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found in schema '{schema}'")
    return FunctionDetail(name=row[0], return_type=row[1] or "", language=row[2], kind=row[3], arg_types=row[4] or "", source=row[5] or "")


@router.post("/functions", status_code=status.HTTP_201_CREATED)
async def create_or_replace_function(payload: FunctionCreate, db: AsyncSession = Depends(get_db)):
    """Create or replace a function/procedure using the provided source definition.

    The source must be a valid CREATE [OR REPLACE] FUNCTION / PROCEDURE statement.
    """
    src = payload.source.strip()
    if not re.match(r"^\s*create\b", src, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Source must start with CREATE")
    try:
        await db.execute(text(src))
        await db.commit()
        return {"ok": True, "message": "Function created/replaced successfully"}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/functions/{name}", status_code=status.HTTP_200_OK)
async def drop_function(name: str, db: AsyncSession = Depends(get_db)):
    """Drop a function (uses CASCADE). Only drops functions in the company schema."""
    # Validate name is a plain identifier
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise HTTPException(status_code=400, detail="Invalid function name")
    try:
        await db.execute(text(f'DROP FUNCTION IF EXISTS {SCHEMA}."{name}" CASCADE'))
        await db.commit()
        return {"ok": True, "message": f"Function '{name}' dropped"}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Indexes (global view + create + drop)
# ---------------------------------------------------------------------------

class IndexGlobal(BaseModel):
    name: str
    table_name: str
    columns: str
    is_unique: bool
    is_primary: bool
    index_def: str


class IndexCreate(BaseModel):
    table_name: str
    column_names: list[str]
    index_name: str | None = None
    unique: bool = False


@router.get("/indexes", response_model=list[IndexGlobal])
async def list_indexes(
    db: AsyncSession = Depends(_get_dynamic_db),
    schema: str = Query(default=SCHEMA, description="PostgreSQL schema name"),
):
    """Return all indexes across all tables in the given schema."""
    q = text("""
        SELECT
            i.relname                                              AS index_name,
            t.relname                                              AS table_name,
            array_to_string(
                array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)), ', ')
                                                                   AS columns,
            ix.indisunique,
            ix.indisprimary,
            pg_get_indexdef(ix.indexrelid)                         AS index_def
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE n.nspname = :schema
        GROUP BY i.relname, t.relname, ix.indisunique, ix.indisprimary, ix.indexrelid
        ORDER BY t.relname, i.relname
    """)
    rows = (await db.execute(q, {"schema": schema})).fetchall()
    return [IndexGlobal(name=r[0], table_name=r[1], columns=r[2], is_unique=r[3], is_primary=r[4], index_def=r[5]) for r in rows]


@router.post("/indexes", status_code=status.HTTP_201_CREATED)
async def create_index(payload: IndexCreate, db: AsyncSession = Depends(get_db)):
    """Create a new index on a table in the company schema.

    Generates a safe CREATE [UNIQUE] INDEX statement from structured parameters.
    """
    tbl = payload.table_name
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", tbl):
        raise HTTPException(status_code=400, detail="Invalid table name")
    for col in payload.column_names:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            raise HTTPException(status_code=400, detail=f"Invalid column name: {col}")
    cols_sql = ", ".join(f'"{c}"' for c in payload.column_names)
    idx_name = payload.index_name or f"idx_{tbl}_{'_'.join(payload.column_names)}"
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", idx_name):
        raise HTTPException(status_code=400, detail="Invalid index name")
    unique_kw = "UNIQUE " if payload.unique else ""
    sql = f'CREATE {unique_kw}INDEX IF NOT EXISTS "{idx_name}" ON {SCHEMA}."{tbl}" ({cols_sql})'
    try:
        await db.execute(text(sql))
        await db.commit()
        return {"ok": True, "name": idx_name, "sql": sql}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/indexes/{name}", status_code=status.HTTP_200_OK)
async def drop_index(name: str, db: AsyncSession = Depends(get_db)):
    """Drop an index by name (schema-qualified). Cannot drop primary key indexes."""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise HTTPException(status_code=400, detail="Invalid index name")
    # Refuse to drop PK indexes
    chk = text("""
        SELECT ix.indisprimary FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = (SELECT relnamespace FROM pg_class WHERE oid = ix.indrelid)
        WHERE i.relname = :name AND n.nspname = :schema
    """)
    row = (await db.execute(chk, {"name": name, "schema": SCHEMA})).fetchone()
    if row and row[0]:
        raise HTTPException(status_code=400, detail="Cannot drop a primary key index")
    try:
        await db.execute(text(f'DROP INDEX IF EXISTS {SCHEMA}."{name}"'))
        await db.commit()
        return {"ok": True, "message": f"Index '{name}' dropped"}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Tables — create via structured column definitions
# ---------------------------------------------------------------------------

class ColumnDef(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    default: str | None = None


class TableCreate(BaseModel):
    name: str
    columns: list[ColumnDef]


_SAFE_TYPE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_ ()\[\]]*$")
_SAFE_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@router.post("/tables", status_code=status.HTTP_201_CREATED)
async def create_table(payload: TableCreate, db: AsyncSession = Depends(get_db)):
    """Create a new table from structured column definitions.

    The backend generates the CREATE TABLE statement — no raw SQL input.
    """
    tbl = payload.name
    if not _SAFE_IDENT_RE.match(tbl):
        raise HTTPException(status_code=400, detail="Invalid table name")
    col_parts = []
    pk_cols = []
    for col in payload.columns:
        if not _SAFE_IDENT_RE.match(col.name):
            raise HTTPException(status_code=400, detail=f"Invalid column name: {col.name}")
        if not _SAFE_TYPE_RE.match(col.type):
            raise HTTPException(status_code=400, detail=f"Invalid type: {col.type}")
        part = f'    "{col.name}" {col.type}'
        if not col.nullable:
            part += " NOT NULL"
        if col.default:
            # Only allow safe default expressions
            if re.search(r"[;'\"]", col.default):
                raise HTTPException(status_code=400, detail=f"Unsafe default for {col.name}")
            part += f" DEFAULT {col.default}"
        col_parts.append(part)
        if col.primary_key:
            pk_cols.append(f'"{col.name}"')
    if pk_cols:
        col_parts.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")
    col_sql = ",\n".join(col_parts)
    sql = f'CREATE TABLE {SCHEMA}."{tbl}" (\n{col_sql}\n)'
    try:
        await db.execute(text(sql))
        await db.commit()
        return {"ok": True, "table": tbl, "sql": sql}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
