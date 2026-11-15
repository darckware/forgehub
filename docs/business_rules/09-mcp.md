# 09 — MCP do ForgeHub

Base: `main` em `11c529eb` (15/11/2026), publicado em produção como `fh-11c529e`. Este guia reúne as
regras de negócio do MCP do ForgeHub, o conjunto de ferramentas pelo qual os agentes (Hermes,
Claude Code, Codex e agy) falam com o ForgeHub. Planejamento e decisões:
[MCP_SPLIT_PLAN.md](../architecture/MCP_SPLIT_PLAN.md) e
[MCP_FASE2_AUTHORIZATION_SPEC.md](../architecture/MCP_FASE2_AUTHORIZATION_SPEC.md).

Os estados seguem o [catálogo](README.md#como-interpretar): IMPLEMENTADA, PARCIAL, POLÍTICA, GAP e
HISTÓRICA. A palavra **servidor** aqui é um programa MCP que roda na própria VPS e entrega um grupo de
ferramentas; não é uma máquina.

## 1. Servidores e ferramentas

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MCP-001 | IMPLEMENTADA | O MCP do ForgeHub é dividido em **7 servidores por área** (decisão D1, 15/11/2026): `forgehub` (Messages, incubação, perguntas e aprovação do Marcelo), `forgehub_factory` (produtos, projetos, planejamento, tarefas), `forgehub_missions` (missões, fases, critérios), `forgehub_ops` (sistema, Auditor, deploy, banco, rotinas 24x7), `forgehub_registry` (perfis, skills, credenciais), `forgehub_remote` (acesso remoto) e `forgehub_personal` (módulos pessoais, só a Maia). | `backend/app/mcp/server_map.py`; `backend/app/mcp/serve.py` |
| MCP-002 | IMPLEMENTADA | Cada ferramenta é **definida uma única vez** e pertence a **exatamente um** servidor. O mapa não cita ferramenta inexistente. Um servidor é montado a partir do catálogo combinado, com os mesmos objetos de ferramenta: nada é copiado. | `backend/app/mcp/server_map.py` (`SERVER_TOOLS`, `server_of`); `backend/tests_unit/test_mcp_server_map.py` |
| MCP-003 | IMPLEMENTADA | `forgehub_all` é o servidor de **transição** com o catálogo inteiro, igual ao `factory_server.py`. Fica até a última onda de migração dos agentes + 7 dias, e só é removido quando o Auditor não registrar mais chamadas pelos nomes antigos (decisão D3). | `backend/app/mcp/serve.py`; plano, Fase 5 |
| MCP-004 | IMPLEMENTADA | As 10 ferramentas de acesso remoto vivem no módulo de Messages (`host-bridge/forgehub_messages_mcp.py`). O FastMCP mantém a **primeira** ferramenta registrada com um nome, e esse módulo é carregado primeiro; as cópias que existiam no `factory_server.py` nunca rodavam e foram removidas. | `backend/app/mcp/factory_server.py` (aliases); `backend/tests_unit/test_mcp_server_map.py` (`test_remote_access_is_defined_once`) |
| MCP-005 | PARCIAL | **Quem recebe o quê** (decisão D4): a lista oficial fica no ForgeHub e cobre todos os agentes cadastrados. Todo agente recebe sempre `forgehub`; quem trabalha com projetos também recebe `forgehub_factory`. O resto é liberado **por tarefa**, e os servidores sensíveis (`ops`, `registry`, `remote`) só com delegação. Hoje os agentes ainda usam `forgehub_all`: a troca é a Fase 3 (migração por ondas). | Plano, seção 3 e D4 |

## 2. Código publicado e chaves da produção

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MCP-010 | IMPLEMENTADA | Todo agente roda o MCP de **`/root/.forgehub/mcp/current`**, uma cópia imutável de **um commit** (`backend/app/mcp` + `host-bridge/forgehub_messages_mcp.py`). Nunca roda do checkout principal, que muda quando uma sessão troca de branch, nem de uma cópia antiga fixa. Isso vale para os perfis Hermes, a Maia (`profiles/maia/mcp/forgehub.py`), o Codex, o agy e as execuções despachadas. | `deploy/publish_mcp.py`; `host-bridge/app.py` (`MESSAGES_MCP_SCRIPT`) |
| MCP-011 | IMPLEMENTADA | Mudança no código do MCP só chega aos agentes depois de `python3 deploy/publish_mcp.py <commit>`. O script compila todos os módulos antes, troca o atalho de uma vez e guarda a cópia anterior, então voltar atrás é publicar o commit anterior. Processos já abertos continuam com o código que carregaram. | `deploy/publish_mcp.py`; `deploy/tests/test_publish_mcp.py` |
| MCP-012 | IMPLEMENTADA | As **chaves da produção** do backend ficam em `deploy/production-flags.env` (versionado, sem segredos). O `docker-compose.yml` carrega o arquivo depois do `.env`, então qualquer `docker compose up`, de qualquer sessão, sobe com as mesmas chaves. Mudar um valor exige aprovação do Marcelo e um commit. (Em 15/11/2026, duas publicações de outra sessão desligaram a análise sob demanda do Messages porque essa lista não existia.) | `deploy/production-flags.env`; `docker-compose.yml` |
| MCP-013 | IMPLEMENTADA | Checagem diária **ECO-072** (dono: Athos): as chaves do contêiner em execução conferem com o arquivo do `origin/main`, e toda entrada de MCP do ForgeHub em todos os agentes usa o código publicado. | `ops/athos/checklist_verifier.py` (`check_versioned_runtime_sources`); migração `f2b4d6e8a0c1` |
| MCP-014 | POLÍTICA | No Hermes, citar **um** servidor MCP na lista de ferramentas de um canal (`platform_toolsets`) transforma a lista em exclusiva: os outros servidores somem da sessão sem aviso. Ao configurar um canal, cite todos os servidores que o agente deve ver, ou nenhum. (Aconteceu com o Athos até 15/11/2026: as rotinas rodavam sem o ForgeHub.) | Hermes `hermes_cli/tools_config.py` (`_merge_mcp_servers`) |

## 3. Identidade e autorização

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MCP-020 | IMPLEMENTADA | Toda chamada do MCP leva a **credencial do próprio agente** (`Authorization: Bearer agt_…`). Ela vem do arquivo da execução despachada ou, sem ele, do `FORGEHUB_AGENT_TOKEN` do perfil (lido do ForgeVault, nunca gravado em disco). A credencial nunca vai para o log. | `host-bridge/forgehub_messages_mcp.py` (`_identity_headers`); `host-bridge/tests/test_messages_mcp_identity.py` |
| MCP-021 | IMPLEMENTADA | **Um agente só age como ele mesmo.** Nas rotas de Messages (enviar, caixa, listar, receber ou descartar incubação, editar, arquivar), de perguntas ao Marcelo e de proposta de tarefa em canal: credencial de outro agente → 403 `AGENT_IMPERSONATION`; credencial vencida, revogada, desconhecida ou de agente inativo → 401 `AGENT_CREDENTIAL_INVALID`. A comparação é pelo `profile_slug` exato, e em `/demands/submit` também pelo `from_agent_id`. | `backend/app/core/bridge_caller.py` (`assert_acts_as`); `backend/app/tests/test_bridge_caller_identity.py` |
| MCP-022 | PARCIAL | O token compartilhado da ponte (`X-Bridge-Token`) **ainda é aceito sozinho**, sem identificar o agente, nas rotas de agente (Fase 2a não muda permissões). Cada chamada assim fica registrada no log do backend, uma vez por hora por rota: é essa lista que libera o corte (Fase 2d). Até lá, quem tem esse token consegue emitir credencial para qualquer agente. | `backend/app/core/bridge_caller.py` (`log_bridge_only_call`); `backend/app/main.py` |
| MCP-023 | GAP | **Ações sensíveis exigem delegação** (Fase 2b, decisões D2 e B): `ops.read` (ver status, logs, checagens, backups): Athos, Aegis, Hephaestus. `ops.database.query`: Athos, Aegis, Hephaestus. `ops.deploy.restart`: Athos, Hephaestus. `ops.backup.run`: Athos, Hephaestus. `ops.audit.run`: Athos, Aegis. `registry.read`: Athos, Aegis, Themis. `registry.manage`: Athos. `registry.credential.request`: Athos. Cada delegação é concedida antes de passar a ser exigida. | Especificação da Fase 2, seção 2 |
| MCP-024 | GAP | **Emissão nova de credencial** (agente novo, sem credencial ou vazamento): só o Athos pede, e Marcelo aprova na aba Aprovação. Aprovada, o ForgeHub emite e grava direto no ForgeVault; o agente recebe só o identificador, nunca o token. Hoje `issue_agent_credential` ainda devolve o token em texto. | Especificação da Fase 2 (2c); decisão D2 |
| MCP-025 | GAP | **Renovação automática** (decisões A e C): toda credencial fixa vale 90 dias. Uma rotina diária renova, 7 dias antes de vencer, a de cada agente **cadastrado e ativo** no ForgeHub, grava a nova no ForgeVault pela identidade de serviço `service:forgehub-credentials` (só pode renovar esses segredos) e revoga a antiga 24 h depois. Sem aprovação; falha vira notificação e alerta do Auditor. As 14 credenciais de hoje, sem validade, recebem 90 dias na publicação. | Especificação da Fase 2 (2c) |
| MCP-026 | GAP | O MCP dos agentes ainda lê o token da ponte do `.env` da produção (`FORGEHUB_ENV_FILE`), que também guarda a senha do banco e o segredo de login. Na Fase 2d essa entrada sai de todos os agentes; o token fica só no host-bridge e nos crons de sistema. | `host-bridge/forgehub_messages_mcp.py` (`_bridge_token`); especificação, L14 |
