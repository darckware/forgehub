"""Pure catalog/render checks for the Windows RDP setup script."""
import pytest

from app.core.host_scripts import ScriptError, render_script, resolve_values, validate_parameters
from app.core.system_scripts import SYSTEM_SCRIPTS

MUTATION_TOKENS = (
    "New-NetFirewallRule",
    "Set-NetFirewallRule",
    "Add-LocalGroupMember",
    "Set-ItemProperty",
    "Set-Service",
    "Start-Service",
)


def _extract_braced_block(text: str, marker: str, start: int = 0) -> tuple[int, int, str]:
    """Return (start_index, end_index, body) for the first `{ ... }` block after `marker`."""
    marker_idx = text.index(marker, start)
    open_idx = text.index("{", marker_idx)
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return marker_idx, idx + 1, text[open_idx + 1 : idx]
    raise AssertionError(f"Unclosed block for marker: {marker}")


def _assert_refusal_block(text: str, marker: str, first_mutation: int, start: int = 0) -> int:
    block_start, block_end, body = _extract_braced_block(text, marker, start)
    assert block_end <= first_mutation, f"Refusal block {marker!r} is not strictly before mutations"
    assert "throw " in body, f"Refusal block {marker!r} must abort with throw"
    for token in MUTATION_TOKENS:
        assert token not in body
    return block_start


