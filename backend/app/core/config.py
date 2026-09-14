"""Application settings loaded from environment variables / .env /
forgehub.config.

This is the single source of truth for configuration. Every other module
(db.base, core.security, alembic/env.py) must import `settings` from here
instead of reading os.environ directly.
"""
from functools import lru_cache
from pathlib import Path

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), str(_APP_CONFIG_FILE)),
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

    # Nexo Remote Agent artifacts are built by the host bridge and exposed to
    # this backend beneath a separate, read-only mount root.
    NEXO_ARTIFACT_ROOT: Path = Path("/tmp/forgehub-nexo-artifacts")
    NEXO_INGESTION_URL: str = ""

    # ForgeRouter dashboard SSO (see api/routes/forgerouter.py). URL is the
    # backend-to-backend address; the browser reaches ForgeRouter directly
    # via VITE_FORGEROUTER_URL on the frontend side.
    FORGEROUTER_URL: str = "http://host.docker.internal:2100"
    FORGEROUTER_SSO_SECRET: str = ""

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
    # entry covers all of them; Aramis/Porthus/Dartan/Vector each get their
    # own runtime's root since they aren't Hermes profiles.
    AGENT_RUNTIME_PATHS: dict[str, str] = {
        "hermes": "/root/.hermes",
        "claude": "/root",
        "codex": "/root",
        "agy": "/root",
        "openclaw": "/root/.openclaw",
    }
    GIT_CONTROL_DEFAULT_REPO: str = "hermes"
    BACKUP_ROOT: str = "/root/backup"
    # Host path, written through the host-bridge, from which Headscale loads
    # the ForgeHub-managed file-mode ACL policy.
    HEADSCALE_ACL_POLICY_PATH: str = "/etc/headscale/acl-policy.hujson"
    HEADSCALE_ADMIN_PRINCIPAL: str = "marcelo@"
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
        """Build a connection URL for an arbitrary PostgreSQL instance."""
        effective_password = password or self.FOUNDATION_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD
        effective_user = user or self.FOUNDATION_POSTGRES_USER or self.POSTGRES_USER
        return f"postgresql+asyncpg://{effective_user}:{effective_password}@{host}:{port}/{db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
