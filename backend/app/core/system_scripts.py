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
    [ -n "$TAILSCALE_AUTHKEY" ] || { echo "Informe a chave de autenticacao da Tailscale" >&2; exit 2; }
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

# Left blank, the auth key is minted by ForgeHub through the Tailscale API: one
# single-use, NOT pre-authorized key per machine, carrying this tag -- each
# machine then waits for a person to approve it in the Tailscale console
# (2026-10-20, Marcelo: "Gerar, com aprovação no painel").
AUTO_AUTHKEY_TAG = "TAILSCALE_TAG"
_TAILSCALE_TAG_PARAM = {"name": AUTO_AUTHKEY_TAG, "label": "Tag da Tailscale (ex.: tag:gatling-users; quando o ForgeHub gera a chave)"}
_TAILSCALE_PARAMS = [
    {"name": "TAILSCALE_AUTHKEY", "label": "Chave de autenticação da Tailscale (tskey-auth-...)", "secret": True},
    _TAILSCALE_TAG_PARAM,
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
    _TAILSCALE_TAG_PARAM,
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
if (-not $TAILSCALE_AUTHKEY) { throw 'Informe a chave de autenticacao da Tailscale' }
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
        "system_key": "rustdesk_firewall:windows",
        "name": "Liberar o RustDesk no firewall do Windows",
        "platform": "windows",
        "category": "rustdesk",
        "risk": "change",
        "timeout_seconds": 120,
        "description": (
            "Cria (ou recria) as regras do Firewall do Windows para o programa do RustDesk, entrada e saída, e "
            "testa as portas do servidor RustDesk da Darckware (lido do ForgeVault). Use quando o RustDesk não "
            "conecta numa máquina com firewall restritivo. Remove só as regras que ele mesmo criou."
        ),
        "parameters": [
            {"name": "PERFIS", "label": "Perfis de rede", "required": True, "default": "todos",
             "options": ["todos", "dominio_e_privado"]},
            {"name": "RUSTDESK_ID_SERVER", "label": "Servidor de ID", "required": True,
             "vault_secret": RUSTDESK_SERVER_SECRET, "vault_field": "id_server"},
        ],
        "content": r"""$ErrorActionPreference = 'Stop'
$exe = Join-Path $env:ProgramFiles 'RustDesk\rustdesk.exe'
if (-not (Test-Path $exe)) { throw 'O RustDesk nao esta instalado nesta maquina' }
$profile = if ($PERFIS -eq 'dominio_e_privado') { 'Domain,Private' } else { 'Any' }
$group = 'Darckware RustDesk'
Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue | Remove-NetFirewallRule
foreach ($dir in 'Inbound', 'Outbound') {
    New-NetFirewallRule -DisplayName "RustDesk ($dir)" -Group $group -Direction $dir -Program $exe `
        -Action Allow -Profile $profile | Out-Null
}
"Regras criadas: RustDesk entrada e saida (perfis: $profile)"
$svc = Get-Service RustDesk -ErrorAction SilentlyContinue
"Servico RustDesk: $(if ($svc) { $svc.Status } else { 'nao encontrado' })"
$failed = @()
foreach ($port in 21116, 21117) {
    $ok = (Test-NetConnection $RUSTDESK_ID_SERVER -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded
    "Porta $($RUSTDESK_ID_SERVER):$($port): $(if ($ok) { 'acessivel' } else { 'SEM resposta' })"
    if (-not $ok) { $failed += $port }
}
if ($failed) { throw "Firewall liberado, mas o servidor RustDesk nao responde nas portas $($failed -join ', ') (rota/Tailscale)" }
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


# Monitoring (2026-11-11, Marcelo: "só vou liberar comandos simples para os
# agentes hermes, como monitoramento, serviços e somente de leitura e
# acompanhamento"). Every one but the reachability probe is risk "read": it
# only reads state, never starts, stops or changes anything, and never elevates
# (no sudo, no SUDO prelude) -- what the login can't read is reported in words.
# Each parameter is validated twice: by its `pattern`/`options` in ForgeHub
# before anything runs, and again in the script, which may also be pasted into
# a console.
_LINES_PATTERN = r"[1-9]|[1-9][0-9]|[1-4][0-9]{2}|500"  # 1-500
_PORT_PATTERN = r"[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]"
_TIMEOUT_PATTERN = r"[1-9]|10"  # seconds
# One machine only: a hostname (with a letter) or an IPv4 address. No list,
# range, CIDR or IPv6.
_IPV4_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
_HOST_PATTERN = (rf"{_IPV4_OCTET}(?:\.{_IPV4_OCTET}){{3}}"
                 r"|(?=[A-Za-z0-9.-]{1,253}\Z)(?=.*[A-Za-z])"
                 r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")
_UNIT_PATTERN = r"[A-Za-z0-9][A-Za-z0-9@._:-]{0,127}"
# Journal units whose lines carry logins, sessions, elevated commands or cron
# job command lines (which can hold secrets): never readable with the "read"
# ceiling (supervisor decision, 2026-11-11; cron: Marcelo, same day).
_JOURNAL_UNIT_PATTERN = r"(?!(?:sshd?|sudo|systemd-logind|cron|crond|cronie|anacron)(?:[@.]|$))(?!.*[Aa][Uu][Tt][Hh])" + _UNIT_PATTERN
_WIN_SERVICE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9 ._@$-]{0,127}"
_CONTAINER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
# Log files a "read" agent may see, relative to /var/log. Never auth.log,
# secure, sudo logs or wtmp/btmp/lastlog (logins and elevated commands).
LINUX_LOG_FILES = ["syslog", "messages", "kern.log", "dpkg.log", "apt/history.log", "nginx/access.log",
                   "nginx/error.log", "apache2/access.log", "apache2/error.log"]
# Windows event logs a "read" agent may see. Never Security (command lines,
# 4688) or PowerShell's own logs (script blocks, 4104, can hold ForgeHub's
# rendered scripts with their parameter values).
WINDOWS_EVENT_LOGS = ["System", "Application", "Setup"]

_LINES_PARAM = {"name": "LINHAS", "label": "Quantidade de linhas/eventos (1 a 500)", "default": "100",
                "pattern": _LINES_PATTERN}
_LINUX_SERVICE_PARAM = {"name": "SERVICO", "label": "Serviço (unidade systemd, ex.: nginx; vazio = listar)",
                        "pattern": _UNIT_PATTERN}
_CONTAINER_PARAM = {"name": "CONTAINER", "label": "Container (nome ou id; vazio = listar todos)",
                    "pattern": _CONTAINER_PATTERN}
_REACHABILITY_PARAMS = [
    {"name": "ALVO_HOST", "label": "Host a testar (nome ou IPv4)", "required": True, "pattern": _HOST_PATTERN},
    {"name": "ALVO_PORTA", "label": "Porta a testar (1 a 65535)", "required": True, "pattern": _PORT_PATTERN},
    {"name": "TEMPO_LIMITE", "label": "Tempo limite em segundos (1 a 10)", "default": "5", "pattern": _TIMEOUT_PATTERN},
]

_SH_CHECK_LINES = """case "$LINHAS" in ''|*[!0-9]*) echo "LINHAS deve ser um numero de 1 a 500" >&2; exit 2;; esac
[ "$LINHAS" -ge 1 ] && [ "$LINHAS" -le 500 ] || { echo "LINHAS deve ser um numero de 1 a 500" >&2; exit 2; }
"""
_SH_CHECK_UNIT = """case "$SERVICO" in -*|*[!A-Za-z0-9@._:-]*) echo "Nome de servico invalido: $SERVICO" >&2; exit 2;; esac
"""
_SH_DOCKER_READY = """command -v docker >/dev/null 2>&1 || { echo "O Docker nao esta instalado nesta maquina" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "O Docker nao respondeu a esta conta (servico parado ou conta fora do grupo docker). Este script so le e nao tenta elevacao." >&2; exit 2; }
"""
# PowerShell's `$` also matches before a trailing newline: every in-script
# check anchors with \z and is case-sensitive (-cnotmatch).
_PS_CHECK_LINES = """if ($LINHAS -cnotmatch '^[0-9]{1,3}\\z' -or [int]$LINHAS -lt 1 -or [int]$LINHAS -gt 500) { throw 'LINHAS deve ser um numero de 1 a 500' }
"""
_PS_DOCKER_READY = """$ErrorActionPreference = 'Continue'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'O Docker nao esta instalado nesta maquina' }
& docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'O Docker nao respondeu a esta conta (servico parado ou sem permissao). Este script so le e nao tenta elevacao.' }
"""

MONITORING_SCRIPTS: list[dict] = [
    {
        "system_key": "monitor_state:linux",
        "name": "Estado da máquina",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": "Somente leitura: há quanto tempo está ligada, carga, memória e espaço em disco.",
        "parameters": [],
        "content": """echo "Maquina: $(hostname) | $(uname -sr)"
