# Divisão do MCP do ForgeHub — plano

Status: **decisões D1–D4 tomadas** (2026-11-15). Implementação não iniciada. A divisão em si foi aprovada por Marcelo
("aprovado a divisão do mcp forgehub"); este documento detalha *como*, e lista as decisões que ainda são dele.

## 1. Por que dividir

O servidor `forgehub` cresceu para **116 ferramentas em dois arquivos**:

| Arquivo | Ferramentas | Conteúdo |
|---|---|---|
| `host-bridge/forgehub_messages_mcp.py` (2.113 linhas) | 53 | Messages, incubação, perguntas, registro de agentes, sistema/Auditor/deploy/banco, acesso remoto |
| `backend/app/mcp/factory_server.py` (1.551 linhas) | 69 | Software Factory, missões, fases, rotinas 24x7, aprovação, acesso remoto (de novo) |

Problemas que isso causa hoje:

- **Tudo ou nada por agente.** O Hermes filtra ferramentas por *servidor* (`platform_toolsets`). Com um servidor só,
  um agente que precisa de Messages recebe também `restart_deploy_container`, `execute_database_query` e
  `issue_agent_credential`. Só Lara e Maia têm filtro (`tools.include`); os outros 9 perfis Hermes recebem as 116.
- **Prompt pesado.** Cada ferramenta ocupa contexto; é a raiz do prompt de ~28 mil tokens do Hephaestus.
- **Crescimento.** Toda área nova (missões, rotinas, acesso remoto) entrou no mesmo servidor; o próximo módulo
  também entraria.

## 2. Lacunas encontradas (além das que motivaram a divisão)

| # | Lacuna | Evidência | Gravidade |
|---|---|---|---|
| L1 | **Ferramentas privilegiadas usam o token compartilhado da ponte**, sem autorização por agente no servidor. Quem tem o MCP pode emitir credencial de agente, reiniciar contêiner, rodar backup e consultar banco. O único limite é o `tools.include` da configuração do cliente. | `_bridge_token()` em `forgehub_messages_mcp.py`; `issue_agent_credential` → `POST /agents/{id}/credentials` com `X-Bridge-Token` | **Alta** (segurança) |
| L2 | **As 10 ferramentas de acesso remoto estão declaradas duas vezes**, uma em cada arquivo. Não foram separadas. | `run_remote_command`, `run_maintenance_script`… nos dois | Média |
| L3 | **O MCP da Maia carrega o código de uma versão antiga fixa.** | `/root/.hermes/profiles/maia/mcp/forgehub.py` → `releases/maia-group-buttons-8ddc9b7` | Média |
| L4 | **O MCP dos outros agentes roda do checkout principal**, que muda quando uma sessão publica ou troca de branch. O código das ferramentas não tem versão. | `args: …/root/project/forgehub/backend/app/mcp/factory_server.py` | Média |
| L5 | **A armadilha da lista de ferramentas por canal.** Citar um servidor MCP em `platform_toolsets` transforma a lista em exclusiva e esconde os demais sem aviso. Aconteceu com o Athos (corrigido hoje) e nenhuma checagem detecta. | `hermes_cli/tools_config.py::_merge_mcp_servers` | Média |
| L6 | **Não há uma lista única das chaves da produção.** Uma publicação de outra sessão desligou `MESSAGE_ANALYSIS_ON_DEMAND_ENABLED` (15/11, 14:46 UTC). | override `/tmp/forgehub-combined-release.compose.yml` sem as chaves | Média |
| L7 | **Três "fontes da verdade" para MCP.** Tabela `company.mcp_catalog_servers` (com `forgehub` **e** `forgehub-factory` apontando para o mesmo arquivo, ambos `apply_to_all_agents`), o registro de MCP do ForgeVault (`admin.mcp.*`) e o arquivo de cada runtime. | consulta à tabela; skill `forgevault` | Média |
| L8 | **Documentação da Foundation desatualizada.** `30_docs/FORGEHUB_MCP_SERVER.md` descreve 21 ferramentas; existem 116. | arquivo | Baixa |
| L9 | **Segredos que o processo não usa.** A entrada `forgehub` dos perfis recebe tokens do CoreTI, Darckware, ForgeRouter e ForgeVault. | `env` das entradas `forgehub` | Média |
| L10 | **Execuções despachadas recebem só o servidor de Messages** (`forgehub_messages_mcp.py` via `--mcp-config` / `forgehub_dispatched`). Depois da divisão é preciso decidir quais servidores cada execução recebe. | `host-bridge/app.py` ~1437–1600 | Média |
| L11 | **Nomes de ferramenta mudam com o servidor** (`mcp__forgehub__x` → `mcp__forgehub_ops__x`). Há 15 citações em SOUL/AGENTS/skills, mais memórias e textos de rotinas. | `grep mcp__forgehub__` | Média |
| L12 | **Sem teste de contrato** que diga qual ferramenta pertence a qual servidor e proíba duplicadas (L2 passou despercebida). | — | Baixa |

