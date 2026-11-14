"""Fictitious verified credentials for authorization tests; never used for SSH."""
import base64
import uuid
from datetime import datetime, timezone


def mark_managed_machine(server):
    # Public bytes identify only a test fixture; no private key exists.
    blob = b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + uuid.uuid4().bytes + uuid.uuid4().bytes
    server.remote_user = 'darckware'
    server.public_key = 'ssh-ed25519 ' + base64.b64encode(blob).decode()
    server.ssh_key_ref = str(uuid.uuid4())
    server.login_password_ref = str(uuid.uuid4())
    server.access_verified_at = datetime.now(timezone.utc)
    return server
