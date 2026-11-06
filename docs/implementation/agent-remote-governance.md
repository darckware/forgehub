# Agent remote access governance — execution ledger

Binding specification: Marcelo's 2026-11-06 request, supplied to Aramis.
Executor: Aramis, completed by Porthus on 2026-11-06 (Aramis out of quota; Marcelo's
decision). Porthus is a co-author and cannot review. Independent reviewer: Dartan, through Messages.

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

Continuation (#42184): agy rejects `mcpServers` in `--settings`, so it gets a separate
`forgehub_dispatched` entry in `mcp_config.json`; the existing `forgehub` entry and its
credential are preserved byte for byte. Maintenance identity comes only from the run
file in both MCP servers. Delegation scope follows the task's project.

Pending: a real agy run proving the environment reaches its MCP child (criterion 1 for
agy), asked of Dartan with the review. Evidence kept: the 390/1440 px captures and
`visual-check.py`. `premium-audit.json` stays out: it is a whole-frontend audit (51
findings, none about this delivery's screens), not proof of anything here.
