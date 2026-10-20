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

INSTALLER_COMMIT = "6df30b11023eaefe6a36d13bc87f2cfa106e0f20"
# The RustDesk server (ID server, relay, public key) lives only in ForgeVault
# (infra/Production), as one JSON secret; a script reads it at run time when
# those fields are left blank.
RUSTDESK_SERVER_SECRET = "RUSTDESK_SERVER"
RUSTDESK_LINUX_DEB = "https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.deb"

RUSTDESK_ID_MARKER = "RUSTDESK_ID="

_WIN_FETCH_INSTALLER = f"""$ErrorActionPreference = 'Stop'
$commit = '{INSTALLER_COMMIT}'
$base = Join-Path $env:ProgramData 'Darckware'
$dir = Join-Path $base 'remoto'
$marker = Join-Path $dir '.commit'
$installed = if (Test-Path $marker) {{ (Get-Content -Raw $marker).Trim() }} else {{ '' }}
if ($installed -ne $commit -or -not (Test-Path (Join-Path $dir 'install.ps1'))) {{
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $zip = Join-Path $env:TEMP "darckware-remote-$commit.zip"
    $tmp = Join-Path $base ('x-' + [guid]::NewGuid().ToString('N'))
    try {{
        Invoke-WebRequest -UseBasicParsing "https://github.com/darckware/darckware-remote/archive/$commit.zip" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        if (Test-Path $dir) {{ Remove-Item -Recurse -Force $dir }}
        Move-Item (Join-Path $tmp "darckware-remote-$commit") $dir
        Set-Content -Path $marker -Value $commit -Encoding ASCII
    }} finally {{
        Remove-Item -Recurse -Force $tmp, $zip -ErrorAction SilentlyContinue
    }}
    # Older layout: one folder per installer commit.
    Get-ChildItem $base -Directory -Filter 'darckware-remote-*' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}}
Set-Location $dir
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

_SH_TAILSCALE_UP = """if command -v tailscale >/dev/null 2>&1 && tailscale status --json 2>/dev/null | grep -q '"BackendState": *"Running"'; then
    echo "Tailscale ja conectado: $(tailscale ip -4)"
else
    command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | $SUDO sh
    HN="${TAILSCALE_HOSTNAME:-$(hostname | tr 'A-Z' 'a-z')}"
    $SUDO tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="$HN"
    echo "Tailscale conectado: $(tailscale ip -4)"
