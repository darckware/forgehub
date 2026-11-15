# MCP do ForgeHub — Fase 2: autorização no servidor

Status: **decisões A, B e C tomadas** (2026-11-15). Implementação não iniciada. Faz parte do [plano de divisão do MCP](MCP_SPLIT_PLAN.md)
(lacunas L1, L9, L13). Decisões que valem aqui: D2 e D4 do plano.

## 1. Como é hoje (verificado no código)

- **48 das 59 ferramentas** do arquivo `host-bridge/forgehub_messages_mcp.py` chamam o backend só com o token
  compartilhado da ponte (`X-Bridge-Token`). Isso cobre todo o núcleo (Messages, perguntas, incubação), o servidor de operação e
  o registro. O `RequireAuthMiddleware` (`backend/app/main.py`) deixa esse token passar, sem identificar
  ninguém, em `/demands/*`, `/operations/agent-questions*`, `/channels/*`, `/agents` (credenciais e skills), `/tools*`,
  `/system-stats`, `/system-control/*`, `/deploy/*`, `/backups*`, `/audit/*`, `/servers` e `/database/query`.
- Consequência: **qualquer processo com esse token emite credencial, reinicia contêiner, consulta qualquer banco e
  manda mensagem em nome de qualquer agente** (o remetente vem do corpo da requisição).
- O MCP lê o token de `FORGEHUB_ENV_FILE=/root/project/forgehub/.env`, **o arquivo de segredos da produção**
  (senha do banco, segredo do JWT, …). Todo perfil Hermes recebe esse caminho (lacuna nova, L14).
- Só o acesso remoto e `get_task_context` já usam a credencial do próprio agente (`agt_`), com autorização na rota.
  O padrão existe: `is_agent_command_path` admite `agt_` numa lista de rotas e cada rota decide.
- Cada agente já tem a sua `agt_` no ForgeVault (`profiles/<p>/forgehub-vault.json` → `secret_id`). O
  `forgehub_vault_token.py` a lê e entrega ao MCP como `FORGEHUB_AGENT_TOKEN`, sem gravar em disco.
- As 14 credenciais fixas emitidas em outubro **não têm validade** (`expires_at` nulo).
- `issue_agent_credential` **devolve o token em texto** ao agente que pediu (fica na conversa e pode ir à memória).
- Outros usuários do token da ponte, que continuam: o host-bridge, e três crons do Athos (`backup_offsite_projects`,
  `ecosystem_weekly_audit`, `report_client_monthly`) em rotas `/internal`/`run-internal` próprias.

## 2. Alvo

1. **Toda ferramenta chama o backend como o agente** (`Authorization: Bearer agt_…`). O backend sabe quem é.
2. **O remetente é quem autenticou**: uma mensagem nunca sai em nome de outro agente.
3. **Ações sensíveis exigem delegação** (`AuthorityDelegation`, a mesma do acesso remoto), concedida por um admin.
   **D2 ajustada ao uso real (Marcelo, 2026-11-15: "ajustar por demandas", "manter os direitos já adquiridos").** A
   tabela abaixo é a D2 original somada ao que cada agente de fato usou nos 30 dias anteriores (eventos de atividade).
   Concedido em 2026-11-15, validade de 1 ano. Uma permissão nova se pede pelo Athos, com aprovação do Marcelo:

| Ação (delegação) | Ferramentas | Quem recebe (D2) |
|---|---|---|
| `ops.read` | `get_system_status`, `list_system_backups`, `list_audit_checks`, `list_deploy_containers`, `get_container_logs`, `list_managed_servers`, `list_routines`, `list_routine_runs` | **Athos, Aegis, Hephaestus, Scriba, Mnemosyne, Daedalus** |
| `ops.audit.run` | `run_audit_checks` | Athos, Aegis, **Hephaestus, Scriba** |
| `ops.backup.run` | `run_system_backup` | Athos, Hephaestus |
| `ops.deploy.restart` | `restart_deploy_container` | **Athos, Hephaestus** |
| `ops.database.query` | `execute_database_query` | **Athos, Aegis, Hephaestus, Mnemosyne** |
| `operations.routines.manage` (já existe) | `create/update/delete_routine`, `run_routine_now` | como hoje |
| `registry.read` | `list_skills`, `list_agent_tools`, `get_agent_profile_file`, `list_agent_credentials` (só metadados) | Athos, Aegis, Themis, **Hephaestus** |
| `registry.manage` | skills, perfis, ferramentas de agente, `sync_hermes_agents` | Athos |
| `registry.credential.request` | `issue_agent_credential` → **pede**, não emite | **Athos** |

