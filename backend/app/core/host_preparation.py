"""Preparation scripts per OS (Remote Access, docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

A station can't be reached over SSH until someone enables it there once --
typically through RustDesk. "Prepare" hands that person a script to paste,
already carrying the station's public key, so a single run leaves the station
"Ready": SSH server on and starting with the machine, the port open to the
tailnet only (100.64.0.0/10), and ForgeHub's key authorized for the login.

With a `password`, the script also creates (or resets) the login as a local
administrator with that password -- the station's own `darckware` account,
whose password ForgeHub generated and stored in ForgeVault (2026-10-16). The
client's administrator account is never touched by the script: disabling it
is a separate step ForgeHub only takes after logging in as `darckware` with
the key worked (api/routes/server.py, prepare_host).

Every script is idempotent (safe to run twice) and only ever *adds*; it never
removes another key or account. The login and key are validated
before being embedded, so nothing a user typed in the form becomes script
syntax.
"""
import base64
import re

TAILNET_CIDR = "100.64.0.0/10"
_LOGIN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$")
_PUBKEY_RE = re.compile(r"^ssh-(?:ed25519|rsa) [A-Za-z0-9+/=]+(?: [\w.@:-]+)?$")
# Generated passwords only (no quotes, $, backtick or backslash), so they are
# safe inside single quotes in PowerShell and sh.
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9!#%*+=?@_-]{12,64}$")


class PreparationError(ValueError):
    pass


def _check(login: str, public_key: str, password: str | None = None, ssh_port: int = 22) -> None:
    if not isinstance(ssh_port, int) or not (1 <= ssh_port <= 65535):
        raise PreparationError("SSH port must be between 1 and 65535")
    if password is not None and not _PASSWORD_RE.match(password):
        raise PreparationError("Invalid generated password")
    if not _LOGIN_RE.match(login or ""):
        raise PreparationError("The machine's login is missing or has characters a script can't carry safely")
    if not _PUBKEY_RE.match(public_key or ""):
        raise PreparationError("The machine's public key is not a valid ssh-ed25519/ssh-rsa line")


_WINDOWS_ADMIN_HELPERS = """function Get-LocalAdministratorsGroupName {
    $sid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
    return ($sid.Translate([System.Security.Principal.NTAccount]).Value -split '\\\\')[-1]
}
function Test-IsLocalAdmin([string]$UserName) {
    $groupName = Get-LocalAdministratorsGroupName
    try {
        $group = [ADSI]"WinNT://./$groupName,group"
        foreach ($m in @($group.Invoke('Members'))) {
            $name = $m.GetType().InvokeMember('Name', 'GetProperty', $null, $m, $null)
            if ($name -ieq $UserName) { return $true }
        }
        return $false
    } catch {
        return ((Get-LocalGroupMember -SID S-1-5-32-544 -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*\\$UserName" }) -ne $null)
    }
}"""


def _windows_account_block(login: str, password: str) -> str:
    return f"""
# 2b) Conta '{login}' (administradora local) com a senha gerada pelo ForgeHub
$pw = ConvertTo-SecureString '{password}' -AsPlainText -Force
if (Get-LocalUser -Name '{login}' -ErrorAction SilentlyContinue) {{
    Set-LocalUser -Name '{login}' -Password $pw -PasswordNeverExpires $true -AccountNeverExpires
    Enable-LocalUser -Name '{login}'
}} else {{
    New-LocalUser -Name '{login}' -Password $pw -PasswordNeverExpires -AccountNeverExpires `
        -Description 'ForgeHub - suporte remoto Darckware' | Out-Null
}}
if (-not (Test-IsLocalAdmin '{login}')) {{
    $adminGroup = Get-LocalAdministratorsGroupName
    try {{
        Add-LocalGroupMember -SID S-1-5-32-544 -Member '{login}' -ErrorAction Stop
    }} catch {{
        net localgroup "$adminGroup" '{login}' /add | Out-Null
        if ($LASTEXITCODE -ne 0) {{ throw "Falha ao adicionar '{login}' ao grupo $adminGroup ($LASTEXITCODE)" }}
    }}
}}
"""