fi
"""

_SH_RUSTDESK_SETUP = f"""if ! command -v rustdesk >/dev/null 2>&1; then
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
"""
_SH_RUSTDESK_INSTALL = _SH_RUSTDESK_SETUP + 'echo "RUSTDESK_ID=$($SUDO rustdesk --get-id)"\n'

_TAILSCALE_PARAMS = [
    {"name": "TAILSCALE_AUTHKEY", "label": "Chave de autenticação da Tailscale (tskey-auth-...)", "required": True, "secret": True},
    {"name": "TAILSCALE_HOSTNAME", "label": "Nome na tailnet (vazio = nome do computador)"},
]

# Pasted into a console (the "copy ready script" path for a machine without
# SSH), the script runs as whoever opened it; over SSH, as darckware (admin).
# Tailscale routing on an already-connected machine (2026-10-19, Marcelo:
# "script de ajuste do tailscale como por exemplo subrede, não rotear").
# `tailscale set` changes only the flag given, never the login or other prefs.
_TAILSCALE_ADJUST_PARAMS = [
    {"name": "AJUSTE", "label": "Ajuste", "required": True, "default": "ver_configuracao",
     "options": ["ver_configuracao", "anunciar_subrede", "parar_de_rotear", "aceitar_rotas", "nao_aceitar_rotas"]},
    {"name": "ROTAS", "label": "Sub-redes a anunciar (ex.: 192.168.0.0/24, separadas por vírgula)"},
]
_TAILSCALE_ADJUST_DESCRIPTION = (
    "Ajusta o roteamento da Tailscale numa máquina já conectada: anunciar sub-redes (a máquina vira roteador "
    "da rede local dela para a tailnet; a rota ainda precisa ser aprovada no painel da Tailscale), parar de "
    "anunciar, passar a usar ou deixar de usar as sub-redes anunciadas por outras máquinas. Cuidado: aceitar "
    "rotas numa máquina que está dentro da própria sub-rede anunciada pode desviar o tráfego local dela. "
    "Sempre mostra a configuração resultante."
)
_WIN_TAILSCALE_ADJUST = """$ErrorActionPreference = 'Stop'
$ts = Join-Path $env:ProgramFiles 'Tailscale\\tailscale.exe'
if (-not (Test-Path $ts)) { throw 'A Tailscale nao esta instalada nesta maquina' }
# tailscale.exe writes errors to stderr: read them under Continue, judge by the exit code.
function Invoke-Ts([string[]]$TsArgs) {
    $ErrorActionPreference = 'Continue'
    $out = & $ts @TsArgs 2>&1 | ForEach-Object { [string]$_ }
    $text = $out -join ' '
    if ($text -match 'already in use by ([^\\s,]+)' -or $text -match 'server mode \\("?([^"\\)]+)') {
        throw ("A Tailscale desta maquina pertence ao usuario $($Matches[1]) do Windows (foi conectada na sessao " +
               'dele) e so essa conta pode altera-la. Para o ForgeHub administrar, a Tailscale precisa ser ' +
               'reconectada pela conta darckware (instalador do ForgeHub com uma nova auth key).')
    }
    if ($LASTEXITCODE -ne 0) { throw "tailscale $($TsArgs -join ' ') falhou: $text" }
    $out
}
switch ($AJUSTE) {
    'anunciar_subrede' {
        $routes = @($ROTAS -split '[,; ]+' | Where-Object { $_ })
        if (-not $routes) { throw 'Informe as sub-redes (ex.: 192.168.0.0/24)' }
        foreach ($r in $routes) { if ($r -notmatch '^\\d{1,3}(\\.\\d{1,3}){3}/\\d{1,2}$') { throw "Sub-rede invalida: $r" } }
        Invoke-Ts @('set', "--advertise-routes=$($routes -join ',')") | Out-Null
        "Anunciando $($routes -join ', '). Aprove a rota no painel da Tailscale (Machines > Edit route settings)."
    }
    'parar_de_rotear' { Invoke-Ts @('set', '--advertise-routes=') | Out-Null; 'A maquina deixou de anunciar sub-redes.' }
    'aceitar_rotas' { Invoke-Ts @('set', '--accept-routes=true') | Out-Null; 'A maquina passou a usar as sub-redes anunciadas na tailnet.' }
    'nao_aceitar_rotas' { Invoke-Ts @('set', '--accept-routes=false') | Out-Null; 'A maquina deixou de usar as sub-redes anunciadas na tailnet.' }
}
$prefs = (Invoke-Ts @('debug', 'prefs')) -join "`n" | ConvertFrom-Json
'=== Configuracao atual'
"Sub-redes anunciadas: $(if ($prefs.AdvertiseRoutes) { $prefs.AdvertiseRoutes -join ', ' } else { 'nenhuma' })"
"Usa sub-redes da tailnet: $(if ($prefs.RouteAll) { 'sim' } else { 'nao' })"
"IP na tailnet: $((Invoke-Ts @('ip', '-4')) -join ' ')"
"""
_SH_TAILSCALE_ADJUST = """command -v tailscale >/dev/null 2>&1 || { echo "A Tailscale nao esta instalada nesta maquina" >&2; exit 2; }
# Reading needs no root; changing does.
if [ "$AJUSTE" != "ver_configuracao" ] && [ -n "$SUDO" ] && ! $SUDO true 2>/dev/null; then
    echo "A conta $(id -un) precisa de sudo sem senha para alterar a Tailscale (ou rode com a conta root)" >&2; exit 2
fi
case "$AJUSTE" in
    anunciar_subrede)
        ROUTES=$(echo "$ROTAS" | tr ';, ' '\\n\\n\\n' | grep -v '^$' | paste -sd, -)
        [ -n "$ROUTES" ] || { echo "Informe as sub-redes (ex.: 192.168.0.0/24)" >&2; exit 2; }
        for R in $(echo "$ROUTES" | tr ',' ' '); do
            echo "$R" | grep -Eq '^[0-9]{1,3}(\\.[0-9]{1,3}){3}/[0-9]{1,2}$' || { echo "Sub-rede invalida: $R" >&2; exit 2; }
        done
        # A Linux subnet router forwards packets itself: IP forwarding must be on (persisted).
        printf 'net.ipv4.ip_forward = 1\\nnet.ipv6.conf.all.forwarding = 1\\n' | $SUDO tee /etc/sysctl.d/99-tailscale.conf >/dev/null
        $SUDO sysctl -p /etc/sysctl.d/99-tailscale.conf >/dev/null
        $SUDO tailscale set --advertise-routes="$ROUTES"
        echo "Anunciando $ROUTES. Aprove a rota no painel da Tailscale (Machines > Edit route settings)."
        ;;
    parar_de_rotear)
        $SUDO tailscale set --advertise-routes=
        echo "A maquina deixou de anunciar sub-redes."
        ;;
    aceitar_rotas)
        $SUDO tailscale set --accept-routes=true
        echo "A maquina passou a usar as sub-redes anunciadas na tailnet."
        ;;
    nao_aceitar_rotas)
        $SUDO tailscale set --accept-routes=false
        echo "A maquina deixou de usar as sub-redes anunciadas na tailnet."
        ;;
