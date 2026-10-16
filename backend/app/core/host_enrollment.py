"""Enrollment scripts: one run on a new station (through RustDesk, as
administrator) leaves it fully in remote support (2026-10-16, Marcelo:
"preciso ter o tailscale instalado e openssh"):

1. Tailscale installed and joined with the client's tag (single-use auth key,
   core/tailscale_api.py), named exactly as the inventory row so ForgeHub
   links the device by name the moment it appears.
2. SSH server on, reachable from the tailnet only (Windows: PowerShell as the
   default shell).
3. Local account `darckware` (administrator; Linux: passwordless sudo, since
   commands run non-interactively) with a strong password generated for this
   station and stored encrypted on its row, and ForgeHub's key authorized.

Idempotent: a station already in the tailnet keeps its connection (only its
name is set), an existing account gets the new password. Values embedded in
the scripts are validated or generated from a quote-free alphabet, so nothing
becomes script syntax. No backslash escapes in these templates other than the
doubled ones -- a "\\v" once became a vertical tab and broke sshd on a station.
"""
import re
import secrets
import string

from app.core.host_preparation import TAILNET_CIDR, _posix_key_block

LOGIN = "darckware"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_TAG_RE = re.compile(r"^tag:[a-z0-9][a-z0-9-]{0,62}$")
_AUTHKEY_RE = re.compile(r"^tskey-[A-Za-z0-9-]+$")
_PUBKEY_RE = re.compile(r"^ssh-(?:ed25519|rsa) [A-Za-z0-9+/=]+(?: [\w.@:-]+)?$")
# No quotes, backticks, $ or backslash: safe inside '...' in PowerShell and sh.
_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!#%*+-=?@_"


class EnrollmentError(ValueError):
    pass


def generate_password(length: int = 20) -> str:
    """Strong, with at least one of each class (Windows complexity rules)."""
    while True:
        pw = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!#%*+-=?@_" for c in pw)
        ):
            return pw


def validate_station_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not _NAME_RE.match(name):
        raise EnrollmentError(
            "Use a station name with lowercase letters, digits and hyphens (e.g. gat-adm-pc02)"
        )
    return name


def _check(name: str, tag: str, auth_key: str, password: str, public_key: str) -> None:
    if not _NAME_RE.match(name):
        raise EnrollmentError("Invalid station name")
    if not _TAG_RE.match(tag):
        raise EnrollmentError("Invalid tag (expected tag:<name>)")
    if not _AUTHKEY_RE.match(auth_key):
        raise EnrollmentError("Invalid Tailscale auth key")
    if not password or any(c not in _PASSWORD_ALPHABET for c in password):
        raise EnrollmentError("Invalid generated password")
    if not _PUBKEY_RE.match(public_key or ""):
        raise EnrollmentError("Invalid public key")