echo "Ligada: $(uptime -p 2>/dev/null || uptime)"
echo "Carga (1/5/15 min): $(cut -d' ' -f1-3 /proc/loadavg) | CPUs: $(nproc 2>/dev/null || echo '?')"
echo "Memoria:"
free -h 2>/dev/null || head -3 /proc/meminfo
echo "Discos:"
df -hP -x tmpfs -x devtmpfs -x squashfs -x overlay 2>/dev/null || df -hP
""",
    },
    {
        "system_key": "monitor_state:windows",
        "name": "Estado da máquina",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": "Somente leitura: há quanto tempo está ligada, carga da CPU, memória e espaço em disco.",
        "parameters": [],
        "content": """$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$up = (Get-Date) - $os.LastBootUpTime
"Maquina: $env:COMPUTERNAME | $($os.Caption) $($os.Version)"
"Ligada ha: $($up.Days)d $($up.Hours)h $($up.Minutes)min (desde $($os.LastBootUpTime))"
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
"Carga da CPU: $cpu% | Processadores logicos: $($env:NUMBER_OF_PROCESSORS)"
"Memoria: $([math]::Round($os.FreePhysicalMemory / 1MB, 1)) GB livres de $([math]::Round($os.TotalVisibleMemorySize / 1MB, 1)) GB"
'Discos:'
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
    "  $($_.DeviceID) $([math]::Round($_.FreeSpace / 1GB, 1)) GB livres de $([math]::Round($_.Size / 1GB, 1)) GB"
}
""",
    },
    {
        "system_key": "monitor_services:linux",
        "name": "Serviços",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": ("Somente leitura: sem serviço informado, lista os serviços em execução e os com falha; "
                        "com um serviço, mostra o estado dele (systemctl show, sem linha de comando dos processos). "
                        "Nunca inicia nem para."),
        "parameters": [_LINUX_SERVICE_PARAM],
        # Not `systemctl status`: it prints every process's full command line,
        # which can carry a --password=.
        "content": """command -v systemctl >/dev/null 2>&1 || { echo "Esta maquina nao usa systemd" >&2; exit 2; }
