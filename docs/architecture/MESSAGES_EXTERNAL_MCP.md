# ForgeHub Messages MCP in external CLI runs

The host bridge starts Claude Code, Codex and agy as its service account. Those
processes do not automatically use an agent's separate MCP configuration.

For Claude Code and Codex, each run receives a session-scoped `forgehub` MCP
definition. The backend passes the registered agent `profile_slug`; the bridge
passes that slug and the protected ForgeHub environment-file path to the MCP
process. The bridge never copies the shared token into CLI arguments or writes
it to global CLI configuration. Agy keeps its existing runtime MCP config.

Every dispatch path must pass the executor's `profile_slug`. Hermes runs use
their own profile configuration and do not use this adapter.