def windows_script(
    login: str, public_key: str, password: str | None = None, *, ssh_port: int = 22, tailnet_only: bool = True
) -> str:
    _check(login, public_key, password, ssh_port=ssh_port)
    if tailnet_only:
        fw_block = f"""# 2) Firewall: SSH somente pela tailnet ({TAILNET_CIDR}) na porta {ssh_port}
Disable-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue
if (-not (Get-NetFirewallRule -Name sshd-tailnet -ErrorAction SilentlyContinue)) {{
    New-NetFirewallRule -Name sshd-tailnet -DisplayName 'OpenSSH (somente tailnet)' -Direction Inbound `
        -Protocol TCP -LocalPort {ssh_port} -RemoteAddress {TAILNET_CIDR} -Action Allow | Out-Null
}}"""
    else:
        fw_block = f"""# 2) Firewall: libera SSH na porta {ssh_port} (host alcancado via LAN/subnet router)
if (-not (Get-NetFirewallRule -Name sshd-forgehub -ErrorAction SilentlyContinue)) {{
    New-NetFirewallRule -Name sshd-forgehub -DisplayName 'OpenSSH (ForgeHub)' -Direction Inbound `
        -Protocol TCP -LocalPort {ssh_port} -Action Allow | Out-Null
}}"""
    return f"""# ForgeHub - preparacao da estacao (rodar UMA vez, PowerShell como administrador)
$ErrorActionPreference = 'Stop'

{_WINDOWS_ADMIN_HELPERS}

# 1) Servidor OpenSSH instalado, ligado e iniciando com a maquina
# (so instala se o servico sshd ainda nao existir: ha maquinas com o OpenSSH
#  instalado pelo MSI avulso, onde o recurso do Windows nao aparece e a instalacao e negada)
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {{
    if ((Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0).State -ne 'Installed') {{
        Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
    }}
}}
Set-Service sshd -StartupType Automatic
Start-Service sshd

# 1b) Shell padrao do SSH = PowerShell (padrao das estacoes Windows)
New-Item -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Name DefaultShell `
    -Value "$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -PropertyType String -Force | Out-Null

{fw_block}

{_windows_account_block(login, password) if password else ""}
# 3) Chave do ForgeHub autorizada para '{login}'
$key = '{public_key}'
$isAdmin = Test-IsLocalAdmin '{login}'
if ($isAdmin) {{
    $dir = "$env:ProgramData\\ssh"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $file = "$dir\\administrators_authorized_keys"
}} else {{
    $profileDir = (Get-CimInstance Win32_UserProfile -ErrorAction SilentlyContinue |
        Where-Object {{ $_.LocalPath -like "*\\{login}" }} | Select-Object -First 1 -ExpandProperty LocalPath)
    if (-not $profileDir) {{ $profileDir = "$env:SystemDrive\\Users\\{login}" }}
    $dir = "$profileDir\\.ssh"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $file = "$dir\\authorized_keys"
}}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$existing = if (Test-Path $file) {{ [IO.File]::ReadAllLines($file) }} else {{ @() }}
if ($existing -notcontains $key) {{
    $lines = @($existing | Where-Object {{ $_ -ne '' }}) + @($key)
    [IO.File]::WriteAllLines($file, $lines, $utf8NoBom)
}}
if ($isAdmin) {{
    icacls $file /inheritance:r /grant "*S-1-5-32-544:F" /grant "*S-1-5-18:F" | Out-Null
    if ($LASTEXITCODE -ne 0) {{ throw "Falha ao ajustar permissoes em $file (icacls=$LASTEXITCODE)" }}
}}

Get-Service sshd | Select-Object Name, Status, StartType
Get-NetTCPConnection -LocalPort {ssh_port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 LocalAddress, LocalPort
Write-Host 'Pronto: volte ao ForgeHub e clique em "Verificar agora".'
"""


