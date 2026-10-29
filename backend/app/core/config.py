"""Application settings loaded from environment variables / .env /
forgehub.config.

This is the single source of truth for configuration. Every other module
(db.base, core.security, alembic/env.py) must import `settings` from here
instead of reading os.environ directly.

ENVIRONMENT=test (Plano Integrado T.1, 2026-10-28) switches the process to
the isolated test Postgres (`test-env/`): the repo-root `.env` -- production
credentials and integration tokens -- is not loaded at all, `test-env/.env.test`
is, and Settings refuses to build unless the database target is on the test
allowlist. The refusal happens while the settings object is constructed, i.e.
before db/base.py can create an engine, so no connection is ever attempted.
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root, two levels up from backend/app/core/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"
# ForgeHub's own operational defaults (paths/behavior, not credentials) --
# see forgehub.config's own header comment for why this is split out from
# .env. Loaded second so a value set there overrides the same key in .env
# (pydantic-settings' env_file tuple: later files win); in practice the two
# files don't share keys today.
_APP_CONFIG_FILE = _REPO_ROOT / "forgehub.config"
# Isolated test database (test-env/docker-compose.yml). Out of git; the
# versioned template is test-env/.env.test.example.
TEST_ENV_FILE = _REPO_ROOT / "test-env" / ".env.test"

TEST_ENVIRONMENT = "test"

# The only (host, port, database, user) targets a test process may reach.
# An allowlist, not just the denylist below: any target nobody listed --
# another app's instance, a typo, a new production port -- is refused too.
# The container-name entry (T.2) is how forgehub_test_backend reaches the
# same instance from inside forgehub_test_network, which is `internal` and
# has no route to the host: that name only resolves on that network.
TEST_DATABASE_ALLOWLIST: frozenset[tuple[str, int, str, str]] = frozenset({
    ("127.0.0.1", 5439, "forgehub_test", "forgehub_test"),
    ("localhost", 5439, "forgehub_test", "forgehub_test"),
    ("forgehub_test_postgres", 5432, "forgehub_test", "forgehub_test"),
})
# Known production markers, reported by name so the refusal says *why*.
PRODUCTION_DATABASE_PORTS = frozenset({5433})
PRODUCTION_DATABASE_HOSTS = frozenset({"forgehub_postgres"})
PRODUCTION_DATABASE_NAMES = frozenset({"forgehub"})
PRODUCTION_DATABASE_USERS = frozenset({"foundation"})


class UnsafeDatabaseTargetError(RuntimeError):
    """A test process was pointed at a database outside the test allowlist.

    A RuntimeError, not a ValueError, so pydantic lets it propagate as-is
    instead of folding it into a ValidationError."""


def is_test_environment(value: str | None) -> bool:
    return (value or "").strip().lower() == TEST_ENVIRONMENT


def assert_test_database_target(host: str, port: int, database: str, user: str) -> None:
    """Raise UnsafeDatabaseTargetError unless the target is on the test
    allowlist. Pure check -- never opens a connection. The password is not
    an input, so it can never end up in the error message."""
    normalized_host = (host or "").strip().lower()
    reasons = []
    if port in PRODUCTION_DATABASE_PORTS:
        reasons.append(f"port {port} is production")
    if normalized_host in PRODUCTION_DATABASE_HOSTS:
        reasons.append(f"host {normalized_host!r} is production")
    if database in PRODUCTION_DATABASE_NAMES:
        reasons.append(f"database {database!r} is production")
    if user in PRODUCTION_DATABASE_USERS:
        reasons.append(f"user {user!r} is production")
    if (normalized_host, port, database, user) not in TEST_DATABASE_ALLOWLIST:
        reasons.append("target is not on the test allowlist (forgehub_test@127.0.0.1:5439, or forgehub_test_postgres:5432 inside the test network)")
    if reasons:
        raise UnsafeDatabaseTargetError(
            f"ENVIRONMENT=test refuses database {user}@{normalized_host}:{port}/{database}: "
            + "; ".join(reasons)
        )


def _env_files() -> tuple[str, ...]:
    # Decided from the process environment, before any file is read: a test
    # process must never load the production .env, not even to override it.
    if is_test_environment(os.environ.get("ENVIRONMENT")):
        return (str(_APP_CONFIG_FILE), str(TEST_ENV_FILE))
    return (str(_ENV_FILE), str(_APP_CONFIG_FILE))


# Response languages the in-app AI chat can be pinned to (Settings -> AI
# chat). Key = value stored in CHAT_RESPONSE_LANGUAGE; value = the hidden
# instruction api/routes/chat.py appends to each outgoing agent call.
# Adding a language here is all the backend needs -- the config PUT
# validator (api/routes/system_control.py) derives from these keys; add
# the matching label to the frontend dropdown's CHAT_RESPONSE_LANGUAGES
# (pages/settings/index.tsx), which mirrors this dict.
CHAT_RESPONSE_LANGUAGE_NOTES: dict[str, str] = {
    "pt-BR": "(Instrução do sistema — responda sempre em português do Brasil.)",
    "en": "(System instruction — always respond in English.)",
    "es": "(Instrucción del sistema — responde siempre en español.)",
    "fr": "(Instruction système — répondez toujours en français.)",
    "de": "(Systemanweisung — antworte immer auf Deutsch.)",
    "it": "(Istruzione di sistema — rispondi sempre in italiano.)",
}

# Existing installations may still have another language saved. Keep its
# instruction available, but offer only the three supported product languages
# for new selections. A legacy value can pass through an unrelated config
# save until an administrator chooses one of the supported languages.
SUPPORTED_CHAT_RESPONSE_LANGUAGES = ("pt-BR", "en", "es")


def chat_response_language_allowed(value: str, current: str) -> bool:
    return value in SUPPORTED_CHAT_RESPONSE_LANGUAGES or (
        value == current and value in CHAT_RESPONSE_LANGUAGE_NOTES
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ForgeHub PostgreSQL instance.
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "foundation"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "forgehub"
    POSTGRES_SCHEMA: str = "company"

    # Auth
    JWT_SECRET: str = "dev_only_insecure_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Deployment environment label -- controls whether FastAPI's own
    # auto-generated docs (/docs, /redoc, /openapi.json) are served (see
    # app/main.py). Fail-closed default: an unset/unrecognized value (e.g.
    # "production", or nothing at all) disables them. Only "development",
    # "dev", "homolog"/"homologacao" or "staging" turn them on -- this host
    # is reachable from the public internet (forgehub.darckware.net), and
    # the schema would publish every route's shape.
    ENVIRONMENT: str = "production"

    # Google reCAPTCHA v2 (login screen, see api/routes/auth.py +
    # core/recaptcha.py). Empty = feature off (fail-open, same convention as
    # darckware's app/core/recaptcha.py) -- set once a key pair is
    # provisioned in the Google reCAPTCHA admin console for
    # forgehub.darckware.net.
    RECAPTCHA_SECRET_KEY: str = ""

    # Temporary single hardcoded dev user — placeholder until a real
    # Users/Auth domain exists (out of scope for this foundation step).
    DEV_USER_USERNAME: str = "admin"
    DEV_USER_PASSWORD: str = "admin"

    # Chat bridge (host-bridge/app.py) -- the real Hermes agents only exist
    # as host processes, so chat messages are proxied there over HTTP.
    CHAT_BRIDGE_URL: str = "http://host.docker.internal:8910"
    CHAT_BRIDGE_TOKEN: str = ""

    # Opt-in only: owner UUID, fixed source-agent UUID -> proposal-store file,
    # and Telegram destination are administered outside agent requests.
    MOODLE_APPROVAL_ENABLED: bool = False
    MOODLE_APPROVAL_OWNER_ID: str = ""
    MOODLE_APPROVAL_SOURCE_FILES: str = "{}"
    MOODLE_APPROVAL_WORKING_PATH: str = ""
    MOODLE_APPROVAL_TELEGRAM_CHAT_ID: str = ""
    MOODLE_APPROVAL_FORM_URL: str = ""

    # HMAC secret the agent runtimes sign their activity webhooks with
    # (POST /api/v1/agent-activity/events). The same value lives in each Hermes
    # profile's .env as FORGEHUB_ACTIVITY_WEBHOOK_SECRET. Empty = the endpoint
    # refuses every event (fail-closed: it is reachable without a JWT).
    AGENT_ACTIVITY_WEBHOOK_SECRET: str = ""

    # ForgeRouter dashboard SSO (see api/routes/forgerouter.py). URL is the
    # backend-to-backend address; the browser reaches ForgeRouter directly
    # via VITE_FORGEROUTER_URL on the frontend side. Container name on
    # foundation_network: ForgeRouter publishes 2100 on the host's 127.0.0.1
    # only, so host.docker.internal:2100 never connected (found 2026-10-14
    # when translation timed out; the SSO call shared the same dead address).
    FORGEROUTER_URL: str = "http://forgerouter:2100"
    FORGEROUTER_SSO_SECRET: str = ""

    # Darckware CRM (client demands, contracts, outbound e-mail queue -- see
    # api/routes/client_ops.py). Darckware stores, ForgeHub operates. Two
    # credentials on purpose: the agent token is the same one Lara's MCP uses
    # (read/write), the approver token is ForgeHub-only and is what lets an
    # e-mail to a client actually leave -- the drafter can never approve.
    # Empty URL and token (or unreadable token file) = integration off (routes answer 503).
    DARCKWARE_API_URL: str = "http://darckware-backend:8020"
    DARCKWARE_AGENT_TOKEN: str = ""
    DARCKWARE_AGENT_TOKEN_FILE: str = ""
    DARCKWARE_APPROVER_TOKEN: str = ""
    # "Traduzir" on a client demand (2026-10-14): a plain ForgeRouter chat
    # completion billed to this agent's own key -- Lara, who owns the client
    # mailbox. Not a Hermes turn: a translation has no tools and must not
    # land in the agent's memory.
    CLIENT_OPS_TRANSLATOR_AGENT: str = "lara"
    CLIENT_OPS_TRANSLATOR_MODEL: str = "forgerouter/standard"
    # The Maia's per-message context pass over her WhatsApp contacts (core/personal_context.py):
    # one completion per incoming message, billed to her own ForgeRouter key.
    PERSONAL_CONTEXT_AGENT: str = "maia"
    PERSONAL_CONTEXT_MODEL: str = "forgerouter/standard"
    # Where the Maia's WhatsApp plugin keeps its runtime state (pausas.json, tarefas.json) --
    # read-only here, for the Pessoal screen's "Maia" tab. Bind mount of /root/.hermes/profiles.
    PERSONAL_WHATSAPP_STATE_DIR: str = "/profiles/maia/whatsapp"

    # Optional Open-Meteo integration for Pessoal. No API key is required;
    # missing coordinates use Rio de Janeiro as the temporary default.
    WEATHER_ENABLED: bool = False
    WEATHER_LATITUDE: float | None = None
    WEATHER_LONGITUDE: float | None = None
    WEATHER_LOCATION: str = ""
    WEATHER_TIMEZONE: str = "America/Sao_Paulo"
    WEATHER_API_URL: str = "https://api.open-meteo.com/v1/forecast"

    # Hindsight/Foundation PostgreSQL instance.
    FOUNDATION_POSTGRES_HOST: str = "hindsight_postgres"
    FOUNDATION_POSTGRES_PORT: int = 5432
    FOUNDATION_POSTGRES_USER: str = "foundation"
    FOUNDATION_POSTGRES_PASSWORD: str = ""  # falls back to POSTGRES_PASSWORD when empty

    # ForgeRouter PostgreSQL instance.
    FORGEROUTER_POSTGRES_HOST: str = "forgerouter_postgres"
    FORGEROUTER_POSTGRES_PORT: int = 5432
    FORGEROUTER_POSTGRES_USER: str = "proxyrouter_user"
    FORGEROUTER_POSTGRES_PASSWORD: str = ""  # falls back to POSTGRES_PASSWORD when empty

    # System Control (api/routes/system_control.py) -- see forgehub.config
    # for the operator-facing explanation of each of these.
    HERMES_SOURCE_PATH: str = "/root/.hermes"
    # Root config/state directory per agent runtime, for reference/visibility
    # in Settings -> Agent runtime paths (not consumed by Git Control/Backup
    # -- those stay Project- or HERMES_SOURCE_PATH-driven, see
    # system_control.py's module docstring for why). Keyed by runtime name,
    # not by individual agent -- every Hermes-profile agent (Athos, Aegis,
    # ...) shares HERMES_SOURCE_PATH's tree via /profiles/<slug>, so one
    # entry covers all of them; Aramis/Porthus/Dartan each get their own
    # runtime's root since they aren't Hermes profiles.
    AGENT_RUNTIME_PATHS: dict[str, str] = {
        "hermes": "/root/.hermes",
        "claude": "/root",
        "codex": "/root",
        "agy": "/root",
    }
    GIT_CONTROL_DEFAULT_REPO: str = "hermes"
    BACKUP_ROOT: str = "/root/backup"
    # Trash path passed by System Control to the authoritative Athos cleanup
    # script. The weekly foundation-clear cron invokes that same script with
    # /root/trash as its default, avoiding duplicated cleanup policies.
    TRASH_ROOT: str = "/root/trash"
    CLEANUP_SCAN_ROOT: str = "/"
    # Where files attached to a message are written (api/routes/demand.py).
    # A root of their own, not the Docs mount: an attachment is a message
    # payload, not a document in the browsable Docs tree. Container path by
    # default (docker-compose bind-mounts /root/messages there); set
    # MESSAGE_ATTACHMENTS_ROOT in .env when running the backend directly on
    # the host, so it writes somewhere real instead of creating a directory at
    # the filesystem root -- which is how a stray /docs appeared on this host.
    # Deliberately not in forgehub.config: that file is regenerated by the
    # Settings form, which would drop a key it doesn't know about.
    MESSAGE_ATTACHMENTS_ROOT: str = "/messages"
    # /var/lib/docker is pruned by path (not just excludable by depth) because
    # it is reproducible container/image/overlay storage the Cleanup card was
    # never going to surface as a candidate anyway -- walking it just adds
    # several seconds of dead I/O to every scan (2026-08-29, confirmed via a
    # standalone `find` timing: ~5.6GB, cutting several seconds off a cold-cache
    # scan when excluded).
    CLEANUP_PRUNE_PATHS: list[str] = ["/mnt", "/proc", "/sys", "/dev", "/run", "/var/lib/docker"]
    CLEANUP_PRUNE_NAMES: list[str] = [
        "node_modules", ".git", "venv", ".venv", "site-packages", "__pycache__",
    ]
    # Language the in-app AI chat (Workspace tabs + Assistant drawer)
    # should answer in -- "pt-BR" or "en". Applied by api/routes/chat.py as
    # an instruction appended to each outgoing agent call (like the voice
    # brevity note), never stored with the user's message.
    CHAT_RESPONSE_LANGUAGE: str = "pt-BR"
    # App shell language (sidebar, dialogs, forms) new users get on creation
    # -- independent of CHAT_RESPONSE_LANGUAGE above. Only "en"/"pt-BR" (see
    # User.ui_language's CheckConstraint); routes/users.py and auth.py's
    # bootstrap-admin path set User.ui_language from this at creation time.
    # Existing users keep whatever they already have -- this only affects
    # the value a brand new row starts with.
    DEFAULT_UI_LANGUAGE: str = "pt-BR"
    # IANA zone used for wall-clock timestamps ForgeHub itself generates
    # (e.g. backup archive filenames, see system_control.py's _now_local) --
    # independent of the host OS timezone, which the rest of the process
    # (unqualified datetime.now() calls elsewhere, log timestamps, ...)
    # still follows.
    TIMEZONE: str = "America/Sao_Paulo"
    # Name of a service-kind row in ForgeRouter's own registry
    # (ai_router.agents, kind='service' -- e.g. "Hindsight") whose key
    # ProjectsForgeRouterCard's (Dashboard "Projects" card) per-tool "Enter
    # the ForgeRouter API key..." prompt pre-fills automatically -- 2026-07-29,
    # Marcelo: "preciso preencher a API KEY de um agente automaticamente...
    # o agente padrão para ser utilizado nesse recurso... eu adicionei
    # agente do tipo serviço no forgerouter, filtra somente esses". A
    # service has no corresponding ForgeHub Agent row (unlike the
    # kind='agent' rows /sync/forgerouter-keys imports), so this is looked
    # up by name straight against ai_router.agents, not an Agent.id.
    # Empty string = no default set, the prompt stays blank like before.
    DEFAULT_FORGEROUTER_SERVICE_NAME: str = ""

    # Personal domain (tasks, agenda, notes -- api/routes/personal.py, 2026-10-07): besides the
    # admin user, only these agents (profile_slug, comma-separated) may read and write it. Maia is
    # Marcelo's personal assistant; no other agent sees his personal data.
    PERSONAL_AGENT_SLUGS: str = "maia"

    # Agents (profile_slug, comma-separated) that "apply to all agents" catalog MCP servers skip
    # (2026-10-07): Maia, Marcelo's personal assistant, runs least-privilege -- a global forgehub
    # entry would give her every ForgeHub tool and overwrite her filtered (tools.include) entry.
    # A server can still be assigned to her explicitly.
    MCP_GLOBAL_EXCLUDED_SLUGS: str = "maia"

    # How many agent runs may be in flight at once across the whole Messages
    # channel (2026-08-13, Marcelo: "pode definir a quantidade de processo em
    # paralelo, no máximo 5. Vai depender no computador... veja o máximo 20").
    #
    # Before this there was no limit at all: the scheduled pass dispatched
    # every due message in one go, so fifty messages coming due together
    # meant fifty agent CLIs starting on the host at once. Operator-tunable
    # because the right number is a property of the machine, not of ForgeHub
    # -- hence the config file rather than a constant.
    MAX_CONCURRENT_DISPATCHES: int = 5
    # Hard ceiling for the tunable above, applied when the value is read
    # (see api/routes/demand.py's _dispatch_slots). A config file edited by
    # hand can hold anything; this is what actually bounds the host.
    MAX_CONCURRENT_DISPATCHES_CEILING: int = 20

    # The background loops main.py starts (scheduled dispatch to the
    # host-bridge, Telegram feedback, Darckware polling, ForgeRouter key sync,
    # the Maia's context pass, ...). Read through `background_workers_enabled`,
    # never directly: under ENVIRONMENT=test they stay off whatever this says
    # (Plano Integrado T.2) -- a test process must not reach an integration,
    # and simulated integrations (T.3) don't exist yet.
    BACKGROUND_WORKERS_ENABLED: bool = True

    @property
    def background_workers_enabled(self) -> bool:
        return self.BACKGROUND_WORKERS_ENABLED and not is_test_environment(self.ENVIRONMENT)

    @model_validator(mode="after")
    def _refuse_production_database_in_test(self) -> "Settings":
        if is_test_environment(self.ENVIRONMENT):
            assert_test_database_target(
                self.POSTGRES_HOST, self.POSTGRES_PORT, self.POSTGRES_DB, self.POSTGRES_USER
            )
        return self

    @property
    def DATABASE_URL(self) -> str:
        """Async SQLAlchemy connection string (postgresql+asyncpg://...)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def db_url_for(
        self,
        host: str,
        port: int,
        db: str,
        *,
        user: str | None = None,
        password: str | None = None,
    ) -> str:
        """Build a connection URL for an arbitrary PostgreSQL instance.

        Under ENVIRONMENT=test this raises for anything off the test
        allowlist -- the other instances it serves (Hindsight, ForgeRouter)
        are production ones."""
        effective_password = password or self.FOUNDATION_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD
        effective_user = user or self.FOUNDATION_POSTGRES_USER or self.POSTGRES_USER
        if is_test_environment(self.ENVIRONMENT):
            assert_test_database_target(host, port, db, effective_user)
        return f"postgresql+asyncpg://{effective_user}:{effective_password}@{host}:{port}/{db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