esac
PREFS=$(tailscale debug prefs 2>/dev/null || $SUDO tailscale debug prefs)
ADV=$(echo "$PREFS" | tr -d ' \\t\\n' | grep -o '"AdvertiseRoutes":\\[[^]]*\\]' | sed 's/.*\\[//; s/\\]//; s/"//g')
echo "=== Configuracao atual"
echo "Sub-redes anunciadas: ${ADV:-nenhuma}"
echo "$PREFS" | grep -q '"RouteAll": *true' && echo "Usa sub-redes da tailnet: sim" || echo "Usa sub-redes da tailnet: nao"
echo "IP na tailnet: $(tailscale ip -4)"
"""

_WIN_REQUIRE_ADMIN = """$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Execute no PowerShell aberto como Administrador'
}
"""

_COMPONENTS_PARAM = {"name": "COMPONENTES", "label": "O que instalar", "required": True,
                     "default": "tailscale_e_rustdesk",
                     "options": ["tailscale_e_rustdesk", "somente_tailscale", "somente_rustdesk"]}
# Required only for the components that use them; the script checks.
_TAILSCALE_PARAMS_OPTIONAL = [
    {"name": "TAILSCALE_AUTHKEY", "label": "Chave de autenticação da Tailscale (tskey-auth-...; quando instalar a Tailscale)", "secret": True},
    {"name": "TAILSCALE_HOSTNAME", "label": "Nome na tailnet (vazio = nome do computador)"},
]

_RUSTDESK_NETWORK_PARAMS = [
    {"name": "RUSTDESK_ID_SERVER", "label": "Servidor de ID", "required": True,
     "vault_secret": RUSTDESK_SERVER_SECRET, "vault_field": "id_server"},
    {"name": "RUSTDESK_RELAY_SERVER", "label": "Servidor de Relay", "required": True,
     "vault_secret": RUSTDESK_SERVER_SECRET, "vault_field": "relay_server"},
    {"name": "RUSTDESK_KEY", "label": "Key", "required": True, "secret": True,
     "vault_secret": RUSTDESK_SERVER_SECRET, "vault_field": "key"},
]
_RUSTDESK_PASSWORD_PARAM = {"name": "RUSTDESK_PASSWORD", "label": "Senha permanente do RustDesk", "required": True, "secret": True}
_RUSTDESK_PASSWORD_OPTIONAL = {**_RUSTDESK_PASSWORD_PARAM, "required": False,
                               "label": "Senha permanente do RustDesk (quando instalar o RustDesk)"}

# Local user password change (2026-10-18, Marcelo: "preciso de uma para
# alteração da senha do usuário do windows ... campo para digitar do login e
# senha ... algumas propriedades do usuário"). "manter" leaves a property as
# it is. The maintenance account itself is refused: its password lives in
# ForgeVault and changes only through the machine's password rotation, which
# keeps the vault in step.
_KEEP = "manter"
_YES_NO_KEEP = [_KEEP, "sim", "nao"]
_USER_LOGIN_PARAM = {"name": "USER_LOGIN", "label": "Login do usuário", "required": True}
_USER_PASSWORD_PARAM = {"name": "USER_PASSWORD", "label": "Nova senha", "required": True, "secret": True}
_USER_FULL_NAME_PARAM = {"name": "USER_FULL_NAME", "label": "Nome completo (vazio = não alterar)"}
_MUST_CHANGE_PARAM = {"name": "MUST_CHANGE_AT_LOGON", "label": "Trocar a senha no próximo logon",
                      "default": "nao", "options": ["nao", "sim"]}
_NEVER_EXPIRES_PARAM = {"name": "PASSWORD_NEVER_EXPIRES", "label": "Senha nunca expira",
                        "default": _KEEP, "options": _YES_NO_KEEP}
_ACCOUNT_STATE_PARAM = {"name": "ACCOUNT_STATE", "label": "Conta",
                        "default": _KEEP, "options": [_KEEP, "ativa", "desativada"]}
_UNLOCK_PARAM = {"name": "UNLOCK_ACCOUNT", "label": "Desbloquear a conta (tentativas de senha erradas)",
                 "default": "sim", "options": ["sim", "nao"]}

_SH_USER_CHECKS = """[ -n "$USER_LOGIN" ] || { echo "Informe o login" >&2; exit 2; }
[ "$USER_LOGIN" != "darckware" ] || { echo "A conta darckware muda de senha pela rotacao da maquina (a senha fica na ForgeVault)" >&2; exit 2; }
id "$USER_LOGIN" >/dev/null 2>&1 || { echo "Usuario $USER_LOGIN nao existe nesta maquina" >&2; exit 2; }
if [ "$MUST_CHANGE_AT_LOGON" = "sim" ] && [ "$PASSWORD_NEVER_EXPIRES" = "sim" ]; then
    echo "Escolha entre 'trocar no proximo logon' e 'senha nunca expira'" >&2; exit 2
