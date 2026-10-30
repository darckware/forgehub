# Agent Identity Token — Specification (F.1 / F.1.1)

> **Status:** design only (Plano Integrado F.1, Onda 1, 2026-10-29). Author: Porthus. Reviewer: Aegis
> (spec and the F.1.1 emergency procedure). Contract consumer: Aramis (implements F.2 in ForgeVault and
> F.4 in ForgeHub). **No token is issued, rotated or revoked by this document, and no production code
> changes with it.** Language: English, per D-5 (technical spec); the plan itself stays pt-BR.
>
> Tags: **[EXISTS file:line]** = verified by reading the code on 2026-10-29 (branch `origin/develop`
> `f45c400` for ForgeHub, `main` for ForgeVault); **[PROPOSED]** = this design, not built; **[NOT
> VERIFIED]** = stated by the plan or another doc but not read in code for this spec.
>
> Context: `docs/plano-integrado/10-area-de-teste-e-identidade.md` §1–§2.1 (diagnosis and target),
> `07-fases-de-implementacao.md` rows F.1–F.9, `docs/architecture/MCP_MISSION_TOOLS_SPEC.md` §0.2
> (how agents are authorized in ForgeHub today). ForgeVault side: `forgevault`
> `docs/architecture/AGENT_IDENTITY_ISSUER.md` (branch `docs/f1-token-design`).

## 1. What exists today

### 1.1 ForgeHub

| Fact | Where |
|---|---|
| Agent credential = `agt_` + 32 random bytes (`secrets.token_urlsafe(32)`), stored only as unsalted SHA-256 hex, optional `expires_at`, `revoked_at` | [EXISTS backend/app/api/routes/agent.py:1406-1414], [EXISTS backend/app/api/routes/governed_approval.py:189-193], model [EXISTS backend/app/db/models/agent.py:229-240] |
| Two issuing routes exist for the same credential type (agent page and governed approval) | [EXISTS agent.py:1399], [EXISTS governed_approval.py:180] |
| `agt_` resolution: hash lookup, not revoked, not expired, agent `is_active` and `status=="active"` → `ActorPrincipal("agent", ...)` | [EXISTS backend/app/core/deps.py:29-48] |
| Authorization of an agent = `authorize_action` against an `AuthorityDelegation` (deny by default; `allowed_actions`, `max_risk`, `budget_limit`, `valid_from`/`expires_at`, `status`, `revoked_at`) | [EXISTS deps.py:59], [EXISTS backend/app/db/models/governance.py:221-243] |
| Middleware admits an `agt_` only on listed path prefixes, and checks **only** `revoked_at` there (not `expires_at`, not agent active); the route's own `get_actor_principal` then re-checks both (expiry [deps.py:43], agent active [deps.py:46]) | [EXISTS backend/app/main.py:201-243] |
| MCP (`forgehub` server) reads one long-lived `FORGEHUB_AGENT_TOKEN` from the agent profile env | [EXISTS backend/app/mcp/factory_server.py:54-58] |
| `AgentServiceCredential` has no `last_used_at`: there is no usage telemetry per credential | [EXISTS agent.py:229-240] |
| Human JWT: HS256 with `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES=60`, claims `sub`+`exp` only (no `aud`, `iss`, `jti`) | [EXISTS backend/app/core/security.py:29-47], [EXISTS backend/app/core/config.py:157-167] |
| Shared bridge token `X-Bridge-Token` = `CHAT_BRIDGE_TOKEN`, compared with `==`/`!=` (not constant-time) in middleware and routes | [EXISTS main.py:262,283,295,307,322,333], [EXISTS backend/app/api/routes/demand.py:505] |
| host-bridge authenticates every request with the same shared secret (`FORGEHUB_BRIDGE_TOKEN`), also `!=` | [EXISTS host-bridge/app.py:16-17,71,261] |
| ForgeRouter SSO: server-to-server shared secret `FORGEROUTER_SSO_SECRET` exchanged for a short ForgeRouter session | [EXISTS backend/app/api/routes/forgerouter.py:1-12,66-72] |
| ForgeRouter per-agent API key imported from ForgeRouter's registry and stored Fernet-encrypted on `Agent` | [EXISTS backend/app/core/forgerouter_sync.py] (CLAUDE.md), not re-read line by line |
| Darckware: two static tokens (agent / approver) from settings or a token file | [EXISTS backend/app/core/darckware_client.py:51-56], [EXISTS config.py:231-233] |
| Test environment refuses production secrets by salted-hash comparison | [EXISTS backend/app/core/test_integration_policy.py:150] |

