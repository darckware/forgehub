"""System scripts shipped by ForgeHub (Remote Access, 2026-10-16, Marcelo:
"preciso de um botão para instalação do tailscale e do rustdesk... passar a
key do tailscale e as configurações de rede e troca de senha do rustdesk").

They live in the script library (`host_scripts.is_system`, keyed by
`system_key`), are run from the single execution screen like any other
script, and can't be edited there. `seed_system_scripts` (startup) creates
them and, when ForgeHub ships a new text, records it as a new version.

Windows reuses Darckware's own installer (`darckware-remote`, pinned to a
commit): it downloads the official Tailscale/RustDesk binaries and checks
hash, signature and publisher before running them. Linux uses the official
Tailscale install script and the RustDesk 1.4.9 .deb.

RustDesk network defaults are Darckware's server (`/root/project/remoto`,
`config/deployment.json` of the installer); every value is a parameter, so a
different server can be typed at run time. A successful RustDesk install or
password change prints `RUSTDESK_ID=<id>`; the runner then stores the ID and
the new password on the machine (see host_execution.py).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.host_scripts import validate_parameters

logger = logging.getLogger(__name__)

INSTALLER_COMMIT = "35a524612ebc65bb6375e6859dfe39f6c0e8ea98"
RUSTDESK_ID_SERVER = "100.105.235.114"
RUSTDESK_RELAY_SERVER = "100.105.235.114:21117"
RUSTDESK_KEY = "30OQH25Eg+VmQH06Y6h7GXiuHML4V8Km4MltPVfP4ys="
RUSTDESK_LINUX_DEB = "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.deb"

RUSTDESK_ID_MARKER = "RUSTDESK_ID="

_WIN_FETCH_INSTALLER = f"""$ErrorActionPreference = 'Stop'
$commit = '{INSTALLER_COMMIT}'
$base = Join-Path $env:ProgramData 'Darckware'
$dir = Join-Path $base "darckware-remote-$commit"
if (-not (Test-Path (Join-Path $dir 'install.ps1'))) {{
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $zip = Join-Path $env:TEMP "darckware-remote-$commit.zip"
    Invoke-WebRequest -UseBasicParsing "https://github.com/darckware/darckware-remote/archive/$commit.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $base -Force
    Remove-Item -Force $zip
}}
function New-SecretDir {{
    $path = Join-Path $base ('s-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $path | Out-Null
    icacls $path /inheritance:r /grant '*S-1-5-32-544:(OI)(CI)F' /grant 'SYSTEM:(OI)(CI)F' | Out-Null
    return $path
}}
function Invoke-Installer([string[]]$InstallerArgs) {{
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dir 'install.ps1') @InstallerArgs
    if ($LASTEXITCODE -ne 0) {{ throw "O instalador da Darckware terminou com codigo $LASTEXITCODE" }}
}}
"""

_WIN_RUSTDESK_CLI = """function Invoke-RustDesk([string[]]$RdArgs) {
    $exe = Join-Path $env:ProgramFiles 'RustDesk\\rustdesk.exe'
    if (-not (Test-Path $exe)) { throw 'O RustDesk nao esta instalado nesta maquina' }
    $quoted = foreach ($a in $RdArgs) {
        $e = [regex]::Replace($a, '(\\\\*)"', '$1$1\\"'); $e = [regex]::Replace($e, '(\\\\+)$', '$1$1'); '"' + $e + '"'
    }
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $exe; $psi.Arguments = $quoted -join ' '
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $p = [Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd(); $null = $p.StandardError.ReadToEnd()
    if (-not $p.WaitForExit(60000)) { $p.Kill(); throw 'O RustDesk nao respondeu' }
    return [pscustomobject]@{ Code = $p.ExitCode; Out = $out.Trim() }
}
"""

_SH_PRELUDE = """set -e
SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo -n"
"""

_RUSTDESK_NETWORK_PARAMS = [
    {"name": "RUSTDESK_ID_SERVER", "label": "Servidor de ID", "required": True, "default": RUSTDESK_ID_SERVER},
    {"name": "RUSTDESK_RELAY_SERVER", "label": "Servidor de Relay", "required": True, "default": RUSTDESK_RELAY_SERVER},
    {"name": "RUSTDESK_KEY", "label": "Key", "required": True, "default": RUSTDESK_KEY},
]
_RUSTDESK_PASSWORD_PARAM = {"name": "RUSTDESK_PASSWORD", "label": "Senha permanente do RustDesk", "required": True, "secret": True}

SYSTEM_SCRIPTS: list[dict] = [
    {
        "system_key": "tailscale_install:windows",
        "name": "Instalar Tailscale",
        "platform": "windows",
        "category": "instalacao",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o Tailscale (instalador oficial validado pelo darckware-remote) e conecta a máquina à "
            "tailnet com a chave informada. Se já estiver conectada, não mexe na conexão."
        ),
        "parameters": [
            {"name": "TAILSCALE_AUTHKEY", "label": "Chave de autenticação da Tailscale (tskey-auth-...)", "required": True, "secret": True},
            {"name": "TAILSCALE_HOSTNAME", "label": "Nome na tailnet (vazio = nome do computador)"},
        ],
        "content": _WIN_FETCH_INSTALLER + """
$ts = Join-Path $env:ProgramFiles 'Tailscale\\tailscale.exe'
if (Test-Path $ts) {
    $state = (& $ts status --json 2>$null | ConvertFrom-Json).BackendState
    if ($state -eq 'Running') { "Tailscale ja conectado: $((& $ts ip -4) -join ' ')"; exit 0 }
}
$hn = if ($TAILSCALE_HOSTNAME) { $TAILSCALE_HOSTNAME } else { $env:COMPUTERNAME.ToLower() }
$sec = New-SecretDir
try {
    [IO.File]::WriteAllText((Join-Path $sec 'ts.txt'), $TAILSCALE_AUTHKEY)
    Invoke-Installer @('-NonInteractive', '-InstallTailscale', '-TailscaleHostname', $hn, '-TailscaleAuthKeyFile', (Join-Path $sec 'ts.txt'))
} finally { Remove-Item -Recurse -Force $sec -ErrorAction SilentlyContinue }
"Tailscale conectado: $((& $ts ip -4) -join ' ')"
""",
    },
    {
        "system_key": "tailscale_unattended:windows",
        "name": "Tailscale em modo autônomo",
        "platform": "windows",
        "category": "manutencao",
        "risk": "change",
        "timeout_seconds": 120,
        "description": (
            "Liga o modo autônomo (unattended) da Tailscale pela política de sistema UnattendedMode=always: a "
            "máquina continua na tailnet sem ninguém logado e depois de reiniciar. Necessário quando a Tailscale "
            "foi conectada pelo ícone da bandeja, o que a prende ao usuário daquela sessão. O serviço é reiniciado "
            "segundos depois do fim da execução, então a conexão cai por um instante."
        ),
        "parameters": [],
        # The restart runs as a CIM-created process: a child of this SSH session
        # would be killed with it, and the session itself rides on the tailnet.
        "content": """$ErrorActionPreference = 'Stop'
if (-not (Get-Service Tailscale -ErrorAction SilentlyContinue)) { throw 'A Tailscale nao esta instalada nesta maquina' }
$key = 'HKLM:\\SOFTWARE\\Policies\\Tailscale'
$current = (Get-ItemProperty $key -ErrorAction SilentlyContinue).UnattendedMode
if ($current -eq 'always') { 'Modo autonomo ja ativo (UnattendedMode=always)'; exit 0 }
New-Item -Path $key -Force | Out-Null
New-ItemProperty -Path $key -Name 'UnattendedMode' -Value 'always' -PropertyType String -Force | Out-Null
$cmd = 'powershell.exe -NoProfile -Command "Start-Sleep 5; Restart-Service Tailscale -Force"'
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd }
if ($r.ReturnValue -ne 0) { throw "Politica gravada, mas o reinicio do servico falhou (codigo $($r.ReturnValue))" }
'Modo autonomo ativado (UnattendedMode=always); a Tailscale reinicia em 5 segundos'
""",
    },
    {
        "system_key": "tailscale_install:linux",
        "name": "Instalar Tailscale",
        "platform": "linux",
        "category": "instalacao",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o Tailscale (script oficial) e conecta a máquina à tailnet com a chave informada. "
            "Se já estiver conectada, não mexe na conexão."
        ),
        "parameters": [
            {"name": "TAILSCALE_AUTHKEY", "label": "Chave de autenticação da Tailscale (tskey-auth-...)", "required": True, "secret": True},
            {"name": "TAILSCALE_HOSTNAME", "label": "Nome na tailnet (vazio = nome da máquina)"},
        ],
        "content": _SH_PRELUDE + """if command -v tailscale >/dev/null 2>&1 && tailscale status --json 2>/dev/null | grep -q '"BackendState": *"Running"'; then
    echo "Tailscale ja conectado: $(tailscale ip -4)"; exit 0