def _posix_key_block(login: str, public_key: str) -> str:
    return f"""# Chave do ForgeHub autorizada para '{login}'
U='{login}'
KEY='{public_key}'
H=$(getent passwd "$U" 2>/dev/null | cut -d: -f6)
[ -n "$H" ] || H=$(dscl . -read "/Users/$U" NFSHomeDirectory 2>/dev/null | awk '{{print $2}}')
[ -n "$H" ] || {{ echo "Usuario $U nao existe nesta maquina" >&2; exit 1; }}
G=$(id -gn "$U" 2>/dev/null || echo "$U")
chmod go-w "$H" 2>/dev/null || true
mkdir -p "$H/.ssh" && chmod 700 "$H/.ssh"
touch "$H/.ssh/authorized_keys" && chmod 600 "$H/.ssh/authorized_keys"
grep -qxF "$KEY" "$H/.ssh/authorized_keys" || echo "$KEY" >> "$H/.ssh/authorized_keys"
chown -R "$U:$G" "$H/.ssh" 2>/dev/null || chown -R "$U" "$H/.ssh"
"""


def _linux_account_block(login: str, password: str) -> str:
    return f"""# 2b) Conta '{login}' com a senha gerada pelo ForgeHub e sudo sem senha
#     (os comandos do ForgeHub rodam sem terminal)
id '{login}' >/dev/null 2>&1 || useradd -m -s /bin/bash '{login}'
usermod -U -s /bin/bash '{login}' 2>/dev/null || true
command -v chage >/dev/null 2>&1 && chage -E -1 -M -1 '{login}' 2>/dev/null || true
echo '{login}:{password}' | chpasswd
mkdir -p /etc/sudoers.d
sudo_tmp=$(mktemp /tmp/fh-sudoers.XXXXXX)
printf '%s ALL=(ALL) NOPASSWD:ALL\\n' '{login}' > "$sudo_tmp"
chmod 440 "$sudo_tmp"
if command -v visudo >/dev/null 2>&1; then
    visudo -cf "$sudo_tmp" >/dev/null
fi
mv -f "$sudo_tmp" '/etc/sudoers.d/{login}'
chmod 440 '/etc/sudoers.d/{login}'
if command -v ucr >/dev/null 2>&1 && [ "$(ucr get auth/sshd/restrict 2>/dev/null)" = "yes" ]; then
    ucr set 'auth/sshd/user/{login}=yes'
fi
"""


def linux_ssh_bootstrap_script(script: str, admin_password: str | None) -> str:
    """Wrap `linux_script` so SSH logins as a non-root admin elevate via sudo or su."""
    script_b64 = base64.b64encode(script.encode()).decode("ascii")
    pw_b64 = base64.b64encode((admin_password or "").encode()).decode("ascii")
    return f"""#!/bin/sh
# ForgeHub - preparacao da estacao (elevacao via sudo/su)
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
if [ "$(id -u)" -eq 0 ]; then
    echo '{script_b64}' | base64 -d | sh
    exit $?
fi
tmp=$(mktemp /tmp/fh-prep.XXXXXX) || exit 1
chmod 600 "$tmp"
trap 'rm -f "$tmp"' EXIT INT TERM
echo '{script_b64}' | base64 -d > "$tmp" || exit 1
ADMIN_PW=$(printf '%s' '{pw_b64}' | base64 -d)
if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo -n sh "$tmp"
elif command -v sudo >/dev/null 2>&1 && printf '%s\\n' "$ADMIN_PW" | sudo -S -p '' true >/dev/null 2>&1; then
    printf '%s\\n' "$ADMIN_PW" | sudo -S -p '' sh "$tmp"
elif command -v python3 >/dev/null 2>&1 && command -v su >/dev/null 2>&1; then
    ADMIN_PW="$ADMIN_PW" TMP_SCRIPT="$tmp" python3 -c '
import os, pty, select, signal, sys, time
pw = os.environ.pop("ADMIN_PW", "")
tmp_script = os.environ["TMP_SCRIPT"]
pid, fd = pty.fork()
if pid == 0:
    os.execvp("su", ["su", "-", "root", "-c", "sh " + tmp_script])
sent = False
buf = b""
prompt_deadline = time.monotonic() + 30.0
while True:
    wait = max(0.5, prompt_deadline - time.monotonic()) if not sent else 10.0
    r, _, _ = select.select([fd], [], [], wait)
    if not r:
        if not sent:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            sys.stderr.write("Timeout aguardando prompt de senha do su.\\n")
            break
        done_pid, done_status = os.waitpid(pid, os.WNOHANG)
        if done_pid == pid:
            os.close(fd)
            code = os.WEXITSTATUS(done_status) if os.WIFEXITED(done_status) else (128 + os.WTERMSIG(done_status) if os.WIFSIGNALED(done_status) else 1)
            sys.exit(code)
        continue
    try:
        chunk = os.read(fd, 4096)
    except OSError:
        break
    if not chunk:
        break
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    if not sent:
        buf += chunk
        low = buf.lower()
        if b"assword" in low or b"senha" in low or low.rstrip().endswith(b":"):
            os.write(fd, (pw + "\\n").encode())
            sent = True
_, status = os.waitpid(pid, 0)
os.close(fd)
code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else (128 + os.WTERMSIG(status) if os.WIFSIGNALED(status) else 1)
sys.exit(code)
'
elif command -v su >/dev/null 2>&1; then
    printf '%s\\n' "$ADMIN_PW" | su - root -c "sh '$tmp'"
else
    echo "Nao foi possivel elevar privilegios para root via sudo ou su." >&2
    exit 1
fi
"""