### 1.2 ForgeVault

| Fact | Where |
|---|---|
| Human access JWT signed **HS256** with a symmetric `SigningKey`, 15 min default lifetime, claims `sub`, `email`, `jti` | [EXISTS forgevault src/ForgeVault.Infrastructure/Auth/AuthService.cs:219,251-261], [EXISTS …/Auth/JwtOptions.cs:20] |
| Validation: `ValidIssuer`, `ValidAudience` = ForgeVault itself, symmetric key | [EXISTS forgevault src/ForgeVault.Api/Program.cs:119-123] |
| Service-account token `fv_sa_` + 32 random bytes, stored as SHA-256 base64, `IssuedAt`/`ExpiresAt`/`RevokedAt`/`LastUsedAt` | [EXISTS …/Auth/ServiceAccountTokenFactory.cs:10-24], [EXISTS src/ForgeVault.Domain/Entities/ServiceAccountToken.cs:7-19] |
| `fv_sa_` routed to its own auth scheme by prefix; refused when revoked, expired or the account `!IsActive`; updates `LastUsedAt` | [EXISTS Program.cs:86-89], [EXISTS src/ForgeVault.Api/Authentication/ServiceAccountAuthenticationHandler.cs:48-58], [EXISTS …/Entities/ServiceAccount.cs:14] |
| Envelope encryption under a master key from a local file provider | [EXISTS src/ForgeVault.Infrastructure/Security/AesGcmEnvelopeEncryptionService.cs], [EXISTS …/Security/LocalFileKeyProvider.cs:17] |
| Audit log entity with actor, action, resource, IP, request/correlation id, JSON metadata | [EXISTS src/ForgeVault.Domain/Entities/AuditLog.cs:13-41] |
| Environments exist in the project hierarchy | [EXISTS src/ForgeVault.Domain/Entities/Environment.cs:13] |
| No JWKS, no asymmetric key, no token exchange anywhere in ForgeVault code or docs | grep for `JWKS|RS256|ES256|token-exchange` in `src/` and `docs/`: no hit |

### 1.3 Findings that matter for the transition (not fixed here)

- **FND-1** Middleware admits an expired `agt_` (only `revoked_at` checked, [main.py:241]). Safe only where
  the admitted route resolves `get_actor_principal` again ([deps.py:43-47]); not audited route by route here. Any admitted route that
  does not would accept an expired credential. F.4 must not copy this split.
- **FND-2** Bridge-token comparisons are not constant-time ([main.py:262…], [host-bridge/app.py:261]).
  Low practical risk on a LAN, but the new validator must use constant-time compares and the fix is cheap.
- **FND-3** No usage telemetry for `agt_` ([agent.py:229-240]): we cannot prove an agent stopped using
  its `agt_` before disabling it. The transition (§9) needs it first.
- **FND-4** ForgeHub signs with `python-jose` ([backend/requirements.txt:8]). For the new tokens the
  validator must pin the algorithm list to exactly `["ES256"]` and never accept `none`/HS*; consider PyJWT
  for the new path (decision for F.4).

## 2. Algorithm: ES256 [PROPOSED]

**Decision: ES256 (ECDSA P-256 + SHA-256), RFC 7518 §3.4.** RS256 is the accepted fallback only if a
consumer library turns out unable to do ES256 (none found).

| Criterion | ES256 | RS256 |
|---|---|---|
| Support in our stacks | .NET `ECDsa` (ForgeVault, native); Python `cryptography` via python-jose/PyJWT (ForgeHub, Darckware, ForgeRouter, host-bridge) | same |
| Token size | 64-byte signature | 256-byte (2048-bit) / 384-byte (3072-bit) |
| Key generation / rotation cost | trivial, fast | slower, larger keys |
| Security level | ~128-bit | 2048-bit ≈ 112-bit; 3072-bit for 128-bit |
| Main pitfall | nonce reuse leaks the key → only use the platform's ECDsa (OS/OpenSSL, deterministic or CSPRNG nonces), never a hand-rolled one | padding/oracle issues are solved in mature libs |