if [ -z "$SERVICO" ]; then
    echo "Servicos em execucao:"
    systemctl list-units --type=service --state=running --no-pager --no-legend
    echo ""
    echo "Servicos com falha:"
    systemctl list-units --type=service --state=failed --no-pager --no-legend
    exit 0
fi
""" + _SH_CHECK_UNIT + """INFO=$(systemctl show -p LoadState,ActiveState,SubState,UnitFileState,MainPID,ActiveEnterTimestamp -- "$SERVICO" 2>/dev/null) \\
    || { echo "Nao foi possivel ler o servico $SERVICO" >&2; exit 2; }
case "$INFO" in *LoadState=not-found*) echo "Servico nao encontrado: $SERVICO" >&2; exit 2;; esac
echo "Servico: $SERVICO"
echo "$INFO"
echo "Estado: $(systemctl is-active -- "$SERVICO" 2>/dev/null)"
""",
    },
    {
        "system_key": "monitor_services:windows",
        "name": "Serviços",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": ("Somente leitura: sem serviço informado, lista os serviços (estado e tipo de início); "
                        "com um serviço, mostra nome, estado e tipo de início (Get-Service). Nunca inicia nem para."),
        "parameters": [{"name": "SERVICO", "label": "Serviço (nome, ex.: Spooler; vazio = listar)",
                        "pattern": _WIN_SERVICE_PATTERN}],
        # Name, display name, status and start type only: never the binary
        # path or command line, which can carry a password.
        "content": """$ErrorActionPreference = 'Stop'
if (-not $SERVICO) {
    Get-Service | Sort-Object Status, Name | Format-Table -AutoSize Status, StartType, Name, DisplayName | Out-String -Width 250
    return
}
if ($SERVICO -cnotmatch '^[A-Za-z0-9][A-Za-z0-9 ._@$-]{0,127}\\z') { throw "Nome de servico invalido: $SERVICO" }
$s = Get-Service -Name $SERVICO -ErrorAction SilentlyContinue
if (-not $s) { throw "Servico nao encontrado: $SERVICO" }
"Servico: $($s.Name) ($($s.DisplayName))"
"Estado: $($s.Status) | Inicio: $($s.StartType)"
""",
    },
    {
        "system_key": "monitor_containers:linux",
        "name": "Containers (Docker)",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": ("Somente leitura: sem container informado, lista todos (docker ps -a); com um, mostra "
                        "estado, saúde, início e reinícios. Precisa de Docker acessível pela conta sem elevação; "
                        "senão, diz isso e não lê nada."),
        "parameters": [_CONTAINER_PARAM],
        "content": _SH_DOCKER_READY + """if [ -z "$CONTAINER" ]; then
    docker ps -a --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'
    exit 0