def test_windows_rdp_setup_requires_authorization_and_explicit_support_user():
    spec = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == "rdp_setup:windows")
    assert spec["name"] == "Configurar Área de Trabalho Remota (Windows)"
    assert spec["category"] == "acesso_remoto" and spec["risk"] == "change"
    params = validate_parameters(spec["parameters"])
    by_name = {p["name"]: p for p in params}
    assert by_name["CLIENTE_AUTORIZOU"]["required"] is True
    assert by_name["CLIENTE_AUTORIZOU"]["default"] == "nao"
    assert by_name["CLIENTE_AUTORIZOU"]["options"] == ["nao", "sim"]
    assert by_name["USUARIO_SUPORTE"]["required"] is True

    # Negative parameter validation scenarios
    with pytest.raises(ScriptError):
        resolve_values(params, {"CLIENTE_AUTORIZOU": "sim"})
    with pytest.raises(ScriptError):
        resolve_values(params, {"CLIENTE_AUTORIZOU": "sim", "USUARIO_SUPORTE": ""})
    with pytest.raises(ScriptError):
        resolve_values(params, {"CLIENTE_AUTORIZOU": "talvez", "USUARIO_SUPORTE": "darckware"})
    default_values, _ = resolve_values(params, {"USUARIO_SUPORTE": "darckware"})
    assert default_values["CLIENTE_AUTORIZOU"] == "nao"
    assert render_script(spec["platform"], spec["content"], default_values).startswith(
        "$CLIENTE_AUTORIZOU = 'nao'\n$USUARIO_SUPORTE = 'darckware'\n"
    )

    values, _ = resolve_values(params, {"CLIENTE_AUTORIZOU": "sim", "USUARIO_SUPORTE": "darckware"})
    text = render_script(spec["platform"], spec["content"], values)
    first_mutation = min(text.index(token) for token in MUTATION_TOKENS)

    # Every preflight refusal block must actually throw and appear strictly before all mutations.
    admin_check = _assert_refusal_block(
        text, "if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))", first_mutation
    )
    authorization = _assert_refusal_block(text, "if ($CLIENTE_AUTORIZOU -ne 'sim')", first_mutation)
    invalid_user = _assert_refusal_block(
        text,
        "if ([string]::IsNullOrWhiteSpace($USUARIO_SUPORTE) -or $USUARIO_SUPORTE.IndexOfAny([char[]]'\\\\/:*?[]<>|\"') -ge 0)",
        first_mutation,
    )
    account_lookup = text.index("Get-LocalUser -ErrorAction Stop | Where-Object { $_.Name -ieq $USUARIO_SUPORTE }")
    missing_user = _assert_refusal_block(
        text, "if ($supportUsers.Count -ne 1 -or -not $supportUsers[0].Enabled)", first_mutation
    )
    service_preflight = _assert_refusal_block(text, "if (-not $terminalService)", first_mutation)
    registry_preflight = _assert_refusal_block(
        text, "if (-not (Test-Path -LiteralPath $terminalServerPath) -or -not (Test-Path -LiteralPath $rdpTcpPath))",
        first_mutation,
    )
    port_preflight = _assert_refusal_block(
        text, "if ([int]$initialListenerConfig.PortNumber -ne 3389)", first_mutation
    )
    policy_preflight = text.index("\nAssert-RdpFirewallPolicy\n", authorization)
    broad_owned_rule = _assert_refusal_block(
        text, "Get-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName", first_mutation
    )
    msg_binary_preflight = _assert_refusal_block(
        text, "if (-not (Test-Path -LiteralPath $msgExe))", first_mutation
    )
    session_enum = text.index("WTSEnumerateSessions")
    no_active_session = _assert_refusal_block(text, "if ($activeSessionIds.Count -eq 0)", first_mutation)
    notice = text.index("& $msgExe ([string]$sessionId) '/TIME:60' $notice")
    notice_failure = _assert_refusal_block(text, "if ($msgCode -ne 0)", first_mutation, start=notice)

    assert (
        admin_check
        < authorization
        < invalid_user
        < account_lookup
        < missing_user
        < service_preflight
        < registry_preflight
        < port_preflight
        < policy_preflight
        < broad_owned_rule
        < msg_binary_preflight
        < session_enum
        < no_active_session
        < notice
        < notice_failure
        < first_mutation
    )

    # IPv4 range parsing must support both CIDR prefixes and dotted-quad netmasks.
    _, range_end, range_body = _extract_braced_block(text, "function Get-IPv4Range")
    assert range_end < authorization
    assert "($inv -band ($inv + 1)) -ne 0" in range_body

    # Firewall policy helper must query ActiveStore once, filter in memory, and throw on every unsafe branch.
    _, policy_end, policy_body = _extract_braced_block(text, "function Assert-RdpFirewallPolicy")
    assert policy_end < authorization
    for token in MUTATION_TOKENS:
        assert token not in policy_body
    for branch_marker in (
        "if ($profiles.Count -eq 0)",
        "if ([string]$profile.Enabled -ine 'True')",
        "if ([string]$profile.DefaultInboundAction -eq 'Allow')",
        "if (-not (Test-TailnetOnly $addresses))",
        "Test-AddressOverlapsTailnet ([string]$_)",
    ):
        _assert_refusal_block(policy_body, branch_marker, len(policy_body) + 1)
    assert "Get-NetFirewallProfile -PolicyStore ActiveStore" in policy_body
    assert "Get-NetFirewallRule -PolicyStore ActiveStore -ErrorAction Stop" in policy_body
    assert "-Action Block" not in policy_body and "-Action Allow" not in policy_body
    assert "[string]$_.Direction -eq 'Inbound' -and [string]$_.Enabled -ieq 'True'" in policy_body
    assert "[string]$_.Action -eq 'Allow'" in policy_body
    assert "[string]$_.Action -eq 'Block'" in policy_body
    assert text.index("\nAssert-RdpFirewallPolicy\n", first_mutation) > first_mutation

    # Post-mutation verification, NLA-before-enable ordering, and safety invariants.
    assert text.index("Name 'UserAuthentication'") < text.index("Name 'fDenyTSConnections'")
    assert "WTS_CONNECTSTATE_CLASS.WTSActive" in text
    assert "Get-LocalUser -Name" not in text
    assert "S-1-5-32-555" in text
    assert "fDenyTSConnections" in text and "UserAuthentication" in text
    assert "PortNumber" in text and "3389" in text
    assert "100.64.0.0/10" in text
    assert "New-LocalUser" not in text and "net user" not in text.lower()
    assert "RemoteAddress" in text
    assert "OwningProcess -eq $serviceInfo.ProcessId" in text
    assert "Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName -ErrorAction SilentlyContinue" in text
    assert "[string]$finalRules[0].Enabled -ine 'True'" in text