def windows_script(name: str, tag: str, auth_key: str, password: str, public_key: str) -> str:
    _check(name, tag, auth_key, password, public_key)
    return f"""# ForgeHub - ingresso da estacao '{name}' no suporte remoto
# Rodar UMA vez no PowerShell como administrador. Pode repetir sem problema.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 1) Tailscale instalado e na rede da Darckware ({tag})
$ts = "$env:ProgramFiles\\Tailscale\\tailscale.exe"
if (-not (Test-Path $ts)) {{
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {{ 'arm64' }} else {{ 'amd64' }}
    $msi = "$env:TEMP\\tailscale-setup.msi"
    Invoke-WebRequest -UseBasicParsing "https://pkgs.tailscale.com/stable/tailscale-setup-latest-$arch.msi" -OutFile $msi
    Start-Process msiexec.exe -Wait -ArgumentList "/i `"$msi`" /quiet /norestart TS_UNATTENDEDMODE=always"
    Start-Sleep -Seconds 5
}}
$state = (& $ts status --json 2>$null | ConvertFrom-Json).BackendState
if ($state -ne 'Running') {{
    & $ts up --authkey={auth_key} --hostname={name} --unattended
}} else {{
    & $ts set --hostname={name}
}}

# 2) Servidor OpenSSH ligado, so pela tailnet, PowerShell como shell padrao
# (so instala se o servico sshd ainda nao existir: ha maquinas com o OpenSSH
#  instalado pelo MSI avulso, onde o recurso do Windows nao aparece e a instalacao e negada)
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {{
    if ((Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0).State -ne 'Installed') {{
        Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
    }}
}}
Set-Service sshd -StartupType Automatic
Start-Service sshd
New-Item -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Name DefaultShell `
    -Value "$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -PropertyType String -Force | Out-Null
Disable-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue
if (-not (Get-NetFirewallRule -Name sshd-tailnet -ErrorAction SilentlyContinue)) {{
    New-NetFirewallRule -Name sshd-tailnet -DisplayName 'OpenSSH (somente tailnet)' -Direction Inbound `
        -Protocol TCP -LocalPort 22 -RemoteAddress {TAILNET_CIDR} -Action Allow | Out-Null
}}

# 3) Conta {LOGIN} (administradora) com senha unica desta estacao + chave do ForgeHub
$pw = ConvertTo-SecureString '{password}' -AsPlainText -Force
if (Get-LocalUser -Name {LOGIN} -ErrorAction SilentlyContinue) {{
    Set-LocalUser -Name {LOGIN} -Password $pw -PasswordNeverExpires $true
    Enable-LocalUser -Name {LOGIN}
}} else {{
    New-LocalUser -Name {LOGIN} -Password $pw -PasswordNeverExpires -AccountNeverExpires `
        -Description 'ForgeHub - suporte remoto Darckware' | Out-Null
}}
if (-not (Get-LocalGroupMember -SID S-1-5-32-544 | Where-Object {{ $_.Name -like '*\\{LOGIN}' }})) {{
    Add-LocalGroupMember -SID S-1-5-32-544 -Member {LOGIN}
}}
$key = '{public_key}'
$file = "$env:ProgramData\\ssh\\administrators_authorized_keys"
if (-not (Test-Path $file) -or -not (Select-String -Path $file -SimpleMatch $key -Quiet)) {{
    Add-Content -Path $file -Value $key
}}
icacls $file /inheritance:r /grant "*S-1-5-32-544:F" /grant "SYSTEM:F" | Out-Null

Write-Host ''
Write-Host "Tailscale: $((& $ts ip -4) -join ' ')"
Get-Service sshd | Select-Object Name, Status, StartType | Format-Table -AutoSize
Write-Host 'Pronto: volte ao ForgeHub, a estacao deve aparecer como Pronta em ate 1 minuto.'
"""


def linux_script(name: str, tag: str, auth_key: str, password: str, public_key: str) -> str:
    _check(name, tag, auth_key, password, public_key)
    return f"""#!/bin/sh
# ForgeHub - ingresso da estacao '{name}' no suporte remoto
# Rodar UMA vez como root: sudo sh ingressar.sh  (pode repetir sem problema)
set -e

# 1) Tailscale instalado e na rede da Darckware ({tag})
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | sh
if tailscale status --json 2>/dev/null | grep -q '"BackendState": *"Running"'; then
    tailscale set --hostname={name}
else
    tailscale up --authkey={auth_key} --hostname={name}
fi

# 2) Servidor SSH ligado; com ufw ativo, so pela tailnet
if ! command -v sshd >/dev/null 2>&1 && [ ! -x /usr/sbin/sshd ]; then
    if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && apt-get install -y -qq openssh-server
    elif command -v dnf >/dev/null 2>&1; then dnf install -y -q openssh-server
    elif command -v zypper >/dev/null 2>&1; then zypper -q install -y openssh
    fi
fi
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q active; then
    ufw allow from {TAILNET_CIDR} to any port 22 proto tcp
fi

# 3) Conta {LOGIN} com senha unica desta estacao, sudo sem senha (comandos
#    do ForgeHub rodam sem terminal) e chave do ForgeHub
id {LOGIN} >/dev/null 2>&1 || useradd -m -s /bin/bash {LOGIN}
echo '{LOGIN}:{password}' | chpasswd
echo '{LOGIN} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/{LOGIN}
chmod 440 /etc/sudoers.d/{LOGIN}

{_posix_key_block(LOGIN, public_key)}
echo "Tailscale: $(tailscale ip -4)"
echo 'Pronto: volte ao ForgeHub, a estacao deve aparecer como Pronta em ate 1 minuto.'
"""


def enrollment_script(os_family: str, **kwargs: str) -> tuple[str, str]:
    if os_family == "windows":
        return windows_script(**kwargs), "powershell"
    if os_family == "linux":
        return linux_script(**kwargs), "sh"
    raise EnrollmentError("Enrollment is available for Windows and Linux stations for now")
