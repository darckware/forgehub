# Agent remote access governance — execution ledger

Binding specification: Marcelo's 2026-11-06 request, supplied to Aramis.
Executor: Aramis. Independent reviewer: Dartan, through Messages.

1. Test and implement machine/group-scoped delegation, including task context.
2. Test and implement immutable proposals, human JWT decisions, atomic single-use claim,
   expiry, secret/elevation validation, audit and runner completion tracking.
3. Deliver short-lived individual agent credentials to dispatched runtimes through a
   protected temporary file. Only its path goes in MCP configuration; never token values.
4. Add the approval UI and machine/group/24-hour delegation controls using existing UI.
5. Run isolated domain and guard tests, lint, TypeScript, Vitest, build and responsive checks.
6. Update architecture/CLAUDE, commit, request Dartan review with fixed_agent and commit;
   address findings and repeat. No deployment or production operations.

Decisions: credential issuance occurs in the authenticated backend dispatch path, bound
by agent UUID, not a slug supplied by a tool. The bridge only transports that credential.
Existing library execution remains available within machine-scoped delegation. Proposed
scripts are never added to the shared library. An uncertain execution remains claimed.