def linux_script(
    login: str, public_key: str, password: str | None = None, *, ssh_port: int = 22, tailnet_only: bool = True
) -> str:
    _check(login, public_key, password, ssh_port=ssh_port)
    ufw_rule = (
        f"ufw allow from {TAILNET_CIDR} to any port {ssh_port} proto tcp"
        if tailnet_only
        else f"ufw allow {ssh_port}/tcp"
    )
    return f"""#!/bin/sh
# ForgeHub - preparacao da estacao (rodar UMA vez como root: sudo sh preparar.sh)
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
if [ "$(id -u)" -ne 0 ]; then echo "Rode como root (ou com sudo)." >&2; exit 1; fi

# 1) Servidor SSH instalado, ligado e iniciando com a maquina
if ! command -v sshd >/dev/null 2>&1 && [ ! -x /usr/sbin/sshd ]; then
    if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && apt-get install -y -qq openssh-server
    elif command -v dnf >/dev/null 2>&1; then dnf install -y -q openssh-server
    elif command -v zypper >/dev/null 2>&1; then zypper -q install -y openssh
    fi
fi
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd

# 2) Firewall: se o ufw estiver ativo, libera o SSH na porta configurada
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q active; then
    {ufw_rule}
fi

{_linux_account_block(login, password) if password else ""}
{_posix_key_block(login, public_key)}
if command -v ucr >/dev/null 2>&1 && [ "$(ucr get auth/sshd/restrict 2>/dev/null)" = "yes" ]; then
    ucr set 'auth/sshd/user/{login}=yes'
fi
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


def preparation_script(
    os_family: str | None,
    login: str,
    public_key: str,
    password: str | None = None,
    *,
    ssh_port: int = 22,
    tailnet_only: bool = True,
) -> tuple[str, str]:
    """(script, language) for the machine's OS. With `password`, the login is
    created/reset as an administrator with it (Windows, Linux)."""
    if os_family == "windows":
        return windows_script(login, public_key, password, ssh_port=ssh_port, tailnet_only=tailnet_only), "powershell"
    if os_family == "linux":
        return linux_script(login, public_key, password, ssh_port=ssh_port, tailnet_only=tailnet_only), "sh"
    if password is not None:
        raise PreparationError("Creating the account is supported on Windows and Linux for now")
    if os_family == "macos":
        return macos_script(login, public_key), "sh"
    raise PreparationError("Set the machine's operating system first")