fi
case "$CONTAINER" in -*|*[!A-Za-z0-9_.-]*) echo "Nome de container invalido: $CONTAINER" >&2; exit 2;; esac
docker inspect --type container --format 'Nome: {{.Name}} | Estado: {{.State.Status}} | Saude: {{if .State.Health}}{{.State.Health.Status}}{{else}}sem healthcheck{{end}} | Iniciado: {{.State.StartedAt}} | Reinicios: {{.RestartCount}} | Imagem: {{.Config.Image}}' -- "$CONTAINER" \\
    || { echo "Container nao encontrado: $CONTAINER" >&2; exit 2; }
""",
    },
    {
        "system_key": "monitor_containers:windows",
        "name": "Containers (Docker)",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": ("Somente leitura: sem container informado, lista todos (docker ps -a); com um, mostra "
                        "estado, saúde, início e reinícios. Precisa de Docker acessível pela conta; senão, diz isso."),
        "parameters": [_CONTAINER_PARAM],
        "content": _PS_DOCKER_READY + """if (-not $CONTAINER) {
    & docker ps -a --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'
    return
}
if ($CONTAINER -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\\z') { throw "Nome de container invalido: $CONTAINER" }
& docker inspect --type container --format 'Nome: {{.Name}} | Estado: {{.State.Status}} | Saude: {{if .State.Health}}{{.State.Health.Status}}{{else}}sem healthcheck{{end}} | Iniciado: {{.State.StartedAt}} | Reinicios: {{.RestartCount}} | Imagem: {{.Config.Image}}' $CONTAINER
if ($LASTEXITCODE -ne 0) { throw "Container nao encontrado: $CONTAINER" }
""",
    },
    {
        "system_key": "monitor_logs:linux",
        "name": "Logs",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 90,
        "description": ("Somente leitura: as últimas N linhas (1 a 500) do journal de um serviço ou de um arquivo "
                        "de uma lista fixa em /var/log (syslog, kern.log, nginx, apache...). Logs de login, sessão "
                        "e elevação (auth.log, secure, sshd, sudo, logind) e o journal do cron são recusados, e as "
                        "linhas do cron são retiradas dos arquivos (podem trazer senhas na linha de comando); o "
                        "que a conta não pode ler é informado, sem elevação."),
        "parameters": [
            {"name": "ORIGEM", "label": "Origem", "default": "servico", "options": ["servico", "arquivo"]},
            {"name": "SERVICO", "label": "Serviço (unidade systemd, quando a origem é serviço)",
             "pattern": _JOURNAL_UNIT_PATTERN},
            {"name": "ARQUIVO", "label": "Arquivo em /var/log (quando a origem é arquivo)",
             "options": LINUX_LOG_FILES},
            _LINES_PARAM,
        ],
        "content": _SH_CHECK_LINES + """if [ "$ORIGEM" = "arquivo" ]; then
    case "$ARQUIVO" in
        """ + "|".join(LINUX_LOG_FILES) + """) ;;
        *) echo "Arquivo fora da lista permitida: $ARQUIVO" >&2; exit 2;;
    esac
    REAL=$(readlink -f -- "/var/log/$ARQUIVO" 2>/dev/null || true)
    case "$REAL" in /var/log/*) ;; *) echo "O arquivo (ou o link) sai de /var/log/: recusado" >&2; exit 2;; esac
    [ -f "$REAL" ] || { echo "Arquivo nao encontrado: /var/log/$ARQUIVO" >&2; exit 2; }
    [ -r "$REAL" ] || { echo "Esta conta nao pode ler /var/log/$ARQUIVO (o script nao tenta elevacao)" >&2; exit 2; }
    # At most the last 1 MiB is read, whatever the file's size. Cron lines
    # (CRON[..]/crond[..]/anacron[..]) are dropped: they carry job command lines.
    tail -c 1048576 < "$REAL" | grep -viE '(ana)?cron(d|ie)?\\[' | tail -n "$LINHAS"
    exit 0
fi
[ "$ORIGEM" = "servico" ] || { echo "ORIGEM deve ser servico ou arquivo" >&2; exit 2; }
[ -n "$SERVICO" ] || { echo "Informe o servico" >&2; exit 2; }
""" + _SH_CHECK_UNIT + """BASE=${SERVICO%%.*}
BASE=${BASE%%@*}
case "$BASE" in
    sshd|ssh|sudo|systemd-logind|cron|crond|cronie|anacron|*[Aa][Uu][Tt][Hh]*) echo "O journal de $SERVICO (login, sessao, elevacao ou cron) nao e lido por este script" >&2; exit 2;;
esac
command -v journalctl >/dev/null 2>&1 || { echo "Esta maquina nao tem journalctl" >&2; exit 2; }
journalctl -u "$SERVICO" -n "$LINHAS" --no-pager -o short-iso
""",
    },
    {
        "system_key": "monitor_logs:windows",
        "name": "Logs",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 90,
        "description": ("Somente leitura: os últimos N eventos (1 a 500) do log System, Application ou Setup. "
                        "Security e os logs do PowerShell não são lidos."),
        "parameters": [
            {"name": "LOG_EVENTOS", "label": "Log de eventos", "default": "System", "options": WINDOWS_EVENT_LOGS},
            _LINES_PARAM,
        ],
        "content": """$ErrorActionPreference = 'Stop'
""" + _PS_CHECK_LINES + """if ($LOG_EVENTOS -cnotin @(""" + ", ".join(f"'{n}'" for n in WINDOWS_EVENT_LOGS) + """)) { throw "Log fora da lista permitida: $LOG_EVENTOS" }
try {
    $events = Get-WinEvent -LogName $LOG_EVENTOS -MaxEvents ([int]$LINHAS) -ErrorAction Stop
} catch {
    if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { "Nenhum evento em $LOG_EVENTOS"; return }
    $denied = $_.Exception -is [UnauthorizedAccessException] -or $_.Exception.InnerException -is [UnauthorizedAccessException]
    if ($denied) { throw "Esta conta nao pode ler o log $LOG_EVENTOS (o script nao tenta elevacao)" }
    throw "Nao foi possivel ler o log $($LOG_EVENTOS): $($_.Exception.Message)"
}
$events | Sort-Object TimeCreated | Format-List TimeCreated, Id, LevelDisplayName, ProviderName, Message | Out-String -Width 300
""",
    },
    {
        "system_key": "monitor_network:linux",
        "name": "Portas em escuta",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": "Somente leitura: as portas TCP/UDP em escuta nesta máquina. Não contata nenhum outro host.",
        "parameters": [],
        "content": """if command -v ss >/dev/null 2>&1; then
    ss -tulpn 2>/dev/null || ss -tuln
elif command -v netstat >/dev/null 2>&1; then
    netstat -tuln
else
    echo "Sem ss nem netstat nesta maquina" >&2; exit 2
fi
""",
    },
    {
        "system_key": "monitor_network:windows",
        "name": "Portas em escuta",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "read",
        "timeout_seconds": 60,
        "description": "Somente leitura: as portas TCP/UDP em escuta nesta máquina, com o processo. Não contata nenhum outro host.",
        "parameters": [],
        "content": """$ErrorActionPreference = 'Stop'
$names = @{}
Get-Process | ForEach-Object { $names[$_.Id] = $_.ProcessName }
'TCP em escuta:'
Get-NetTCPConnection -State Listen | Sort-Object LocalPort | ForEach-Object { "  $($_.LocalAddress):$($_.LocalPort)  $($names[[int]$_.OwningProcess])" }
'UDP:'
Get-NetUDPEndpoint | Sort-Object LocalPort | ForEach-Object { "  $($_.LocalAddress):$($_.LocalPort)  $($names[[int]$_.OwningProcess])" }
""",
    },
    # Not read-only (Marcelo, 2026-11-11): the machine opens a connection to
    # another host, so the probe needs the "change" ceiling. Same caps: one
    # hostname or IPv4, port 1-65535, timeout 1-10 s.
    {
        "system_key": "monitor_reachability:linux",
        "name": "Teste de alcance (host:porta)",
        "platform": "linux",
        "category": "monitoramento",
        "risk": "change",
        "timeout_seconds": 30,
        "description": ("Abre uma conexão TCP desta máquina para um host (nome ou IPv4) e porta, com tempo limite "
                        "de 1 a 10 segundos, e diz se respondeu. Contata outro host, por isso não é somente leitura."),
        "parameters": _REACHABILITY_PARAMS,
        "content": """case "$ALVO_HOST" in ''|-*|*..*|*[!A-Za-z0-9.-]*) echo "Informe um host valido (nome ou IPv4)" >&2; exit 2;; esac
case "$ALVO_PORTA" in ''|*[!0-9]*) echo "Informe uma porta de 1 a 65535" >&2; exit 2;; esac
[ "$ALVO_PORTA" -ge 1 ] && [ "$ALVO_PORTA" -le 65535 ] || { echo "Informe uma porta de 1 a 65535" >&2; exit 2; }
case "$TEMPO_LIMITE" in ''|*[!0-9]*) echo "TEMPO_LIMITE deve ser de 1 a 10" >&2; exit 2;; esac
[ "$TEMPO_LIMITE" -ge 1 ] && [ "$TEMPO_LIMITE" -le 10 ] || { echo "TEMPO_LIMITE deve ser de 1 a 10" >&2; exit 2; }
OK=""
if command -v nc >/dev/null 2>&1; then
    nc -z -w "$TEMPO_LIMITE" "$ALVO_HOST" "$ALVO_PORTA" >/dev/null 2>&1 && OK=1
elif command -v bash >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
    timeout "$TEMPO_LIMITE" bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$ALVO_HOST" "$ALVO_PORTA" 2>/dev/null && OK=1
else
    echo "Sem nc nem bash nesta maquina para testar a porta" >&2; exit 2
fi
if [ -n "$OK" ]; then echo "Porta $ALVO_HOST:$ALVO_PORTA: acessivel"; exit 0; fi
echo "Porta $ALVO_HOST:$ALVO_PORTA: SEM resposta em $TEMPO_LIMITE s" >&2; exit 1
""",
    },
    {
        "system_key": "monitor_reachability:windows",
        "name": "Teste de alcance (host:porta)",
        "platform": "windows",
        "category": "monitoramento",
        "risk": "change",
        "timeout_seconds": 30,
        "description": ("Abre uma conexão TCP desta máquina para um host (nome ou IPv4) e porta, com tempo limite "
                        "de 1 a 10 segundos, e diz se respondeu. Contata outro host, por isso não é somente leitura."),
        "parameters": _REACHABILITY_PARAMS,
        "content": """$ErrorActionPreference = 'Stop'
if ($ALVO_HOST -cnotmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}\\z' -or $ALVO_HOST.Contains('..')) { throw 'Informe um host valido (nome ou IPv4)' }
if ($ALVO_PORTA -cnotmatch '^[0-9]{1,5}\\z' -or [int]$ALVO_PORTA -lt 1 -or [int]$ALVO_PORTA -gt 65535) { throw 'Informe uma porta de 1 a 65535' }
if ($TEMPO_LIMITE -cnotmatch '^[0-9]{1,2}\\z' -or [int]$TEMPO_LIMITE -lt 1 -or [int]$TEMPO_LIMITE -gt 10) { throw 'TEMPO_LIMITE deve ser de 1 a 10' }
$client = [Net.Sockets.TcpClient]::new()
try { $ok = $client.ConnectAsync($ALVO_HOST, [int]$ALVO_PORTA).Wait([int]$TEMPO_LIMITE * 1000) } catch { $ok = $false } finally { $client.Dispose() }
if (-not $ok) { throw "Porta $($ALVO_HOST):$($ALVO_PORTA): SEM resposta em $TEMPO_LIMITE s" }
"Porta $($ALVO_HOST):$($ALVO_PORTA): acessivel"
""",
    },
]
SYSTEM_SCRIPTS += MONITORING_SCRIPTS

# How the library groups the scripts (2026-10-19, Marcelo: "os scripts precisam
# serem classificados. Exemplo: tailscale, rustdesk, criação de conta,
# manutenção"). Created on startup when missing; never renamed afterwards.
SYSTEM_CATEGORIES = [
    ("tailscale", "Tailscale", "Instalação e ajustes da Tailscale"),
    ("rustdesk", "RustDesk", "Instalação e senha do RustDesk"),
    ("acesso_remoto", "Acesso remoto", "Instalador Darckware Remoto (Tailscale + RustDesk)"),
    ("contas", "Contas de usuário", "Criação de contas, senhas e propriedades de usuários"),
    ("manutencao", "Manutenção", None),
    ("monitoramento", "Monitoramento", "Estado, serviços, containers, logs e rede (leitura) e teste de alcance"),
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