## 3. Divisão proposta

Um só código, vários servidores pequenos. Um pacote `backend/app/mcp/` com um cliente HTTP comum
(`_client.py`: autenticação, erros, rótulo de dado não confiável) e **um arquivo de entrada por servidor**.
O código de domínio continua na API do ForgeHub; os servidores só traduzem chamadas.

| Servidor | Ferramentas (origem atual) | Qtd. aprox. |
|---|---|---|
| **`forgehub`** (núcleo) | Messages (`send/list/get/check/update/archive_agent_message`), incubação (`list_my_incubation`, `receive/drop_incubation`), `ask_marcelo`, `list_my_questions`, `record_marcelo_answer`, `request_marcelo_approval`, `propose_improvement`, `propose_skill_change`, `list_channel_members`, `propose_channel_task`, `list_agents`, `get_agent_profile`, `get_task_context`, `set_agent_unavailable` | ~20 |
| **`forgehub_factory`** | produtos, projetos, escopo, telas, ERD, planejamento, tarefas, versões (`list_projects` … `close_version_and_publish`, `report_governance_blocker`) e o fluxo de tarefa (`assign/dispatch_task`, `report_task_execution`, `request_task_review`, `return_task_for_correction`, `add_task_dependency`, `list_my_tasks`) | ~28 |
| **`forgehub_missions`** | missões, critérios, plano, fases, aceite, ciclo (`create_internal_project`, `manage_project_members`, `attach_project_document`, `submit/withdraw_project_plan`, `*_mission_*`, `*_phase*`, `sequence_planning_tasks`, `mission_decide`, `pause_mission`…) | ~24 |
| **`forgehub_ops`** | sistema, backups, Auditor, deploy/logs, servidores cadastrados, consulta ao banco, rotinas 24x7 | ~16 |
| **`forgehub_registry`** | perfil e arquivos de agente, skills, credenciais, ferramentas de agente, `sync_hermes_agents` | ~16 |
| **`forgehub_remote`** | as 10 ferramentas de manutenção e acesso remoto (uma cópia só) | 10 |
| **`forgehub_personal`** | módulos `personal_*`/agenda/contatos/grupos (hoje no wrapper da Maia) | ~45 |

Continuam como estão, e passam a ser documentados: `forgehub_macro` (macros de navegador) e `forgehub_testing`.

### Quem recebe o quê (proposta)

| Agente | forgehub | factory | missions | ops | registry | remote | personal |
|---|---|---|---|---|---|---|---|
| Athos (governo/orquestração) | ✔ | ✔ | ✔ | ✔ | ✔ | — | — |
| Aegis (segurança) | ✔ | leitura | — | ✔ | leitura | ✔ (com delegação) | — |
| Hephaestus (infra) | ✔ | — | — | ✔ | — | ✔ (com delegação) | — |
| Daedalus (engenharia) | ✔ | ✔ | ✔ | leitura | — | — | — |
| Atlas (planejamento) | ✔ | ✔ | ✔ | — | — | — | — |
| Scriba (documentação) | ✔ | leitura | leitura | — | — | — | — |
| Mnemosyne (memória) | ✔ | — | — | — | — | — | — |
| Themis (conformidade) | ✔ | leitura | — | leitura | leitura | — | — |
| Kairos (receita) | ✔ | leitura | — | — | — | — | — |
| Lara (atendimento) | ✔ (Messages) | leitura (4 ferramentas, como hoje) | — | — | — | — | — |
| Maia (pessoal) | ✔ (Messages) | leitura | — | — | — | — | ✔ |
| Porthus / Aramis / Dartan (despachados) | ✔ | ✔ | ✔ | — | — | ✔ (só na tarefa autorizada) | — |