4. **Emissão nova de credencial (D2)**: `issue_agent_credential` cria um item na aba **Aprovação**
   (`requires_approval`). Só depois que Marcelo aprova, o backend emite a credencial e a grava direto no
   ForgeVault. O agente recebe o id e a confirmação, **nunca o token**. A revogação continua imediata.
5. **Renovação automática (D2)**: toda credencial fixa passa a valer 90 dias. Uma rotina diária do ForgeHub renova,
   7 dias antes de vencer, a de cada agente **cadastrado e ativo**: emite a nova, grava no mesmo segredo do ForgeVault
   (nova versão) e revoga a antiga 24 h depois. Sem aprovação; falha vira notificação e alerta do Auditor.
6. **O token da ponte sai dos agentes**: nenhuma entrada de MCP de agente recebe `FORGEHUB_ENV_FILE`, e nenhuma lê o
   `.env` da produção. Ele fica só no host-bridge e nos crons de sistema, em rotas próprias.

## 3. Ordem de execução (incrementos pequenos, cada um publicado e verificado)

**2a. Identidade, sem mudar permissões.**
- O MCP manda `agt_` em toda chamada.
- O backend aceita `agt_` nas rotas acima e, quando presente, usa o agente autenticado como remetente ou dono.
  Se o corpo disser outro agente, a resposta é 403.
- O token da ponte continua aceito em paralelo. Nenhuma ferramenta perde acesso, e passa a dar para ver, nos logs,
  quem chama o quê.

**2b. Delegações.**
- Criar as ações da tabela e concedê-las conforme D2.
- As rotas sensíveis passam a exigir a delegação quando chamadas com `agt_`.
- Conceder **antes** de exigir, para ninguém perder acesso no meio.

**2c. Credenciais.**
- Emissão vira pedido com aprovação.
- Validade de 90 dias e rotina de renovação.
- Gravação no ForgeVault (decisão A abaixo).
- Fim do token em texto.

**2d. Corte do token da ponte.**
- O middleware deixa de aceitar o token da ponte nas rotas de agente; continua só nas rotas internas.
- Sai o `FORGEHUB_ENV_FILE` das entradas de MCP dos agentes.
- Checagem nova do Auditor: nenhum agente tem o token da ponte ou o `.env` da produção no ambiente.

**2e. Documentação.**
- `docs/business_rules/09-mcp.md` (regras MCP-001…).
- Foundation, nas mesmas regras de segredo.

Cada incremento tem testes de rota (`agt_` certo, `agt_` de outro agente, sem delegação, delegação vencida, ponte),
revisão independente e publicação pelo processo de sempre. O 2d só entra depois que os logs do 2a mostrarem que
nenhuma chamada de agente ainda usa a ponte.

## 4. Decisões abertas

- **A. Decidido (2026-11-15, Marcelo): renovação automática para os agentes cadastrados no ForgeHub.** Uma
  identidade de serviço própria (`service:forgehub-credentials`), usada só pelo host-bridge, com permissão apenas de
  `admin.secret.rotate` nos segredos `FORGEHUB_AGENT_TOKEN` desses agentes; sem passo manual. Agente não cadastrado,
  inativo ou retirado não é renovado.
- **B. Decidido (2026-11-15, Marcelo): olhar também exige permissão.** `ops.read` é uma delegação como as
  outras; quem não a tem não vê status, logs, checagens nem backups, mesmo com o servidor `forgehub_ops` configurado.
  Recebem `ops.read`: Athos, Aegis e Hephaestus.
- **C. Decidido junto com A:** as 14 credenciais sem validade recebem 90 dias a partir da publicação do 2c e
  entram na renovação automática.

## 5. Volta atrás

- **2a e 2b:** reverter o commit e publicar o MCP anterior (`deploy/publish_mcp.py <commit>`). O token da ponte continua
  aceito até o 2d.
- **2c:** as credenciais antigas só são revogadas 24 h depois da nova estar no ForgeVault.
- **2d:** reverter o middleware recoloca o token da ponte.