fi
"""

SYSTEM_SCRIPTS: list[dict] = [
    {
        "system_key": "user_password:windows",
        "name": "Alterar senha de usuário",
        "platform": "windows",
        "category": "contas",
        "risk": "change",
        "timeout_seconds": 120,
        "description": (
            "Define a senha de uma conta local do Windows e, opcionalmente, nome completo, descrição, "
            "\"trocar no próximo logon\", \"senha nunca expira\", \"usuário pode trocar a senha\", conta "
            "ativa/desativada e desbloqueio. \"manter\" não mexe na propriedade. Não vale para conta de "
            "domínio nem para a conta darckware (essa usa a rotação de senha da máquina)."
        ),
        "parameters": [
            _USER_LOGIN_PARAM, _USER_PASSWORD_PARAM, _USER_FULL_NAME_PARAM,
            {"name": "USER_DESCRIPTION", "label": "Descrição (vazio = não alterar)"},
            _MUST_CHANGE_PARAM, _NEVER_EXPIRES_PARAM,
            {"name": "USER_MAY_CHANGE_PASSWORD", "label": "Usuário pode trocar a senha",
             "default": _KEEP, "options": _YES_NO_KEEP},
            _ACCOUNT_STATE_PARAM, _UNLOCK_PARAM,
        ],
        "content": """$ErrorActionPreference = 'Stop'
if (-not $USER_LOGIN) { throw 'Informe o login' }
if ($USER_LOGIN -eq 'darckware') { throw 'A conta darckware muda de senha pela rotacao da maquina (a senha fica na ForgeVault)' }
$user = Get-LocalUser -Name $USER_LOGIN -ErrorAction SilentlyContinue
if (-not $user) { throw "Conta local $USER_LOGIN nao existe nesta maquina (conta de dominio nao e alterada aqui)" }
if ($MUST_CHANGE_AT_LOGON -eq 'sim' -and ($PASSWORD_NEVER_EXPIRES -eq 'sim' -or ($PASSWORD_NEVER_EXPIRES -eq 'manter' -and -not $user.PasswordExpires))) {
    throw "O Windows nao aceita 'trocar no proximo logon' com 'senha nunca expira': escolha 'nao' em 'senha nunca expira'"
}
if ($MUST_CHANGE_AT_LOGON -eq 'sim' -and $USER_MAY_CHANGE_PASSWORD -eq 'nao') {
    throw "'Trocar no proximo logon' exige que o usuario possa trocar a senha"
}
$set = @{ Name = $USER_LOGIN; Password = (ConvertTo-SecureString $USER_PASSWORD -AsPlainText -Force) }
if ($USER_FULL_NAME) { $set.FullName = $USER_FULL_NAME }
if ($USER_DESCRIPTION) { $set.Description = $USER_DESCRIPTION }
if ($PASSWORD_NEVER_EXPIRES -ne 'manter') { $set.PasswordNeverExpires = ($PASSWORD_NEVER_EXPIRES -eq 'sim') }
if ($USER_MAY_CHANGE_PASSWORD -ne 'manter') { $set.UserMayChangePassword = ($USER_MAY_CHANGE_PASSWORD -eq 'sim') }
Set-LocalUser @set
if ($ACCOUNT_STATE -eq 'ativa') { Enable-LocalUser -Name $USER_LOGIN }
if ($ACCOUNT_STATE -eq 'desativada') { Disable-LocalUser -Name $USER_LOGIN }
$adsi = [ADSI]"WinNT://./$USER_LOGIN,user"
if ($UNLOCK_ACCOUNT -eq 'sim' -and $adsi.IsAccountLocked) { $adsi.IsAccountLocked = $false; $adsi.SetInfo(); 'Conta desbloqueada' }
if ($MUST_CHANGE_AT_LOGON -eq 'sim') { $adsi.PasswordExpired = 1; $adsi.SetInfo() }
$u = Get-LocalUser -Name $USER_LOGIN
"Senha de $USER_LOGIN alterada"
"Conta ativa: $($u.Enabled) | Senha expira em: $(if ($u.PasswordExpires) { $u.PasswordExpires } else { 'nunca' }) | Pode trocar a senha: $($u.UserMayChangePassword) | Trocar no proximo logon: $($MUST_CHANGE_AT_LOGON -eq 'sim')"
""",
    },
    {
        "system_key": "user_password:linux",
        "name": "Alterar senha de usuário",
        "platform": "linux",
        "category": "contas",
        "risk": "change",
        "timeout_seconds": 120,
        "description": (
            "Define a senha de um usuário local do Linux e, opcionalmente, nome completo, \"trocar no próximo "
            "logon\", \"senha nunca expira\", conta ativa/bloqueada e desbloqueio de tentativas erradas "
            "(faillock). \"manter\" não mexe na propriedade. Não vale para a conta darckware (rotação da máquina)."
        ),
        "parameters": [
            _USER_LOGIN_PARAM, _USER_PASSWORD_PARAM, _USER_FULL_NAME_PARAM,
            _MUST_CHANGE_PARAM, _NEVER_EXPIRES_PARAM, _ACCOUNT_STATE_PARAM, _UNLOCK_PARAM,
        ],
        # chpasswd reads the password on stdin, so it never shows in a process list.
        "content": _SH_PRELUDE + _SH_USER_CHECKS + """printf '%s:%s\\n' "$USER_LOGIN" "$USER_PASSWORD" | $SUDO chpasswd