fi
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | $SUDO sh
HN="${TAILSCALE_HOSTNAME:-$(hostname | tr 'A-Z' 'a-z')}"
$SUDO tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="$HN"
echo "Tailscale conectado: $(tailscale ip -4)"
""",
    },
    {
        "system_key": "rustdesk_install:windows",
        "name": "Instalar RustDesk",
        "platform": "windows",
        "category": "instalacao",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o RustDesk (instalador oficial validado pelo darckware-remote), configura o servidor de "
            "ID/Relay e a Key da Darckware e define a senha permanente. A senha e o ID ficam guardados no "
            "cadastro da máquina. Requer a máquina conectada à tailnet."
        ),
        "parameters": [*_RUSTDESK_NETWORK_PARAMS, _RUSTDESK_PASSWORD_PARAM],
        "content": _WIN_FETCH_INSTALLER + _WIN_RUSTDESK_CLI + """
$cfgPath = Join-Path $dir 'config\\deployment.json'
$cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json
$cfg.rustdesk.idServer = $RUSTDESK_ID_SERVER
$cfg.rustdesk.relayServer = $RUSTDESK_RELAY_SERVER
$cfg.rustdesk.publicKey = $RUSTDESK_KEY
$cfg | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $cfgPath
$sec = New-SecretDir
try {
    [IO.File]::WriteAllText((Join-Path $sec 'rd.txt'), $RUSTDESK_PASSWORD)
    Invoke-Installer @('-NonInteractive', '-InstallRustDesk', '-ConnectivityMode', 'LocalTailscale', '-RustDeskPasswordFile', (Join-Path $sec 'rd.txt'))
} finally { Remove-Item -Recurse -Force $sec -ErrorAction SilentlyContinue }
$id = (Invoke-RustDesk @('--get-id')).Out
"RUSTDESK_ID=$id"
""",
    },
    {
        "system_key": "rustdesk_install:linux",
        "name": "Instalar RustDesk",
        "platform": "linux",
        "category": "instalacao",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o RustDesk 1.4.9 (Debian/Ubuntu, x86_64), configura o servidor de ID/Relay e a Key e define "
            "a senha permanente. Só para máquinas com interface gráfica — não instalar em servidor sem tela."
        ),
        "parameters": [*_RUSTDESK_NETWORK_PARAMS, _RUSTDESK_PASSWORD_PARAM],
        "content": _SH_PRELUDE + f"""if ! command -v rustdesk >/dev/null 2>&1; then
    command -v apt-get >/dev/null 2>&1 || {{ echo "Instalacao automatica so em Debian/Ubuntu" >&2; exit 2; }}
    [ "$(uname -m)" = "x86_64" ] || {{ echo "Arquitetura $(uname -m) nao suportada" >&2; exit 2; }}
    TMP=$(mktemp -d)
    curl -fsSL -o "$TMP/rustdesk.deb" {RUSTDESK_LINUX_DEB}
    $SUDO apt-get install -y -qq "$TMP/rustdesk.deb"
    rm -rf "$TMP"
