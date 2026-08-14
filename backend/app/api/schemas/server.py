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
    description: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, min_length=1, max_length=100)
    remote_user: str | None = Field(default=None, min_length=1, max_length=100)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_key_path: str | None = Field(default=None, max_length=500)
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
    description: str | None
    created_at: datetime
    updated_at: datetime


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
      "offline" -- unreachable, connection refused, or the key was rejected.
    """

    server_id: uuid.UUID
    status: Literal["online", "offline", "no_key"]
    detail: str
