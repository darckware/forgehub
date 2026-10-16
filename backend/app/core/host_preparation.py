"""Preparation scripts per OS (Remote Access, docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

A station can't be reached over SSH until someone enables it there once --
typically through RustDesk. "Prepare" hands that person a script to paste,
already carrying the station's public key, so a single run leaves the station
"Ready": SSH server on and starting with the machine, the port open to the
tailnet only (100.64.0.0/10), and ForgeHub's key authorized for the login.

Every script is idempotent (safe to run twice) and only ever *adds* the key;
it never removes another key or account. The login and key are validated
before being embedded, so nothing a user typed in the form becomes script
syntax.
"""
import re

TAILNET_CIDR = "100.64.0.0/10"
_LOGIN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
_PUBKEY_RE = re.compile(r"^ssh-(?:ed25519|rsa) [A-Za-z0-9+/=]+(?: [\w.@:-]+)?$")


class PreparationError(ValueError):
    pass


def _check(login: str, public_key: str) -> None:
    if not _LOGIN_RE.match(login or ""):
        raise PreparationError("The machine's login is missing or has characters a script can't carry safely")
    if not _PUBKEY_RE.match(public_key or ""):
        raise PreparationError("The machine's public key is not a valid ssh-ed25519/ssh-rsa line")


def windows_script(login: str, public_key: str) -> str:
    _check(login, public_key)
    return f"""# ForgeHub - preparacao da estacao (rodar UMA vez, PowerShell como administrador)
$ErrorActionPreference = 'Stop'

# 1) Servidor OpenSSH instalado, ligado e iniciando com a maquina
if ((Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0).State -ne 'Installed') {{
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}}
Set-Service sshd -StartupType Automatic
Start-Service sshd

# 1b) Shell padrao do SSH = PowerShell (padrao das estacoes Windows)
New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell `
    -Value "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null

# 2) Firewall: SSH somente pela tailnet ({TAILNET_CIDR})
Disable-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue
if (-not (Get-NetFirewallRule -Name sshd-tailnet -ErrorAction SilentlyContinue)) {{
    New-NetFirewallRule -Name sshd-tailnet -DisplayName 'OpenSSH (somente tailnet)' -Direction Inbound `
        -Protocol TCP -LocalPort 22 -RemoteAddress {TAILNET_CIDR} -Action Allow | Out-Null
}}

# 3) Chave do ForgeHub autorizada para '{login}'
$key = '{public_key}'
$isAdmin = (Get-LocalGroupMember -SID S-1-5-32-544 -ErrorAction SilentlyContinue |
    Where-Object {{ $_.Name -like "*\\{login}" }}) -ne $null
if ($isAdmin) {{
    $file = "$env:ProgramData\\ssh\\administrators_authorized_keys"
}} else {{
    $dir = "C:\\Users\\{login}\\.ssh"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $file = "$dir\\authorized_keys"
}}
if (-not (Test-Path $file) -or -not (Select-String -Path $file -SimpleMatch $key -Quiet)) {{
    Add-Content -Path $file -Value $key
}}
if ($isAdmin) {{ icacls $file /inheritance:r /grant "*S-1-5-32-544:F" /grant "SYSTEM:F" | Out-Null }}

Get-Service sshd | Select-Object Name, Status, StartType
Get-NetTCPConnection -LocalPort 22 -State Listen | Select-Object -First 1 LocalAddress, LocalPort
Write-Host 'Pronto: volte ao ForgeHub e clique em "Verificar agora".'
"""


def _posix_key_block(login: str, public_key: str) -> str:
    return f"""# Chave do ForgeHub autorizada para '{login}'
U='{login}'
KEY='{public_key}'
H=$(getent passwd "$U" 2>/dev/null | cut -d: -f6)
[ -n "$H" ] || H=$(dscl . -read "/Users/$U" NFSHomeDirectory 2>/dev/null | awk '{{print $2}}')
[ -n "$H" ] || {{ echo "Usuario $U nao existe nesta maquina" >&2; exit 1; }}
mkdir -p "$H/.ssh" && chmod 700 "$H/.ssh"
touch "$H/.ssh/authorized_keys" && chmod 600 "$H/.ssh/authorized_keys"
grep -qxF "$KEY" "$H/.ssh/authorized_keys" || echo "$KEY" >> "$H/.ssh/authorized_keys"
chown -R "$U" "$H/.ssh"
"""


def linux_script(login: str, public_key: str) -> str:
    _check(login, public_key)
    return f"""#!/bin/sh
# ForgeHub - preparacao da estacao (rodar UMA vez como root: sudo sh preparar.sh)
set -e

# 1) Servidor SSH instalado, ligado e iniciando com a maquina
if ! command -v sshd >/dev/null 2>&1 && [ ! -x /usr/sbin/sshd ]; then
    if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && apt-get install -y -qq openssh-server
    elif command -v dnf >/dev/null 2>&1; then dnf install -y -q openssh-server
    elif command -v zypper >/dev/null 2>&1; then zypper -q install -y openssh
    fi
fi
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd

# 2) Firewall: se o ufw estiver ativo, libera o SSH somente pela tailnet
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q active; then
    ufw allow from {TAILNET_CIDR} to any port 22 proto tcp
fi

{_posix_key_block(login, public_key)}
echo 'Pronto: volte ao ForgeHub e clique em "Verificar agora".'
"""


def macos_script(login: str, public_key: str) -> str:
    _check(login, public_key)
    return f"""#!/bin/sh
# ForgeHub - preparacao da estacao (rodar UMA vez no Terminal: sudo sh preparar.sh)
set -e

# 1) Login Remoto (SSH) ligado
systemsetup -setremotelogin on

{_posix_key_block(login, public_key)}
echo 'Pronto: volte ao ForgeHub e clique em "Verificar agora".'
"""


def preparation_script(os_family: str | None, login: str, public_key: str) -> tuple[str, str]:
    """(script, language) for the machine's OS."""
    if os_family == "windows":
        return windows_script(login, public_key), "powershell"
    if os_family == "linux":
        return linux_script(login, public_key), "sh"
    if os_family == "macos":
        return macos_script(login, public_key), "sh"
    raise PreparationError("Set the machine's operating system first")