fi
$SUDO rustdesk --option custom-rendezvous-server "$RUSTDESK_ID_SERVER"
$SUDO rustdesk --option relay-server "$RUSTDESK_RELAY_SERVER"
$SUDO rustdesk --option key "$RUSTDESK_KEY"
$SUDO rustdesk --password "$RUSTDESK_PASSWORD" >/dev/null
echo "RUSTDESK_ID=$($SUDO rustdesk --get-id)"
""",
    },
    {
        "system_key": "rustdesk_password:windows",
        "name": "Trocar senha do RustDesk",
        "platform": "windows",
        "category": "seguranca",
        "risk": "change",
        "timeout_seconds": 120,
        "description": "Define uma nova senha permanente do RustDesk. A nova senha só é guardada no cadastro se a troca der certo.",
        "parameters": [_RUSTDESK_PASSWORD_PARAM],
        "content": "$ErrorActionPreference = 'Stop'\n" + _WIN_RUSTDESK_CLI + """
$r = Invoke-RustDesk @('--password', $RUSTDESK_PASSWORD)
if ($r.Code -ne 0) { throw "O RustDesk recusou a troca de senha (codigo $($r.Code))" }
$id = (Invoke-RustDesk @('--get-id')).Out
"RUSTDESK_ID=$id"
""",
    },
    {
        "system_key": "rustdesk_password:linux",
        "name": "Trocar senha do RustDesk",
        "platform": "linux",
        "category": "seguranca",
        "risk": "change",
        "timeout_seconds": 120,
        "description": "Define uma nova senha permanente do RustDesk. A nova senha só é guardada no cadastro se a troca der certo.",
        "parameters": [_RUSTDESK_PASSWORD_PARAM],
        "content": _SH_PRELUDE + """command -v rustdesk >/dev/null 2>&1 || { echo "O RustDesk nao esta instalado nesta maquina" >&2; exit 2; }