[ -z "$USER_FULL_NAME" ] || $SUDO usermod -c "$USER_FULL_NAME" "$USER_LOGIN"
[ "$PASSWORD_NEVER_EXPIRES" != "sim" ] || $SUDO chage -M -1 "$USER_LOGIN"
[ "$PASSWORD_NEVER_EXPIRES" != "nao" ] || $SUDO chage -M 90 "$USER_LOGIN"
[ "$ACCOUNT_STATE" != "ativa" ] || { $SUDO usermod -U "$USER_LOGIN"; $SUDO chage -E -1 "$USER_LOGIN"; }
[ "$ACCOUNT_STATE" != "desativada" ] || { $SUDO usermod -L "$USER_LOGIN"; $SUDO chage -E 0 "$USER_LOGIN"; }
if [ "$UNLOCK_ACCOUNT" = "sim" ] && command -v faillock >/dev/null 2>&1; then $SUDO faillock --user "$USER_LOGIN" --reset; fi
[ "$MUST_CHANGE_AT_LOGON" != "sim" ] || $SUDO chage -d 0 "$USER_LOGIN"
echo "Senha de $USER_LOGIN alterada"
$SUDO chage -l "$USER_LOGIN"
""",
    },
    {
        "system_key": "user_password:macos",
        "name": "Alterar senha de usuário",
        "platform": "macos",
        "category": "contas",
        "risk": "change",
        "timeout_seconds": 120,
        "description": (
            "Define a senha de um usuário local do macOS e, opcionalmente, nome completo, \"trocar no próximo "
            "logon\" e conta ativa/desativada. Atenção: a troca feita pelo administrador não atualiza as "
            "chaves do usuário (Keychain) e, com FileVault, a senha de desbloqueio do disco pode continuar a "
            "antiga até o usuário entrar. Não vale para a conta darckware (rotação da máquina)."
        ),
        "parameters": [
            _USER_LOGIN_PARAM, _USER_PASSWORD_PARAM, _USER_FULL_NAME_PARAM,
            _MUST_CHANGE_PARAM, _ACCOUNT_STATE_PARAM,
        ],
        "content": _SH_PRELUDE + _SH_USER_CHECKS + """$SUDO dscl . -passwd "/Users/$USER_LOGIN" "$USER_PASSWORD"
