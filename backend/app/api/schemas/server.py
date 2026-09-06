"""Pydantic schemas for the Server domain."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=1, max_length=100)
    remote_user: str = Field(min_length=1, max_length=100)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_key_path: str | None = Field(default=None, max_length=500)
    # Write-only: encrypted on arrival and never echoed back (ServerOut carries
    # the key_passphrase_stored boolean instead).
    key_passphrase: str | None = None
    access_enabled: bool = True
    environment: Literal["vps", "semed"] = "semed"
    description: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, min_length=1, max_length=100)
    remote_user: str | None = Field(default=None, min_length=1, max_length=100)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_key_path: str | None = Field(default=None, max_length=500)
    # Three distinct intents, which is why the field is write-only and
    # tri-state: omitted -> keep whatever is stored (the form cannot re-send a
    # passphrase it never received); "" or null -> clear it; a value -> replace
    # it. update_server reads it through model_dump(exclude_unset=True), so
    # "omitted" and "explicitly null" stay distinguishable.
    key_passphrase: str | None = None
    access_enabled: bool | None = None
    environment: Literal["vps", "semed"] | None = None
    description: str | None = None


class ServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    ip_address: str
    remote_user: str
    ssh_port: int
    ssh_key_path: str | None
    public_key: str | None
    # Whether an encrypted copy of the identity file is vaulted on the row.
    # The material itself is never serialized -- see Server.private_key_stored.
    private_key_stored: bool = False
    # Whether a passphrase for that key is on file. Also never serialized.
    key_passphrase_stored: bool = False
    # ForgeHub-side access switch: false parks the server (no probe, no
    # terminal) without touching any key -- see Server.access_enabled.
    access_enabled: bool = True
    environment: str = "semed"
    description: str | None
    created_at: datetime
    updated_at: datetime


class ServerDetailOut(ServerOut):
    """Single-server read. Carries the decrypted key passphrase, which the list
    never does -- same shape as AgentDetailOut's forgerouter_api_key, and for
    the same reason: the field is edited in a card that shows the current value
    behind an eye toggle, so the form has to receive it. The route is
    admin-only.
    """

    key_passphrase: str | None = None


class ServerKeyStoreRequest(BaseModel):
    """A pasted private key, for a server whose identity file ForgeHub cannot
    read from the host (a key that lives on another machine, or one being
    recovered from a backup by hand)."""

    private_key: str = Field(min_length=1)
    public_key: str | None = None


class ServerKeyVaultResult(BaseModel):
    """Outcome of a vault action (backup / restore). `key_path` is the host
    path read from or written to; `written` lists the files a restore
    actually created."""

    server_id: uuid.UUID
    private_key_stored: bool
    key_path: str | None = None
    written: list[str] = Field(default_factory=list)


class ServerInstallKeyRequest(BaseModel):
    """Credentials for the one-shot key installation (see install_server_key
    in api/routes/server.py). The password is used only for this request's
    ssh login on the host and is never persisted or logged.

    Two modes:
      - admin_user set  -> log in with the server admin account (root or a
        sudo user), CREATE remote_user on the server if missing, then install
        the key into its authorized_keys. `password` is the admin's password.
      - admin_user unset -> classic ssh-copy-id as remote_user itself (the
        account must already exist); `password` is remote_user's password.
    """

    password: str = Field(min_length=1)
    # The key owner on the server (the login account the key enables, e.g.
    # "aegis"). Defaults to the row's remote_user. When it differs, it also
    # becomes the row's remote_user so status/terminal match afterwards.
    remote_user: str | None = Field(default=None, min_length=1, max_length=100)
    # Server admin account used to create the user / install the key.
    admin_user: str | None = Field(default=None, min_length=1, max_length=100)


class ServerInstallKeyResult(BaseModel):
    ok: bool
    steps: list[str]
    error: str | None = None
    failed_step: str | None = None
    key_path: str | None = None
    public_key: str | None = None


class ServerImportRequest(BaseModel):
    """Raw CSV text, header row required:
    SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION
    """
    csv_text: str = Field(min_length=1)


class ServerImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str]


class ServerCheckResult(BaseModel):
    """Result of an on-demand SSH reachability probe (see `check_server_status`
    in api/routes/server.py) -- never persisted, always computed live.

    status:
      "no_key"  -- no ssh_key_path configured on the server row, so key-based
                   auth can't be attempted (a raw TCP probe still runs, but a
                   missing key is reported first since it's the actionable
                   fix).
      "online"  -- TCP connect + SSH handshake + key auth all succeeded.
      "unreachable" -- the host did not answer on the SSH path.
      "auth_failed" -- the host answered but rejected/unlocked no usable key.
      "key_missing" -- the configured identity file does not exist.
      "offline" -- another SSH transport failure that could not be classified.
      "disabled" -- access_enabled is false, so nothing was probed at all.
                   Distinct from "offline" on purpose: the server may well be
                   up, ForgeHub is simply not using it.
    """

    server_id: uuid.UUID
    status: Literal[
        "online",
        "offline",
        "unreachable",
        "auth_failed",
        "key_missing",
        "no_key",
        "disabled",
    ]
    detail: str


class ServerServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    port: int = Field(ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    # Normalised to a leading slash (or None) by the route -- "admin" and
    # "/admin" mean the same thing to whoever types it.
    path: str | None = Field(default=None, max_length=255)
    description: str | None = None


class ServerServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    port: int | None = Field(default=None, ge=1, le=65535)
    scheme: Literal["http", "https"] | None = None
    path: str | None = Field(default=None, max_length=255)
    description: str | None = None


class ServerServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    name: str
    port: int
    scheme: str
    path: str | None
    description: str | None
    # Built by the route from the parent server's current address, never
    # stored: a server that changes IP must not leave a set of URLs pointing
    # at the old one.
    url: str
    created_at: datetime
    updated_at: datetime


class ServerPortScanEntry(BaseModel):
    port: int
    scheme: Literal["http", "https"]
    # Whether this port is already registered as a service on the row.
    registered: bool
    # False for ports that answer TCP but are not a web endpoint (a database,
    # a message broker). Reported rather than hidden -- knowing Postgres is
    # listening is useful -- but the UI must not offer it as a link, since
    # http://host:5432 opens nothing.
    likely_web: bool = True


class ServerPortScanResult(BaseModel):
    """Ports that answered a TCP connect, in the order scanned.

    A finding is a suggestion, never a row: nothing is persisted by a scan.
    An open port says something is listening, not what it is, so naming it is
    left to whoever registers it.
    """

    server_id: uuid.UUID
    scanned: int
    open_ports: list[ServerPortScanEntry]