$SUDO rustdesk --password "$RUSTDESK_PASSWORD" >/dev/null
echo "RUSTDESK_ID=$($SUDO rustdesk --get-id)"
""",
    },
]


async def seed_system_scripts() -> int:
    """Creates missing system scripts and versions changed ones. Idempotent;
    safe when two processes (dev + production) start together."""
    from app.db.base import AsyncSessionLocal
    from app.db.models.host_script import HostScript, HostScriptCategory, HostScriptVersion

    changed = 0
    async with AsyncSessionLocal() as db:
        categories = {c.slug: c.id for c in (await db.execute(select(HostScriptCategory))).scalars()}
        for spec in SYSTEM_SCRIPTS:
            params = validate_parameters(spec["parameters"])
            row = (await db.execute(select(HostScript).where(HostScript.system_key == spec["system_key"]))).scalar_one_or_none()
            category_id = categories.get(spec["category"])
            if category_id is None:
                continue
            if row is None:
                row = HostScript(
                    name=spec["name"], category_id=category_id, description=spec["description"],
                    platform=spec["platform"], risk=spec["risk"], timeout_seconds=spec["timeout_seconds"],
                    parameters=params, content=spec["content"], current_version=1, is_system=True,
                    system_key=spec["system_key"], created_by="forgehub", updated_by="forgehub",
                )
                db.add(row)
                await db.flush()
                db.add(HostScriptVersion(script_id=row.id, version=1, content=spec["content"], parameters=params,
                                         changed_by="forgehub", note="Script de sistema"))
                changed += 1
                continue
            row.name, row.description, row.risk = spec["name"], spec["description"], spec["risk"]
            row.timeout_seconds, row.category_id = spec["timeout_seconds"], category_id
            if row.content != spec["content"] or row.parameters != params:
                row.current_version += 1
                row.content, row.parameters = spec["content"], params
                db.add(HostScriptVersion(script_id=row.id, version=row.current_version, content=spec["content"],
                                         parameters=params, changed_by="forgehub", note="Atualizado pelo ForgeHub"))
                changed += 1
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()  # the other process seeded first
            return 0
    return changed