[ -z "$USER_FULL_NAME" ] || $SUDO dscl . -create "/Users/$USER_LOGIN" RealName "$USER_FULL_NAME"
[ "$ACCOUNT_STATE" != "ativa" ] || $SUDO pwpolicy -u "$USER_LOGIN" -enableuser
[ "$ACCOUNT_STATE" != "desativada" ] || $SUDO pwpolicy -u "$USER_LOGIN" -disableuser
[ "$MUST_CHANGE_AT_LOGON" != "sim" ] || $SUDO pwpolicy -u "$USER_LOGIN" -setpolicy "newPasswordRequired=1"
echo "Senha de $USER_LOGIN alterada"
""",
    },
    {
        "system_key": "tailscale_install:windows",
        "name": "Instalar Tailscale",
        "platform": "windows",
        "category": "tailscale",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o Tailscale (instalador oficial validado pelo darckware-remote) e conecta a máquina à "
            "tailnet com a chave informada. Se já estiver conectada, não mexe na conexão."
        ),
        "parameters": _TAILSCALE_PARAMS,
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
        "category": "tailscale",
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
        "category": "tailscale",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o Tailscale (script oficial) e conecta a máquina à tailnet com a chave informada. "
            "Se já estiver conectada, não mexe na conexão."
        ),
        "parameters": _TAILSCALE_PARAMS,
        "content": _SH_PRELUDE + _SH_TAILSCALE_UP,
    },
    {
        "system_key": "tailscale_adjust:windows",
        "name": "Ajustar roteamento da Tailscale",
        "platform": "windows",
        "category": "tailscale",
        "risk": "change",
        "timeout_seconds": 120,
        "description": _TAILSCALE_ADJUST_DESCRIPTION,
        "parameters": _TAILSCALE_ADJUST_PARAMS,
        "content": _WIN_TAILSCALE_ADJUST,
    },
    {
        "system_key": "tailscale_adjust:linux",
        "name": "Ajustar roteamento da Tailscale",
        "platform": "linux",
        "category": "tailscale",
        "risk": "change",
        "timeout_seconds": 120,
        "description": _TAILSCALE_ADJUST_DESCRIPTION,
        "parameters": _TAILSCALE_ADJUST_PARAMS,
        "content": _SH_PRELUDE + _SH_TAILSCALE_ADJUST,
    },
    {
        "system_key": "rustdesk_install:windows",
        "name": "Instalar RustDesk",
        "platform": "windows",
        "category": "rustdesk",
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
        "category": "rustdesk",
        "risk": "change",
        "timeout_seconds": 900,
        "description": (
            "Instala o RustDesk 1.4.9 (Debian/Ubuntu, x86_64), configura o servidor de ID/Relay e a Key e define "
            "a senha permanente. Só para máquinas com interface gráfica — não instalar em servidor sem tela."
        ),
        "parameters": [*_RUSTDESK_NETWORK_PARAMS, _RUSTDESK_PASSWORD_PARAM],
        "content": _SH_PRELUDE + _SH_RUSTDESK_INSTALL,
    },
    {
        "system_key": "remote_access_install:windows",
        "name": "Instalador Darckware Remoto",
        "platform": "windows",
        "category": "acesso_remoto",
        "risk": "change",
        "timeout_seconds": 1200,
        "description": (
            "O instalador darckware-remote com as mesmas opções da tela dele: Tailscale e RustDesk, só "
            "Tailscale ou só RustDesk. Só RustDesk chega ao servidor pela Tailscale desta máquina ou por um host "
            "Tailscale da rede local configurado como roteador de sub-rede (cria a rota do servidor RustDesk via "
            "o IP dele). No fim valida Tailscale, rota, serviço e portas do RustDesk e mostra o ID. Roda por SSH "
            "ou colado no PowerShell como Administrador. A senha e o ID do RustDesk ficam no cadastro da máquina."
        ),
        "parameters": [
            _COMPONENTS_PARAM, *_TAILSCALE_PARAMS_OPTIONAL,
            {"name": "CONEXAO_RUSTDESK", "label": "Conexão do RustDesk (só quando instalar somente o RustDesk)",
             "default": "tailscale_local", "options": ["tailscale_local", "roteador_subrede"]},
            {"name": "ROUTER_IP", "label": "IPv4 na rede local do host Tailscale roteador (modo roteador)"},
            {"name": "SUBSTITUIR_ROTA", "label": "Substituir a rota que o instalador criou antes (modo roteador)",
             "default": "nao", "options": ["nao", "sim"]},
            *_RUSTDESK_NETWORK_PARAMS, _RUSTDESK_PASSWORD_OPTIONAL,
        ],
        "content": _WIN_REQUIRE_ADMIN + _WIN_FETCH_INSTALLER + _WIN_RUSTDESK_CLI + """
$wantTs = $COMPONENTES -ne 'somente_rustdesk'
$wantRd = $COMPONENTES -ne 'somente_tailscale'
$router = $COMPONENTES -eq 'somente_rustdesk' -and $CONEXAO_RUSTDESK -eq 'roteador_subrede'
if ($wantTs -and -not $TAILSCALE_AUTHKEY) { throw 'Informe a chave de autenticacao da Tailscale' }
if ($wantRd -and -not $RUSTDESK_PASSWORD) { throw 'Informe a senha permanente do RustDesk' }
if ($router -and -not ($ROUTER_IP -match '^\\d{1,3}(\\.\\d{1,3}){3}$')) { throw 'Informe o IPv4 do host roteador na rede local' }
$cfgPath = Join-Path $dir 'config\\deployment.json'
$cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json
$cfg.rustdesk.idServer = $RUSTDESK_ID_SERVER
$cfg.rustdesk.relayServer = $RUSTDESK_RELAY_SERVER
$cfg.rustdesk.publicKey = $RUSTDESK_KEY
$cfg.route.destinationPrefix = "$RUSTDESK_ID_SERVER/32"
$cfg | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $cfgPath
$hn = if ($TAILSCALE_HOSTNAME) { $TAILSCALE_HOSTNAME } else { $env:COMPUTERNAME.ToLower() }
$installerArgs = @('-NonInteractive')
$sec = New-SecretDir
try {
    if ($wantTs) {
        [IO.File]::WriteAllText((Join-Path $sec 'ts.txt'), $TAILSCALE_AUTHKEY)
        $installerArgs += @('-InstallTailscale', '-TailscaleHostname', $hn, '-TailscaleAuthKeyFile', (Join-Path $sec 'ts.txt'))
    }
    if ($wantRd) {
        [IO.File]::WriteAllText((Join-Path $sec 'rd.txt'), $RUSTDESK_PASSWORD)
        $installerArgs += @('-InstallRustDesk', '-RustDeskPasswordFile', (Join-Path $sec 'rd.txt'))
        if (-not $wantTs) {
            if ($router) {
                $installerArgs += @('-ConnectivityMode', 'Router', '-RouterIp', $ROUTER_IP)
                if ($SUBSTITUIR_ROTA -eq 'sim') { $installerArgs += '-ConfirmRouteReplacement' }
            } else { $installerArgs += @('-ConnectivityMode', 'LocalTailscale') }
        }
    }
    Invoke-Installer $installerArgs
} finally { Remove-Item -Recurse -Force $sec -ErrorAction SilentlyContinue }

