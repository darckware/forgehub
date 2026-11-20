# ForgeHub: execute localmente no PowerShell como administrador.
# Somente leitura. Nao instala, inicia, reinicia ou reconfigura nada.
$ErrorActionPreference = 'Stop'
function Test-Section([string]$Name, [scriptblock]$Check) {
    "`n--- $Name ---"
    try { & $Check } catch { "NAO_VERIFICADO: consulta falhou ou permissao insuficiente ($($_.Exception.Message))." }
}
'FORGEHUB_SSH_DIAGNOSTIC_V1 Windows'
Test-Section 'Ambiente' {
    "Maquina: $env:COMPUTERNAME"
    "PowerShell: $($PSVersionTable.PSVersion) | 64 bits: $([Environment]::Is64BitProcess)"
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    "Administrador: $($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
    $os = Get-CimInstance Win32_OperatingSystem
    "Windows: $($os.Caption) $($os.Version)"
}
Test-Section 'Recurso OpenSSH Server' {
    Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 |
        Select-Object Name, State | Format-Table -AutoSize | Out-String -Width 160
    'O recurso pode estar ausente quando o OpenSSH foi instalado por MSI; confira o servico.'
}
Test-Section 'Servico SSH' {
    $service = @(Get-CimInstance Win32_Service -Filter "Name='sshd'")
    if ($service.Count -eq 0) { 'AUSENTE: servico sshd. Instalar/configurar o servidor SSH pode ser necessario.' }
    else { $service | Select-Object Name, State, StartMode | Format-Table -AutoSize | Out-String -Width 160 }
}
Test-Section 'Portas em escuta' {
    $listeners = @(Get-NetTCPConnection -State Listen)
    $processes = @(Get-Process -Name sshd -ErrorAction SilentlyContinue)
    $ports = @($listeners | Where-Object { $_.LocalPort -eq 22 -or $_.OwningProcess -in $processes.Id })
    if ($ports.Count -eq 0) { 'AUSENTE: porta 22 e listeners de processos sshd.' }
    else { $ports | Select-Object LocalAddress, LocalPort | Sort-Object LocalPort, LocalAddress -Unique | Format-Table -AutoSize | Out-String -Width 160 }
}
Test-Section 'Firewall (regras conhecidas do OpenSSH)' {
    Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction | Format-Table -AutoSize | Out-String -Width 160
    $rules = @(Get-NetFirewallRule | Where-Object { $_.Name -in @('OpenSSH-Server-In-TCP', 'sshd-tailnet', 'sshd-forgehub') })
    if ($rules.Count -eq 0) { 'AUSENTE: regras padrao do OpenSSH, sshd-tailnet e sshd-forgehub.' }
    foreach ($rule in $rules) {
        $rule | Select-Object Name, Enabled, Direction, Action | Format-Table -AutoSize | Out-String -Width 160
        $rule | Get-NetFirewallPortFilter | Select-Object Protocol, LocalPort | Format-Table -AutoSize | Out-String -Width 160
        $rule | Get-NetFirewallAddressFilter | Select-Object RemoteAddress | Format-Table -AutoSize | Out-String -Width 160
    }
    'Consulta parcial: regras personalizadas, politicas de dominio e ACL da tailnet podem afetar o acesso.'
}
Test-Section 'Tailscale local' {
    $service = @(Get-CimInstance Win32_Service -Filter "Name='Tailscale'")
    if ($service.Count -eq 0) { 'AUSENTE: servico Tailscale.' }
    else { $service | Select-Object Name, State, StartMode | Format-Table -AutoSize | Out-String -Width 160 }
    Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -like '*Tailscale*' } |
        Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize | Out-String -Width 160
}
Test-Section 'Conta darckware' {
    $user = @(Get-LocalUser | Where-Object { $_.Name -eq 'darckware' })
    if ($user.Count -eq 0) { 'AUSENTE: conta local darckware.' }
    else {
        $user | Select-Object Name, Enabled, PasswordExpires, AccountExpires | Format-Table -AutoSize | Out-String -Width 160
        try {
            $adsiUser = [ADSI]"WinNT://./darckware,user"
            "Conta bloqueada (lockout): $([bool]$adsiUser.InvokeGet('IsAccountLocked'))"
        } catch { 'NAO_VERIFICADO: estado de lockout da conta.' }
        $sid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
        $adminGroup = ($sid.Translate([System.Security.Principal.NTAccount]).Value -split '\\')[-1]
        try {
            $group = [ADSI]"WinNT://./$adminGroup,group"
            $isAdmin = $false
            foreach ($m in @($group.Invoke('Members'))) {
                if ($m.GetType().InvokeMember('Name', 'GetProperty', $null, $m, $null) -ieq 'darckware') { $isAdmin = $true; break }
            }
            "Membro dos administradores locais: $isAdmin"
        } catch {
            $admins = @(Get-LocalGroupMember -SID S-1-5-32-544)
            "Membro dos administradores locais: $([bool]($admins | Where-Object { $_.SID -eq $user[0].SID }))"
        }
    }
}
Test-Section 'Arquivos de autorizacao (somente metadados)' {
    $paths = @("$env:ProgramData\ssh\administrators_authorized_keys")
    $user = @(Get-LocalUser | Where-Object { $_.Name -eq 'darckware' })
    if ($user.Count -gt 0) {
        $profile = @(Get-CimInstance Win32_UserProfile | Where-Object { $_.SID -eq $user[0].SID.Value })
        if ($profile.Count -gt 0) { $paths += Join-Path $profile[0].LocalPath '.ssh\authorized_keys' }
    }
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path)) { "AUSENTE: $path"; continue }
        $item = Get-Item -LiteralPath $path
        $bytes = if ($item.Length -ge 2) { [IO.File]::ReadAllBytes($path)[0..([Math]::Min(2, $item.Length - 1))] } else { @() }
        $bom = if ($bytes.Count -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { 'UTF-8 BOM (pode falhar em OpenSSH antigo)' }
            elseif ($bytes.Count -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))) { 'UTF-16 BOM (incompativel com OpenSSH)' }
            else { 'sem BOM' }
        "Arquivo: $path | bytes: $($item.Length) | codificacao: $bom"
        $acl = Get-Acl -LiteralPath $path
        "Proprietario: $($acl.Owner) | heranca protegida: $($acl.AreAccessRulesProtected)"
        $acl.Access | Select-Object IdentityReference, FileSystemRights, AccessControlType, IsInherited |
            Format-Table -AutoSize | Out-String -Width 160
    }
    'O conteudo das chaves nao foi exibido; a correspondencia com a chave pendente nao foi testada.'
}
Test-Section 'Configuracao SSH e shell' {
    $config = "$env:ProgramData\ssh\sshd_config"
    if (Test-Path -LiteralPath $config) {
        'Diretivas selecionadas do arquivo padrao (podem existir Include e Match):'
        foreach ($line in Get-Content -LiteralPath $config) {
            if ($line -match '^\s*(Port\s+[0-9]{1,5}|PubkeyAuthentication\s+(yes|no)|PasswordAuthentication\s+(yes|no)|StrictModes\s+(yes|no)|AllowUsers\s+.+|AllowGroups\s+.+|DenyUsers\s+.+|DenyGroups\s+.+|AuthorizedKeysFile\s+.+|Match\s+Group\s+administrators)\s*(#.*)?$') { $Matches[1] }
        }
    } else { 'AUSENTE: arquivo padrao sshd_config.' }
    $shell = $null
    if (Test-Path -LiteralPath 'HKLM:\SOFTWARE\OpenSSH') {
        $shell = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\OpenSSH'
    }
    if ($shell -and $shell.DefaultShell) { "DefaultShell configurado; executavel existe: $(Test-Path -LiteralPath $shell.DefaultShell)" }
    else { 'DefaultShell nao configurado: usa o padrao do OpenSSH.' }
}
'Nao testa autenticacao, conectividade a partir do ForgeHub ou correspondencia da chave.'
'FIM_DO_DIAGNOSTICO'