"Leitura" = o mesmo servidor com `tools.include` só das ferramentas de consulta. Matriz final é decisão D2.

## 4. Autorização no servidor (resolve L1)

A divisão sozinha não resolve L1: um filtro na configuração do cliente não é controle de acesso.

- Todo servidor autentica **com a credencial do próprio agente** (`agt_`, por ForgeVault), nunca com o token da ponte.
- Ações privilegiadas passam a exigir uma `AuthorityDelegation` no backend, como acesso remoto e rotinas já fazem:
  `registry.manage` (credenciais, skills, perfis), `ops.deploy.restart`, `ops.backup.run`, `ops.database.query`.
- O token da ponte sai do ambiente dos agentes; continua só entre backend, host-bridge e crons de sistema.
- Cada entrada de MCP recebe **apenas** o segredo que usa (resolve L9).

## 5. Ordem de execução

Cada fase é publicada e verificada antes da próxima; nenhuma derruba um agente.

**Fase 0. Pré-requisitos — CONCLUÍDA (2026-11-15, `da37a121`, release `fh-da37a12`).** Chaves da produção em
`deploy/production-flags.env` (carregado pelo `docker-compose.yml`); MCP publicado por `deploy/publish_mcp.py` em
`/root/.forgehub/mcp/current`, usado por 10 perfis Hermes, a Maia, o Codex, o agy e as execuções despachadas;
Auditor ECO-072 (diária) passando. Itens originais:
1. L6: arquivo versionado com as chaves da produção, lido por todo processo de publicação, mais checagem que
   compara com o contêiner em execução.
2. L4/L3: os agentes passam a rodar o MCP de um caminho de release estável (`/root/.forgehub/mcp/current` →
   release publicada), atualizado pelo script de publicação; a Maia passa a usar o mesmo.
3. L11: inventário de toda citação `mcp__forgehub__*` (perfis, skills, memórias, rotinas, hooks).

**Fase 1. Código — PRONTA (2026-11-15, branch `feat/mcp-split-fase1`).** `backend/app/mcp/server_map.py` diz a
qual servidor cada ferramenta pertence; `backend/app/mcp/serve.py <servidor>` monta o servidor a partir do catálogo
combinado, com os mesmos objetos de ferramenta (nada é copiado). Contagem: forgehub 22, factory 30 (28 + 2 do
navegador, opcionais), missions 23 (22 + 1 opcional), ops 16, registry 14, remote 10, personal 41 (Maia); `forgehub_all`
= o catálogo inteiro, igual ao `factory_server.py`. As 10 cópias mortas do acesso remoto saíram do `factory_server.py`
(a versão viva sempre foi a de `forgehub_messages_mcp.py`, registrada primeiro). Teste de contrato:
`backend/tests_unit/test_mcp_server_map.py`. Plano original: Pacote com cliente comum e um arquivo por servidor; L2 resolvida (uma cópia). Um servidor
`forgehub_all`, temporário, expõe tudo para compatibilidade. Teste de contrato: cada ferramenta pertence a
exatamente um servidor, nenhuma duplicada, nenhuma órfã (L12).

**Fase 2. Autorização** (seção 4). Credencial própria em todos os servidores; delegações novas no backend;
token da ponte fora dos agentes. Revisão independente obrigatória (P4: credenciais e produção).

**Fase 3. Migração dos agentes, em ondas**, com `fleet_config_guard accept` e um reinício do gateway por onda:
Scriba e Mnemosyne → Atlas e Daedalus → Themis e Kairos → Hephaestus e Aegis → Athos → execuções despachadas
(L10) → Lara e Maia. Em cada onda: resolução real das ferramentas (`_get_platform_tools`), um turno de teste e
verificação de que nenhuma citação antiga ficou.

**Fase 4. Documentação e controles** (seção 6).