'=== Validacao'
$failed = @()
if ($wantTs -or -not $router) {
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like 'Tailscale*' -and $_.IPAddress -like '100.*' } | ForEach-Object { $_.IPAddress })
    if ($ips.Count) { "Tailscale: conectada ($($ips -join ' '))" } else { 'Tailscale: SEM endereco na tailnet'; $failed += 'Tailscale' }
}
if ($router) {
    $route = Get-NetRoute -DestinationPrefix "$RUSTDESK_ID_SERVER/32" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($route -and $route.NextHop -eq $ROUTER_IP) { "Rota: $RUSTDESK_ID_SERVER/32 via $ROUTER_IP" }
    else { "Rota: $RUSTDESK_ID_SERVER/32 NAO aponta para $ROUTER_IP"; $failed += 'Rota' }
}
if ($wantRd) {
    $svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq 'Running') { 'Servico RustDesk: em execucao' } else { 'Servico RustDesk: PARADO ou ausente'; $failed += 'Servico RustDesk' }
    foreach ($port in $cfg.rustdesk.tcpPorts) {
        $okPort = (Test-NetConnection $RUSTDESK_ID_SERVER -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded
        "Porta $($RUSTDESK_ID_SERVER):$($port): $(if ($okPort) { 'acessivel' } else { 'SEM resposta' })"
        if (-not $okPort) { $failed += "Porta $port" }
    }
    $id = (Invoke-RustDesk @('--get-id')).Out
    if ($id) { "RUSTDESK_ID=$id" } else { $failed += 'ID do RustDesk' }
}
if ($failed.Count) { throw "Validacao falhou: $($failed -join ', ')" }
'Validacao concluida'
""",
    },
    {
        "system_key": "remote_access_install:linux",
        "name": "Instalador Darckware Remoto",
        "platform": "linux",
        "category": "acesso_remoto",
        "risk": "change",
        "timeout_seconds": 1200,
        "description": (
            "Tailscale e RustDesk, só Tailscale ou só RustDesk (Tailscale pelo script oficial; RustDesk 1.4.9 "
            "para Debian/Ubuntu x86_64 com servidor de ID/Relay, Key e senha). No fim valida a Tailscale, as "
            "portas do servidor RustDesk e mostra o ID. Roda por SSH ou colado num terminal com sudo. RustDesk "
            "só em máquina com interface gráfica; o modo roteador do darckware-remote existe só no Windows."
        ),
        "parameters": [_COMPONENTS_PARAM, *_TAILSCALE_PARAMS_OPTIONAL, *_RUSTDESK_NETWORK_PARAMS, _RUSTDESK_PASSWORD_OPTIONAL],
        "content": _SH_PRELUDE + """WANT_TS=1; WANT_RD=1
[ "$COMPONENTES" != "somente_rustdesk" ] || WANT_TS=0
[ "$COMPONENTES" != "somente_tailscale" ] || WANT_RD=0
[ "$WANT_TS" = 0 ] || [ -n "$TAILSCALE_AUTHKEY" ] || { echo "Informe a chave de autenticacao da Tailscale" >&2; exit 2; }
[ "$WANT_RD" = 0 ] || [ -n "$RUSTDESK_PASSWORD" ] || { echo "Informe a senha permanente do RustDesk" >&2; exit 2; }
if [ "$WANT_TS" = 1 ]; then
""" + _SH_TAILSCALE_UP + """fi
if [ "$WANT_RD" = 1 ]; then
""" + _SH_RUSTDESK_SETUP + """RD_ID="$($SUDO rustdesk --get-id)"
fi
echo "=== Validacao"
FAILED=""
if command -v tailscale >/dev/null 2>&1 && TS_IP=$(tailscale ip -4 2>/dev/null) && [ -n "$TS_IP" ]; then
    echo "Tailscale: conectada ($TS_IP)"
