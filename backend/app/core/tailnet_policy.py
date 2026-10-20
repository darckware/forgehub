"""Reads a Tailscale policy file (HuJSON) and answers one question for Remote
Access: can ForgeHub's server open SSH to each client tag?

The policy lives in Tailscale's admin console; ForgeHub keeps the versions
someone pasted (TailnetPolicyVersion) so the rule that makes maintenance work
is recorded next to the screen that depends on it. The 2026-10-16 incident
that motivated it: every station read "SSH port unreachable" while SSH worked
from the admin's notebook -- the policy let admin devices reach everything and
gave the server (tag:darckware-infra) no way in at all, and `tailscale ping`
(which ignores the policy) answered fine, hiding it.

Understands both policy styles: `grants` (src/dst/ip) and legacy `acls`
(action/src/dst with "host:ports"). Tags are "client tags" when they are not
ForgeHub's own (SERVER_TAG, ADMIN_TAGS).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SERVER_TAG = "tag:darckware-infra"
ADMIN_TAGS = frozenset({"tag:darckware-admin"})
SSH_PORT = 22


class PolicyParseError(ValueError):
    pass


def parse_hujson(text: str) -> dict:
    """HuJSON -> dict: drops // and /* */ comments (outside strings) and
    trailing commas, then parses as JSON."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end == -1 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise PolicyParseError("Unclosed /* comment")
            i = end + 2
        else:
            out.append(c)
            i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise PolicyParseError(f"Invalid policy (line {exc.lineno}, column {exc.colno}): {exc.msg}") from exc
    if not isinstance(data, dict):
        raise PolicyParseError("The policy must be a JSON object")
    return data


def _port_spec_allows(spec: str, port: int) -> bool:
    """'*', '22', '20-30', '22,80' (optionally prefixed 'tcp:')."""
    spec = spec.strip()
    if ":" in spec:
        proto, spec = spec.split(":", 1)
        if proto not in ("tcp", "*"):
            return False
    for part in spec.split(","):
        part = part.strip()
        if part == "*":
            return True
        if "-" in part:
            lo, hi = part.split("-", 1)
            if lo.isdigit() and hi.isdigit() and int(lo) <= port <= int(hi):
                return True
        elif part.isdigit() and int(part) == port:
            return True
    return False


def _src_matches(src: list, tag: str) -> bool:
    return any(s in ("*", tag) for s in src if isinstance(s, str))


@dataclass
class PolicyAnalysis:
    client_tags: list[str]
    tags_with_ssh: list[str]
    missing_ssh: list[str]
    snippet: str | None
    style: str  # "grants" | "acls" | "none"
    warnings: list[str] = field(default_factory=list)


def _grants_allow(policy: dict, tag: str) -> bool:
    for grant in policy.get("grants") or []:
        if not isinstance(grant, dict) or not _src_matches(grant.get("src") or [], SERVER_TAG):
            continue
        dst = [d for d in grant.get("dst") or [] if isinstance(d, str)]
        if not any(d in ("*", tag) for d in dst):
            continue
        ips = grant.get("ip") or []
        if any(isinstance(ip, str) and _port_spec_allows(ip, SSH_PORT) for ip in ips):
            return True
    return False


def _acls_allow(policy: dict, tag: str) -> bool:
    for acl in policy.get("acls") or []:
        if not isinstance(acl, dict) or acl.get("action") != "accept":
            continue
        if not _src_matches(acl.get("src") or [], SERVER_TAG):
            continue
        for dst in acl.get("dst") or []:
            if not isinstance(dst, str) or ":" not in dst:
                continue
            host, ports = dst.rsplit(":", 1)
            if host in ("*", tag) and _port_spec_allows(ports, SSH_PORT):
                if acl.get("proto") not in (None, "tcp", "6"):
                    continue
                return True
    return False


def analyze_policy(policy: dict) -> PolicyAnalysis:
    owners = policy.get("tagOwners") or {}
    client_tags = sorted(t for t in owners if t != SERVER_TAG and t not in ADMIN_TAGS)
    style = "grants" if policy.get("grants") else "acls" if policy.get("acls") else "none"
    with_ssh = [t for t in client_tags if _grants_allow(policy, t) or _acls_allow(policy, t)]
    missing = [t for t in client_tags if t not in with_ssh]
    warnings: list[str] = []
    if SERVER_TAG not in owners:
        warnings.append(f"{SERVER_TAG} is not declared in tagOwners")

    snippet = None
    if missing:
        dst = ", ".join(f'"{t}"' for t in missing)
        if style == "acls":
            dst = ", ".join(f'"{t}:{SSH_PORT}"' for t in missing)
            snippet = (
                "// ForgeHub (servidor) faz a manutenção das estações e servidores dos clientes via SSH\n"
                "{\n"
                '    "action": "accept",\n'
                f'    "src":    ["{SERVER_TAG}"],\n'
                f'    "dst":    [{dst}],\n'
                "},"
            )
        else:
            snippet = (
                "// ForgeHub (servidor) faz a manutenção das estações e servidores dos clientes via SSH\n"
                "{\n"
                f'    "src": ["{SERVER_TAG}"],\n'
                f'    "dst": [{dst}],\n'
                f'    "ip":  ["tcp:{SSH_PORT}"],\n'
                "},"
            )
    return PolicyAnalysis(
        client_tags=client_tags,
        tags_with_ssh=with_ssh,
        missing_ssh=missing,
        snippet=snippet,
        style=style,
        warnings=warnings,
    )