**Fase 5. Remoção** do `forgehub_all` e das entradas antigas no catálogo (L7).

## 6. Documentação, skills e Auditor

- **Foundation:** novo `30_docs/FORGEHUB_MCP_SERVERS.md` (servidores, ferramentas, matriz, credenciais) no lugar
  do `FORGEHUB_MCP_SERVER.md` desatualizado (L8); atualizar `36_governance/AGENT_CONFIGURATION_GUIDE.md`; registro
  em `47_migrations/`; política sobre a armadilha do `platform_toolsets` (L5).
- **Regras de negócio:** `docs/business_rules/09-mcp.md` (regras MCP-001…), índice no README.
- **Skills, uma por servidor**, editadas pelo `shared_skills_lock.py` e copiadas para Claude, Codex e agy:
  `forgehub` (núcleo, enxuta), `forgehub-factory`, `forgehub-missions`, `forgehub-ops`, `forgehub-registry`,
  `forgehub-personal` (Maia). A skill `remote-access` existente passa a cobrir `forgehub_remote`.
- **Auditor (checagens novas):**
  - cada agente recebe exatamente os servidores da matriz;
  - nenhuma lista `platform_toolsets` esconde um servidor habilitado sem intenção registrada;
  - nenhum agente tem o token da ponte no ambiente do MCP;
  - as chaves da produção conferem com o arquivo versionado.

## 7. Decisões de Marcelo

- **D1. Decidido (2026-11-15, Marcelo): 7 servidores**, como na seção 3. Servidor MCP aqui é um programa na
  mesma VPS que entrega um grupo de ferramentas, não uma máquina.
- **D2.** A matriz da seção 3, especialmente quem pode `execute_database_query`, reiniciar contêiner e emitir credencial.
- **D3. Decidido (2026-11-15, Marcelo):** o `forgehub_all` de compatibilidade fica até a última onda + 7 dias,
  e só é removido quando o Auditor não registrar mais chamadas pelos nomes antigos.
- **D2. Decidido (2026-11-15, Marcelo).** Credenciais: a **renovação** da credencial fixa de agente cadastrado e
  ativo é automática (rotina do ForgeHub, grava no ForgeVault, o agente nunca vê o token), validade de 90 dias e
  renovação 7 dias antes, sem aprovação; **emissão nova** (agente novo, sem credencial, vazamento) só o Athos pede
  e Marcelo aprova na aba Aprovação (botões no Telegram ficam para depois). Consultar o banco: Athos, Aegis e
  Hephaestus. Reiniciar contêiner: Athos e Hephaestus. **Ajuste ao uso real (2026-11-15, Marcelo: "ajustar por demandas", "manter os
  direitos já adquiridos"):** somou-se o que cada agente usou nos 30 dias anteriores. Ver status também para
  Scriba, Mnemosyne e Daedalus; rodar o Auditor também para Hephaestus e Scriba; consultar o banco também para
  Mnemosyne; ver o registro também para Hephaestus. Tabela completa: especificação da Fase 2, seção 2. Lacuna L13: hoje `issue_agent_credential` devolve o token
  em texto ao agente, e as credenciais fixas não têm validade.
- **D4. Decidido (2026-11-15, Marcelo): a lista oficial fica no ForgeHub e cobre todos os agentes cadastrados;
  acesso por demanda.** Agente não cadastrado não recebe servidor. Base fixa: todos recebem `forgehub` (núcleo); os
  que trabalham com projetos, também `forgehub_factory`. O resto (`missions`, `ops`, `registry`, `remote`) é
  liberado para a tarefa que precisa: em execução despachada, o ForgeHub monta os servidores daquela execução; no
  Telegram vale a base fixa (mudá-la exige configuração e reinício do gateway). Servidores sensíveis (`ops`,
  `registry`, `remote`) exigem delegação, como o acesso remoto. O ForgeVault guarda só os segredos. A matriz da
  seção 3 passa a ser o teto de cada agente, não o que ele recebe sempre.

## 8. Fora deste plano

Reduzir o prompt do Hephaestus além do que a divisão já reduz; MCPs de outros sistemas (Darckware, Moodle,
SAEDAS, CoreTI); o MCP do ForgeRouter e do ForgeVault.