else
    echo "Tailscale: SEM endereco na tailnet"; FAILED="$FAILED Tailscale"
fi
if [ "$WANT_RD" = 1 ]; then
    for PORT in 21116 21117; do
        if timeout 5 bash -c "</dev/tcp/$RUSTDESK_ID_SERVER/$PORT" 2>/dev/null || nc -z -w 5 "$RUSTDESK_ID_SERVER" "$PORT" 2>/dev/null; then
            echo "Porta $RUSTDESK_ID_SERVER:$PORT: acessivel"
        else
            echo "Porta $RUSTDESK_ID_SERVER:$PORT: SEM resposta"; FAILED="$FAILED porta-$PORT"
        fi
    done
    if [ -n "$RD_ID" ]; then echo "RUSTDESK_ID=$RD_ID"; else FAILED="$FAILED ID-RustDesk"; fi
fi
[ -z "$FAILED" ] || { echo "Validacao falhou:$FAILED" >&2; exit 1; }
echo "Validacao concluida"
""",
    },
    {
        "system_key": "rustdesk_get_id:windows",
        "name": "Obter ID do RustDesk",
        "platform": "windows",
        "category": "rustdesk",
        "risk": "read",
        "timeout_seconds": 90,
        "description": (
            "Lê o ID do RustDesk já instalado na máquina e grava no cadastro (coluna ID RustDesk). "
            "Não altera nada na máquina; útil quando o RustDesk não foi instalado pelo ForgeHub."
        ),
        "parameters": [],
        "content": "$ErrorActionPreference = 'Stop'\n" + _WIN_RUSTDESK_CLI + """
$svc = Get-Service RustDesk -ErrorAction SilentlyContinue
"Servico RustDesk: $(if ($svc) { $svc.Status } else { 'nao encontrado' })"
$id = (Invoke-RustDesk @('--get-id')).Out
if ($id -notmatch '^\\d{6,15}$') { throw "O RustDesk nao devolveu um ID valido ('$id'); confira se o servico esta rodando" }
"RUSTDESK_ID=$id"
""",
    },
    {
        "system_key": "rustdesk_get_id:linux",
        "name": "Obter ID do RustDesk",
        "platform": "linux",
        "category": "rustdesk",
        "risk": "read",
        "timeout_seconds": 90,
        "description": (
            "Lê o ID do RustDesk já instalado na máquina e grava no cadastro (coluna ID RustDesk). "
            "Não altera nada na máquina; útil quando o RustDesk não foi instalado pelo ForgeHub."
        ),
        "parameters": [],
        "content": _SH_PRELUDE + """command -v rustdesk >/dev/null 2>&1 || { echo "O RustDesk nao esta instalado nesta maquina" >&2; exit 2; }
echo "Servico RustDesk: $(systemctl is-active rustdesk 2>/dev/null || echo desconhecido)"
ID=$($SUDO rustdesk --get-id 2>/dev/null | tr -d '[:space:]')
echo "$ID" | grep -Eq '^[0-9]{6,15}$' || { echo "O RustDesk nao devolveu um ID valido ('$ID')" >&2; exit 1; }
echo "RUSTDESK_ID=$ID"
""",
    },
    {
        "system_key": "rustdesk_password:windows",
        "name": "Trocar senha do RustDesk",
        "platform": "windows",
        "category": "rustdesk",
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
        "category": "rustdesk",
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


# How the library groups the scripts (2026-10-19, Marcelo: "os scripts precisam
# serem classificados. Exemplo: tailscale, rustdesk, criação de conta,
# manutenção"). Created on startup when missing; never renamed afterwards.
SYSTEM_CATEGORIES = [
    ("tailscale", "Tailscale", "Instalação e ajustes da Tailscale"),
    ("rustdesk", "RustDesk", "Instalação e senha do RustDesk"),
    ("acesso_remoto", "Acesso remoto", "Instalador Darckware Remoto (Tailscale + RustDesk)"),
    ("contas", "Contas de usuário", "Criação de contas, senhas e propriedades de usuários"),
    ("manutencao", "Manutenção", None),
]


async def seed_system_scripts() -> int:
    """Creates missing system scripts and versions changed ones. Idempotent;
    safe when two processes (dev + production) start together."""
    from app.db.base import AsyncSessionLocal
    from app.db.models.host_script import HostScript, HostScriptCategory, HostScriptVersion

    changed = 0
    async with AsyncSessionLocal() as db:
        categories = {c.slug: c.id for c in (await db.execute(select(HostScriptCategory))).scalars()}
        for slug, label, description in SYSTEM_CATEGORIES:
            if slug not in categories:
                category = HostScriptCategory(slug=slug, label=label, description=description)
                db.add(category)
                await db.flush()
                categories[slug] = category.id
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