Reasons: shorter tokens (they ride on every MCP call), cheap overlapping rotation (§3), and equal or better
security than RSA-2048. The algorithm is fixed per `kid`; validators **pin** `alg=ES256` and refuse any
other value, including `none` and `HS256` (key-confusion defence).

## 3. Issuer, keys, `kid`, JWKS and rotation [PROPOSED]

**Issuer: ForgeVault** (`iss = "https://forgevault.<internal>/identity"`, exact value fixed in F.2).
Why ForgeVault and not ForgeHub:
- it already holds the agents' long credential (`fv_sa_` service accounts, §1.2) and decides
  "identity active" ([ServiceAccountAuthenticationHandler.cs:53]); the plan makes it the single revocation
  point and the global stop (10 §2.1, F.8);
- it already has envelope encryption and an audit trail ([AuditLog.cs:13]) for every issuance;
- ForgeHub is itself a consumer (aud) and runs agent-written code daily; the signer must not live in the
  process agents change most.

Keys:
- Private keys are generated inside ForgeVault, stored only envelope-encrypted under the master key, never
  exported, never shown in UI/MCP/log. Decrypted in memory only to sign.
- `kid` = `fv-<env>-<yyyymmdd>-<4 hex>` (env ∈ `test`, `prod`). **Separate key sets per environment**:
  a test ForgeVault/test environment can never sign a token a production validator accepts, even if
  someone mislabels `env`.
- JWKS at `GET /.well-known/jwks.json` (public, cacheable, `Cache-Control: max-age=600`), plus
  `GET /.well-known/openid-configuration`-style metadata with `issuer`, `jwks_uri`,
  `revocation_events_uri`, `revocation_list_uri`.

Key states and overlapping rotation:

```
pending ──(published ≥ 24 h)──► active (signs) ──(next key active)──► retiring (verify only)
                                                                      │ ≥ max token lifetime + JWKS cache (≥ 30 min; we keep 24 h)
                                                                      ▼
                                                                  retired (removed from JWKS)
compromised: any state ──► removed from JWKS immediately + kid on the revoked-kid list (F.1.1)
```

- Exactly one `active` key per environment; JWKS always carries `pending` + `active` + `retiring`.
- Scheduled rotation every 90 days; manual rotation on demand. A rotation is: create `pending` →
  wait ≥ 24 h (every consumer has refreshed JWKS) → promote → old becomes `retiring` for 24 h → retire.
  No consumer restart is needed at any step.
- Rotation and every state change write a ForgeVault audit event. Scheduled rotation needs no approval
  (it removes nothing that is in use); emergency rotation follows F.1.1.

## 4. Token format and claims [PROPOSED]

Header: `{"alg":"ES256","typ":"at+jwt","kid":"fv-prod-20261101-a1b2"}` (RFC 9068 access-token type;
validators require `typ=at+jwt` so an ID token or another JWT is never accepted as an access token).

| Claim | Type | Meaning / rule |
|---|---|---|
| `iss` | string | ForgeVault issuer URL. Exact match. |
| `sub` | string | `sa:<ForgeVault ServiceAccount UUID>`. Stable, issuer-owned. Never a name. |
| `agent` | string | Agent slug (e.g. `athos`). Informational and for logs; **mapping uses `sub`**, never this. |
| `aud` | string | **Exactly one** system: `forgehub`, `forgerouter`, `forgevault`, `darckware`, `coreti`, `host-bridge` (§6). An array is refused. |
| `env` | string | `test` or `production`. Must equal the validator's own environment. |
| `roles` | string[] | ForgeVault roles of the identity in that `env` (e.g. `executor`, `orchestrator`, `deployer`). |
| `scopes` | string[] | Coarse, system-specific permissions (`<system>:<area>:<verb>`, e.g. `forgehub:factory:read`, `forgehub:missions:write`, `darckware:emails:draft`). Ceiling only (§6). |
| `mission_id` | UUID, optional | Present when the token was requested for one mission; the validator then refuses actions outside it. |
| `delegation_id` | UUID, optional | ForgeHub `AuthorityDelegation` the request relies on. ForgeHub still evaluates it live. |
| `jti` | UUID | Unique per token; key for revocation and audit correlation. |
| `iat`, `nbf`, `exp` | int | `exp - iat` ≤ **15 min**, default **10 min**. Clock skew tolerated: 60 s. |
| `ver` | int | Contract version, `1`. Unknown major → refuse. |

