# Moodle approvals through Messages

Protected Moodle proposals use a ForgeHub Messages record and Marcelo's approval. The protected
set is course update, course deletion, group deletion, user deletion, manual unenrolment and group
member removal. The proposal creator registers it with `moodle_register_proposal`; registration
does not execute a Moodle write.

Marcelo signs in to ForgeHub, opens **Pessoal → Tarefas dos agentes**, requests the link sent to
his private Telegram by Maia, reviews the selected operations and confirms with his ForgeHub
password. The link is short-lived and consumed once for the selected batch. The Messages task
goes to the chosen executor. The executor calls `moodle_execute_approved` with the request ID,
message ID and hash from that task. A lost claim or uncertain Moodle response requires
investigation; never retry it automatically. The Messages record is authoritative because the
creator's local proposal can remain pending after another agent executes it.

The agent dropdown lists the registry. Selection does not provision Moodle access: the executor
must already have the Moodle MCP and its own credential. Maia and Athos are the configured Moodle
profiles. Other agents need explicit provisioning before they can execute these actions.

The backend defaults `MOODLE_APPROVAL_ENABLED` to false. Activation requires the owner ID, a fixed
private Telegram chat ID, an HTTPS form URL, the host working path, and a map of authorized source
agent IDs to their proposal stores inside the backend container. The map points to
`/profiles/<profile>/moodle-mcp/proposals.json`; the host gateway writes the same files under
`/root/.hermes/profiles/<profile>/moodle-mcp`. The backend sends the link through the existing
host bridge using Maia's Telegram bot. It does not receive or store the bot token. Sign in before
opening the Telegram link: the current login redirect does not retain the link fragment.

The individual ForgeHub credentials for Maia and Athos are stored in the ForgeVault ForgeHub
production environment, with an explicit grant to each agent's own Vault identity. Their MCP
processes fetch the credential in memory through `scripts/forgehub_vault_token.py`; the installed
host copy is `/root/.hermes/scripts/forgehub_vault_token.py`. Maia's contact and agenda consumers
also fetch through that helper. The old shared-environment Vault copies and old ForgeHub
credentials were revoked after the new credentials and gateway were verified. Other Hermes
agents still require a separate migration: their current ForgeHub credentials remain in local
configuration and their old Vault environment has broader service-account access.

Do not enable protected writes until the backend migration, source mapping, agent credentials,
gateway reload and synthetic end-to-end checks have succeeded. Disable the feature flag to block
new registrations, approvals and claims during rollback; retain the approval tables and audit
records. Do not restore old MCP code that accepts local approval for destructive operations.