Rules:
- **A token never grants more than the target system would grant on its own.** Effective permission =
  token `scopes` ∩ local authorization (e.g. ForgeHub `authorize_action` [deps.py:59]). A scope missing
  from the token denies; a scope present does not allow by itself.
- No secret, prompt, e-mail, phone or free text in claims.
- Production tokens are issued only to identities with an explicit production role grant (10 §2.1:
  agents default to `test` only; e.g. Hephaestus `deployer` in production).

## 5. Issuance and renewal [PROPOSED]

- `POST /identity/token` (ForgeVault), authenticated with the agent's `fv_sa_` (the one long credential),
  body `{aud, env, scopes?, mission_id?, delegation_id?}` (OAuth 2.0 Token Exchange, RFC 8693 shape:
  `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`).
- Checks, all fail-closed: service account active; not under global stop (F.8); requested `env` granted;
  requested `aud` allowed for the identity; requested `scopes` ⊆ role scopes for that `aud`/`env`;
  rate limit (e.g. 60 issuances/agent/min).
- Every issuance and every refusal is a ForgeVault audit event: actor, `aud`, `env`, scopes, `jti`,
  outcome, source IP — never the token.
- Renewal: the client (MCP server / SDK helper) requests a new token when < 2 min remain; there is no
  refresh token. Losing ForgeVault therefore stops new work within one lifetime (§8).
- Caching on the client: in memory only, per (`aud`, `env`, `mission_id`); never written to disk or env.

## 6. Validation per system [PROPOSED]

Common validator (one small library per stack, same test vectors): parse header → `alg == ES256` and
`typ == at+jwt` → `kid` known in cached JWKS for this env and not on revoked-kid list → signature →
`iss`, `aud == self`, `env == self`, `nbf`/`exp` with 60 s skew, `ver` → `jti` not revoked and `sub` not
suspended (revocation cache, §7) → map `sub` to a local principal → local authorization ∩ `scopes`.

| System | Accepts `aud` | Maps `sub` to | Local authorization that still applies | Notes |
|---|---|---|---|---|
| ForgeHub | `forgehub` | `Agent` row via new `agents.forgevault_service_account_id` (unique) [PROPOSED F.4]; refuse if no row, `is_active` false or `status != active` (same as [deps.py:46-47]) | middleware prefix list [main.py:201-232] + `authorize_action`/`AuthorityDelegation` [deps.py:59]; `mission_id`/`delegation_id` must match the delegation used | One code path for both credentials: middleware does the **full** check (fixes FND-1) |
| ForgeRouter | `forgerouter` | ForgeRouter agent row (`ai_router.agents`, `kind='agent'`) by a stored `sub` | ForgeRouter's per-agent routing/budget | Replaces the per-agent API key for agent calls (later phase). External runtimes (claude/codex/agy) never route through ForgeRouter — unaffected. [NOT VERIFIED in ForgeRouter code] |
| ForgeVault | `forgevault` | the same service account | ForgeVault RBAC + secret grants | Lets an agent call ForgeVault's own API/MCP with the short token instead of `fv_sa_` (the `fv_sa_` then only reaches `/identity/token`) |
| Darckware | `darckware` | Darckware agent identity (Lara today) | Darckware's own rules; **approver actions never accept an agent token** (the agent/approver split stays, [darckware_client.py:51-56]) | [NOT VERIFIED in Darckware code] |
| host-bridge | `host-bridge` | — | — | **Out of this wave.** Agents do not call the bridge; ForgeHub does, with `X-Bridge-Token` [host-bridge/app.py:261]. Future: ForgeHub's own service identity token with an RFC 8693 `act` claim naming the agent. |
| CoreTI | `coreti` | CoreTI agent user | CoreTI | Listed in 10 §2.1; not designed here. [NOT VERIFIED] |

## 7. Revocation: push + polling [PROPOSED]

What can be revoked: a token (`jti`), an identity (`sub` suspended — includes global stop G.10/F.8), a
signing key (`kid`).

- **Push:** ForgeVault POSTs each revocation event, signed with the active key (a JWS with
  `typ=revocation+jwt`, `aud=<system>`), to every registered consumer endpoint, retrying with backoff for
  10 min. Target delivery: **≤ 10 s**.
- **Polling:** each consumer `GET /identity/revocations?since=<cursor>` every **30 s** (authenticated as
  that system's own service identity). The list holds every revocation not yet past the max token
  lifetime (jti) and every active suspension/kid revocation. Upper bound on missed push: **≤ 60 s**.
- **Hard bound:** even if both channels fail, an access token dies at `exp` (≤ 15 min). This meets F.8's
  "stop an agent cuts all systems within 15 min" with margin; normal case ≤ 60 s.
- **Staleness rule (fail-closed):** if a consumer's last successful poll is older than **120 s**, it
  refuses every token with a write scope, `env=production` or `mission_id`, and keeps accepting only
  read scopes until the poll recovers; at **15 min** stale it refuses all tokens. Each change of state
  is logged and raises a notification.
- Revocation itself (who may trigger it) is in F.1.1 §10.

## 8. HA, caching and issuer outage [PROPOSED]

- ForgeVault is a single instance today [NOT VERIFIED: deployment topology not read]. This design does
  not require HA for safety, only for availability.
- **JWKS cache:** fetched at start-up and every 10 min; an unknown `kid` triggers one refetch, at most
  once per 30 s (stops a flood of forged `kid`s from hammering ForgeVault). Cached public keys stay
  usable up to 24 h without refresh (they are not secret); revoked-kid list always wins.
- **Issuer down:** no new tokens. Existing tokens keep working until `exp`, subject to the staleness rule
  (§7). So agents stop within ≤ 15 min — **fail-closed for agents by design**. Humans are unaffected
  (they log in to each system directly). Recovery = ForgeVault back up; nothing to re-sync.
- **Consumer start-up without JWKS:** refuses all ForgeVault tokens (no "accept until first fetch").
- During the transition (§9) an agent whose token path fails may still use its `agt_` in ForgeHub; that is
  the pre-existing trust, not a new hole. After cut-over there is no agent fallback.
- Later, if availability matters more: a second ForgeVault replica sharing the database and master key,
  or pre-issued tokens — decision for Marcelo (§12 Q4).

## 9. Transition from `agt_` without an unsafe window [PROPOSED]

| Step | What | Gate to the next step |
|---|---|---|
| T0 (now) | Only `agt_`. | Add `last_used_at` (+ source) to `AgentServiceCredential` and fix FND-1/FND-2 (small, separate task). |
| T1 (F.2/F.3) | ForgeVault issues tokens in **test** only; one service account per agent (13). | Test suite: inactive identity gets no token; `env=test` token refused by a production validator; forged/HS256/`none`/wrong-`aud` refused. |
| T2 (F.4) | ForgeHub accepts both, per agent: new column `agents.accepted_credentials ∈ {agt, both, forgevault}` [PROPOSED], default `agt`. MCP prefers the short token when configured. | For each agent: ≥ 7 days on `both` with zero failed validations. |
| T3 | Per agent, set `forgevault` (agt_ refused **but not revoked**, so rollback is a flag flip). | ≥ 7 days with `last_used_at` of the `agt_` unchanged and no rollback. |
| T4 | Revoke that agent's `agt_` (`revoked_at`), remove `FORGEHUB_AGENT_TOKEN` from its profile env. When all agents are at T4, the `agt_` branch is deleted from code. | Marcelo approves T4 per agent batch. |

No unsafe window because: (a) at no step does an agent hold a credential it did not already hold, except
the new short token, which is narrower; (b) the `agt_` is refused before it is revoked, so a hidden
consumer shows up as a failure, not as a silent loss; (c) the per-agent flag is changed only by an admin
and audited; (d) production tokens are not issued until T2 is done for that agent in test.

## 10. F.1.1 — Emergency procedure

Roles: **Detector** = anyone (agent, alert, Marcelo). **Incident lead** = Aegis. **Approver** = Marcelo.
Principle: actions that only **reduce** access may be taken immediately by the incident lead and are
reported to Marcelo at once; actions that **restore or create** access require Marcelo's explicit approval.
Every step is recorded as a ForgeVault audit event and a ForgeHub `AuditEvent`, with timestamps. No
secret value is ever pasted into Messages, Telegram, a ticket or a log.

### 10.1 A single access token leaked (a `jti`)
1. Lead revokes the `jti` (ForgeVault) — immediate, no approval. Push + poll propagate (≤ 60 s).
2. Lead suspends the `sub` if the leak path is unknown or the token holder's host may be compromised.
3. Lead checks audit: what the `jti` did in each system between leak and revocation.
4. Lead reports to Marcelo: what leaked, where, exposure window, actions done.
5. Resume (unsuspend `sub`): **Marcelo approves**.

### 10.2 An agent's long credential leaked (`fv_sa_`, or an `agt_` during the transition)
1. Lead revokes that credential and suspends the service account — immediate. (For `agt_`: set
   `revoked_at`.)
2. Lead revokes every live `jti` of that `sub` (ForgeVault keeps the issuance list).
3. Audit review as 10.1.3, including token issuances made with the leaked credential.
4. Report to Marcelo.
5. New credential for the agent and unsuspension: **Marcelo approves**; the new value is delivered to the
   profile by the existing ForgeVault provisioning path, never by chat.

### 10.3 A signing private key leaked or suspected (`kid`)
1. Lead marks the `kid` **compromised** — immediate: removed from JWKS, added to the revoked-kid list,
   pushed to all consumers (≤ 10 s; polling ≤ 60 s). Every token signed by it dies at once.
   Effect: every agent stops until 3 is done. This is accepted.
2. Lead reports to Marcelo with the suspected path (DB dump, master-key file, process memory, backup).
3. **Marcelo approves** activating a replacement key **without** the 24 h `pending` wait (emergency
   promotion). Consumers pick it up by the unknown-`kid` refetch.
4. If the master key may be exposed, go to 10.4.
5. Post-incident: find and close the path; rotate the master key if it was readable.

### 10.4 Issuer compromised (ForgeVault host, DB or master key)
1. Lead flips each consumer's local kill switch `FORGEVAULT_TOKENS_ENABLED=false` [PROPOSED] — immediate:
   all ForgeVault tokens refused everywhere. During the transition, agents at T2 fall back to `agt_`;
   agents at T3/T4 stop. Humans continue with their own logins.
2. Lead stops ForgeVault's token endpoint (or the service) — immediate.
3. Report to Marcelo. **Marcelo decides** scope: which secrets in ForgeVault are presumed exposed (the
   issuer also holds secrets; this is the larger incident) and their rotation order.
4. Rebuild from a known-good state: new master key, new signing keys (new `kid`s), every `fv_sa_`
   re-issued — **Marcelo approves** each restoration step and the re-enabling of the kill switch.
5. Consumers re-enable only after their JWKS shows only the new `kid`s.

### 10.5 Drill
Before production issuance (end of F.4), run 10.1–10.4 in the test environment (T.x) with test keys only,
measuring propagation times against §7. Aegis signs the drill report.

## 11. Out of this wave

Issuing, rotating or revoking any real token or key; F.2–F.9 implementation; human SSO through
ForgeVault; host-bridge on tokens (§6); CoreTI and Darckware validator code; sender-constrained tokens
(DPoP/mTLS) and workload identity to replace the `fv_sa_` stored in profile env; HSM/KMS for the signing
key; a ForgeVault replica; the Windows target.

## 12. Risks and open questions for Marcelo

Risks:
- **R1** The `fv_sa_` stays a long credential in each profile's env; whoever reads that env can mint
  tokens until it is revoked. Mitigation now: narrow role scopes, issuance audit/alerts (F.9); later:
  sender-constrained tokens.
- **R2** Single ForgeVault = single point of failure for agents (fail-closed ≤ 15 min).
- **R3** Signing key protected by a master key on a local file ([LocalFileKeyProvider.cs:17]); a host
  compromise exposes both.
- **R4** Two validators (Python, .NET) must behave identically; mitigation: shared test vectors (valid,
  expired, wrong `aud`/`env`/`typ`, `alg` none/HS256, unknown/revoked `kid`).
- **R5** ForgeHub's `python-jose` (FND-4).

Questions:
- **Q1** ES256 approved (RS256 only as fallback)?
- **Q2** Default lifetime 10 min, max 15 min?
- **Q3** Staleness rule (120 s → read-only, 15 min → refuse all) acceptable?
- **Q4** Accept agents stopping when ForgeVault is down, or plan a replica now?
- **Q5** Pre-authorize Aegis to take the access-reducing steps of F.1.1 without asking first (reporting
  immediately), as written in §10?
- **Q6** Retirement of `agt_` (T4): per-agent batches approved by you, or one date for all?
- **Q7** Should host-bridge move to tokens in a later wave, or stay on the shared secret with only FND-2 fixed?
