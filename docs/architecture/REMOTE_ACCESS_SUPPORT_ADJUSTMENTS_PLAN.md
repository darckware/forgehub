# Acesso Remoto — ajustes do processo de suporte

Pedido de Marcelo em 2026-11-11: o Acesso Remoto gerencia todas as estações e servidores e já
tem "Agentes autorizados a fazer manutenção". Ele pediu para verificar as lacunas do processo de
suporte e planejar os ajustes. **Os formulários não devem abrir em modal, e sim à direita**
("não quero essa tela modal. O formulário precisa abrir a direita").

## Status

| Fase | Situação (2026-11-11) |
|---|---|
| 1 — Formulários à direita | **Homologada em 2026-11-11** (566 testes, build, Chrome 1440/390 no backend de teste). **Publicada em 2026-11-11** com a fase 2 (`5c3e5ad`) |
| 2 — Autorização única + reorganização da tela | **Homologada em 2026-11-11**: backend e frontend revisados; Chrome 1440/390 com concessão real na base de teste (somente leitura → comandos 1 h com confirmação de máquina sensível → remoção). Corrigido um defeito anterior: a concessão de scripts pela tela falhava com 422 desde 2026-11-08. Scripts Windows conferidos no PowerShell 7.4 (sintaxe e validação); falta rodá-los numa estação real (Marcelo). **Publicada em 2026-11-11** (`7f8199c`, imagens `fh-7f8199c`, release `remote-access-7f8199c`, sem migração), com o journal do cron bloqueado (aprovado por Marcelo) |
| 3 — Ciclo com o chamado da Darckware | **Publicada em 2026-11-12** (`173c8a0`, imagens `fh-173c8a0`, release `ticket-loop-173c8a0`, sem migração). Revisão independente sem bloqueio (5 correções aplicadas); 2282 testes no backend, Chrome 1440/390 |
| 4 — Alerta de máquina | Planejada |
| 5 — Documentação | Feita em 2026-11-11: Foundation sincronizada, skill `remote-access` 1.1.0, CLAUDE.md; a regra não mudou |

## Documentos de acesso remoto

| Documento | Papel |
|---|---|
| `REMOTE_ACCESS_RULE.md` | **A regra** (Marcelo, 2026-11-06): conta `darckware`, chave no cofre, agente só pelo ForgeHub. Fonte canônica; a Foundation tem uma cópia em `52_policies/` |
| `REMOTE_MAINTENANCE_PLAN.md` | Desenho técnico do que já está publicado: execuções, delegações, propostas por hash, acesso direto, transferências |
| `REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md` | Histórico (2026-10-17): como Servidores e VPN viraram uma tela só |
| `../implementation/2026-11-08-remote-access-continuation.md` | Registro da publicação de 2026-11-08 (`fh-4b6ef28`) e das evidências |
| **Este documento** | Próximos ajustes do processo de suporte (fases 1 a 5) |
| **Skill compartilhada `remote-access`** | O que os agentes leem antes de agir numa máquina: regra, ferramentas, códigos de recusa e relato (1.0.0, 2026-11-11). Ligada a todos os perfis com o MCP `forgehub` (menos Lara e Maia) e aos três runtimes externos |
| Skill compartilhada `forgehub` §4.1 | Só aponta para `remote-access` (1.4.0) |

## Situação em 2026-11-11 (produção, só leitura)

- Versão em produção: `fh-2d0eeab`, que já inclui a configuração por agente, o Pausar, a ECO-060
  e as transferências.
- Nenhum agente está autorizado: `authority_delegations` não tem nenhuma linha
  `remote_access.execute` nem `remote_access.direct`.
- Só 3 das 23 máquinas seguem o padrão `darckware` com chave no ForgeVault (as estações
  desk-semed-admin, gat-adm-pc01 e gat-ges-nb01). 13 ainda usam `aegis`, e 11 não têm chave no
  cofre. As 5 linhas `*-0c97aee2` (100.127.9.x, criadas em 2026-10-20) parecem dados de teste.
- Nenhuma execução de agente até hoje. A última execução é de uma pessoa, em 2026-10-21.

## Fora deste plano: Marcelo faz manualmente, depois da finalização

- [ ] Preparar cada máquina com "Configurar acesso" (conta `darckware` + chave nova no cofre),
      começando pelos servidores Linux, que hoje ainda usam `aegis`.
- [ ] Levar ao cofre as chaves que ainda estão em disco
      (`/root/.hermes/profiles/aegis/server-management/ssh_keys/`: `172_15_2_5_key`,
      `95_111_252_124_key`) ou removê-las se forem duplicadas.
- [ ] Decidir as exceções: pfSense, Proxmox, NAS.
- [ ] Remover as 5 máquinas `*-0c97aee2`.
- [ ] Configurar os agentes na tela e só depois desativar o `aegis` em cada máquina.

## Lacunas e onde cada uma é tratada

| # | Lacuna | Fase |
|---|---|---|
| 1 | Nenhum agente autorizado | manual |
| 2–3 | Máquinas fora do padrão `darckware` + cofre | manual |
| 4 | Dois cartões, duas autorizações independentes ("Agentes autorizados" = scripts; "Acesso direto" = comandos), sem explicação | 2 |
| 5 | "Pedir ao agente" recusa agente que só tem acesso direto, e o texto da tarefa só fala em scripts | 2 |
| 6 | Formulário de concessão lista agentes e máquinas que não podem ser usados (Lara, Maia, máquina sem login), sem dizer por quê | 1 |
| 7 | Chamado da Darckware não gera tarefa de manutenção | 3 |
| 8 | Resultado não volta ao chamado (nota, horas, status) | 3 |
| 9 | Comando do acesso direto não registra o chamado da Darckware | 2 |
| 10 | Sem alerta quando uma máquina sai do estado `complete` | 4 |
| 11 | Windows sem transferência de arquivo | decisão pendente |
| 12 | Quais agentes fazem manutenção | decidida: todos, menos Lara e Maia |
| — | Regra, skill e Foundation desatualizadas | 5 |

## Fase 1 — Formulários à direita (frontend)

Padrão já aprovado: `pages/servers/ServerForm.tsx` virou painel à direita em 2026-10-18 (pedido
de Marcelo). Este plano extrai esse padrão e o aplica a todos os formulários da tela.

1. **Primitiva `components/ui/side-panel.tsx`**, extraída do `ServerForm`:
   - painel de altura total à direita, `max-w-xl`, largura total no celular, entrada com
     `slide-in-from-right` respeitando `motion-safe`;
   - cabeçalho fixo (título + fechar), um único corpo rolável e ações fixas no rodapé;
   - fundo `bg-black/30`, com a lista ainda visível ao lado. Clicar fora ou apertar Esc fecha o
     painel, exceto durante `submitting`;
   - `role="dialog"`, `aria-modal`, `aria-labelledby`, foco no primeiro campo e retorno do foco ao
     botão que abriu;
   - `ServerForm` passa a usar a primitiva, sem mudar o comportamento.
2. **Migrar para o painel** (um commit por tela, checklist abaixo):
   - [x] `AuthorizedAgentsCard.tsx`: "Conceder acesso a agentes" (o da captura de tela), primeiro;
   - [x] `AgentRequestDialog.tsx`: "Pedir ao agente";
   - [x] `PrepareDialog.tsx`: "Configurar acesso" / "Preparar estação";
   - [x] `RotationDialog.tsx`: rotacionar senha / chave SSH;
   - [x] `MaintenanceDialog.tsx`: histórico da máquina (painel de leitura);
   - [x] `ScriptCategoriesDialog.tsx`: classificações;
   - [x] `RevealPasswordDialog.tsx`: revelar senha.
   - [x] `pages/servers/ServerDialogs.tsx` (`InstallKeyModal`, `ImportCsvModal`, abertos pela aba
     Máquinas): o `ModalShell` deles agora é o painel.
   - O `ConfirmDialog` central continua para confirmações (excluir, ampliar acesso sensível): ele
     confirma uma ação, não é um formulário.
3. **Conteúdo do painel de concessão (lacuna 6):**
   - agentes: só os que podem usar o acesso aparecem habilitados. Os outros aparecem
     desabilitados, com o motivo vindo do backend (`direct_access_problem`), por exemplo
     "perfil sem ferramentas de manutenção";
   - máquinas: busca, status (`complete`/`partial`/`not_prepared`/`offline`) e "selecionar
     todas"/"por grupo". Máquina sem login do ForgeHub aparece desabilitada, com "preparar
     primeiro";
   - um resumo no rodapé ("3 agentes · 12 máquinas · até risco médio · 24 h") antes de gravar.
4. **Verificação:** Vitest de cada painel (abrir, Esc, não fechar enquanto grava, foco), layout em
   390 px e 1440 px, e marcar os itens em `FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` na mesma mudança.

Situação em 2026-11-11 (implementação, sem commit): itens 1 a 3 feitos. Testes em
`components/ui/side-panel.test.tsx`, `pages/remote-access/SidePanels.test.tsx` e
`AgentMaintenance.test.tsx`. Revisão independente feita (1 achado importante e 6 menores,
corrigidos; o achado 3 foi para a fase 2, item 7). Homologação no Chrome, em 1440 e 390 px, contra
um backend com o código atual na base de teste: painéis à direita, sem rolagem lateral, fundo
travado, Esc fecha e o foco volta ao botão (corrigido para o StrictMode), nenhuma requisição com
erro. O
`FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` não lista estas telas, então nada foi marcado lá.

## Fase 2 — Uma autorização por agente (lacunas 4, 5 e 9)

1. **Um cartão só, "Agentes autorizados"**, com uma linha por agente. Editar abre o painel da
   fase 1 com duas permissões independentes:
   - **Scripts da biblioteca**: risco máximo (leitura/alteração/destrutivo);
   - **Comandos livres** (acesso direto): `sudo/docker` sim/não.
   - As mesmas máquinas/grupos, duração (0 h = indeterminado, 1/4/24 h) e motivo.
   - O backend continua gravando as duas ações (`remote_access.execute`, `remote_access.direct`)
     como linhas de `AuthorityDelegation`, para preservar o histórico e as FKs. Só a tela passa a
     ser uma.
   - Pausar fica no cabeçalho do cartão.
   - **Frontend feito (fase 2b, 2026-11-11):** `AgentAuthorizationsCard.tsx` +
     `useAgentAuthorizationViewModel` (escopo em `useMachineScope`) substituem
     `AuthorizedAgentsCard`/`DirectAccessCard`; salvar chama só o que mudou, por permissão (scripts: cria a
     delegação nova e só depois revoga a antiga; comandos: PUT com a confirmação de cobertura sensível, ou
     DELETE), e uma falha aparece por permissão com o painel aberto. "Todas as máquinas" só nos comandos.
     Revisão (mesmo dia): cada permissão guarda o próprio escopo; a lista de máquinas compartilhada só é
     enviada a uma permissão quando o usuário a altera (senão cada uma reenvia as suas máquinas), e o motivo é
     só dos comandos. Uma revogação da delegação antiga que falha fica pendente ("nova permissão gravada; a
     anterior continua ativa") e Salvar refaz só ela. Várias delegações de scripts (ou uma futura/por
     projeto) aparecem uma por linha e só são substituídas por uma após confirmação explícita; "Manter" usa
     o prazo mais curto. Remover revoga toda delegação `remote_access.execute` ativa do agente (também
     futura ou por produto/projeto) e trata o 404 "fora da lista" como feito.
   - **Prazos em unidades diferentes, de propósito:** scripts da biblioteca em dias (1/7/30 ou manter o
     prazo atual), porque a delegação é um mandato limitado pelo risco; comandos livres em horas (0 =
     indeterminado, 1/4/24), porque o acesso direto é uma janela de trabalho curta e sem teto de risco.
   - **Limitação conhecida (anterior a esta fase):** a rotação de senha/chave só é oferecida a máquinas
     Prontas com `ssh_key_path` registrado; uma máquina só com chave na ForgeVault (`ssh_key_ref`) não
     aparece no painel de rotação nem no menu "Ações" dela.
2. **"Pedir ao agente"** aceita agentes com qualquer uma das duas permissões. Se o agente tem
   comandos livres, o texto da tarefa cita `run_remote_command`, e não apenas
   `run_maintenance_script`. O pedido é recusado só quando o agente não tem nenhuma das duas
   permissões que a tarefa exige.
   - **Backend feito (fase 2a, 2026-11-11):** sem scripts escolhidos, basta delegação de scripts ou acesso
     direto cobrindo todas as máquinas; com scripts, só a delegação de scripts. O texto da tarefa cita a(s)
     ferramenta(s) do agente; a auditoria do pedido grava `scripts_allowed`/`commands_allowed`.
   - **Frontend feito (fase 2b, 2026-11-11):** `useAgentRequestViewModel` lista quem tem delegação de
     scripts cobrindo todas as máquinas ou acesso direto em vigor cobrindo todas; com scripts escolhidos, só
     quem tem delegação com o risco deles. Cada agente indisponível mostra o motivo.
3. **`DirectCommandCreate` ganha `darckware_item_kind`/`darckware_item_id`** (as colunas de
   `host_executions` já existem), e o MCP `run_remote_command` passa a aceitá-los. Assim, o
   trabalho por comando também fica ligado ao chamado.
   - **Backend feito (fase 2a, 2026-11-11):** a API usa `darckware_ticket_id`/`darckware_demand_id`
     (um ou nenhum, 422 se os dois), os mesmos nomes do MCP; grava em `host_executions.darckware_item_*`.
4. **Reorganização da tela** (Marcelo, 2026-11-11: "pode incluir a reorganização na fase 2").
   Nenhuma regra de acesso muda, só a organização:

   | Aba | Conteúdo |
   |---|---|
   | **Máquinas** | Só a lista de máquinas. Os dez botões de ação rápida do topo (Preparar estação, Rotacionar senha/chave SSH, Detectar SO, Instalador Darckware Remoto, Instalar Tailscale/RustDesk, Obter ID do RustDesk, Liberar RustDesk no firewall, Trocar senha do RustDesk) saem do topo: vão para um menu "Ações" na barra da lista e para o menu de cada máquina, que já vem com ela selecionada |
   | **Agentes** (nova) | O cartão único do item 1 (quem pode fazer manutenção, em quais máquinas, scripts e/ou comandos), o Pausar e as propostas de manutenção |
   | **Scripts e execuções** | Sem mudança |
   | **Rede Tailscale** | Sem mudança |

   - A aba ativa fica na URL (`?tab=`), para os links e o voltar do navegador funcionarem.
   - Um não admin com o módulo `servers` continua vendo só Máquinas, sem o menu "Ações".
   - Celular: as abas usam `components/ui/tabs.tsx`, que já rola para o lado, e o menu "Ações"
     cabe em 390 px.
   - **Frontend feito (fase 2b, 2026-11-11):** abas `?tab=machines|agents|scripts|network` (trocar de aba
     empilha no histórico); menu "Ações" (`components/ui/action-menu.tsx`, sem dependência nova: teclado,
     Esc, portal fixo) na barra da lista e um por máquina, que abre o mesmo painel com ela escolhida
     (`RotationDialog.initialServerIds`, `ExecutionComposer.initialMachineIds` via `?machine=`).
5. **Testes:** backend (pedido com agente só direto, comando com chamado, recusa sem permissão) e
   frontend (cartão único, painel, abas, menu "Ações" por perfil).
   - **Frontend feito (fase 2b, 2026-11-11):** `AgentAuthorizationsCard.test.tsx` (chamadas exatas por
     permissão, motivos, Somente leitura, confirmação Hermes, pausa, remoção), `index.test.tsx` (abas, URL,
     voltar, ações), `MachinesCard.test.tsx` (menus e perfil), `AgentMaintenance.test.tsx` (pedido com só
     comandos), `RotationDialog`/`ExecutionComposer` (pré-seleção). Plurais com `_zero` em pt-BR/en/es.

6. **Perfil "somente leitura" para os agentes Hermes** (Marcelo, 2026-11-11: "só vou liberar
   comandos simples para os agentes hermes, como monitoramento, serviços e somente de leitura e
   acompanhamento").
   - Comando livre não pode ser garantido como leitura (a checagem de `sudo/docker` é por texto,
     não barreira). Então "somente leitura" = **scripts da biblioteca com risco `read`**, comandos
     livres desligados.
   - No painel do agente, um atalho "Somente leitura (monitoramento)" preenche: scripts ligados,
     risco máximo leitura, comandos livres desligados, `sudo/docker` desligado. Para um agente
     Hermes, esse é o padrão do formulário; ligar comandos livres para ele pede confirmação.
   - Hoje a biblioteca tem **um** script `read` (Obter ID do RustDesk). Criar, como scripts de
     sistema (categoria nova **Monitoramento**, criada na inicialização como as outras de
     `SYSTEM_CATEGORIES`), versões Linux e Windows de:
     - estado da máquina: uptime, carga, memória, disco;
     - serviços: listar e ver o estado de um serviço (`systemctl status`/`Get-Service`), sem
       iniciar nem parar;
     - containers: `docker ps` e estado de um container (só leitura; exige `docker` sem `sudo`, ou
       o script declara que não roda onde precisaria de elevação);
     - logs: últimas N linhas de um serviço ou arquivo de log, com N limitado e caminho
       restrito a `/var/log` e ao journal;
     - rede: portas em escuta e teste de alcance de um host/porta.
     Todos com `risk="read"`, parâmetros validados e sem segredo; os testes de template seguem a
     regra de nenhum caractere de controle.
   - **Scripts feitos (fase 2a, 2026-11-11):** categoria `monitoramento`, Linux/Windows, sem `sudo`:
     `monitor_state|services|containers|logs|network` com risco `read`, e `monitor_reachability` (teste
     host:porta) com risco `change` (Marcelo: contatar outro host não é leitura). Logs só de lista fixa
     (Linux: syslog, messages, kern.log, dpkg.log, apt, nginx, apache2; journal sem sshd/ssh/sudo/logind/*auth* nem cron/crond/cronie/anacron, e as linhas do
     cron retiradas dos arquivos — Marcelo aprovou o bloqueio em 2026-11-11: trazem a linha de comando
     das tarefas, onde costumam estar senhas;
     Windows: System, Application, Setup). Serviços sem linha de comando (`systemctl show`, Get-Service).
     Parâmetros com `pattern`/`options` conferidos antes de rodar (valor com `pattern` até 1024 caracteres) e
     de novo no script. O atalho do painel segue para a fase 2b (frontend).
   - Testes: um agente com teto `read` é recusado num script `change`; o atalho grava exatamente
     esse perfil.
   - **Frontend feito (fase 2b, 2026-11-11):** atalho "Somente leitura (monitoramento)" no painel; padrão
     de um agente Hermes sem permissão; ligar comandos livres para ele abre uma confirmação. O teste de
     alcance (`change`) fica fora desse perfil, como decidido.
7. Nota da revisão da fase 1: o motivo de inelegibilidade do agente (`direct_access_problem`)
   só confere `run_remote_command`. No cartão único, dar um motivo por permissão (scripts
   confere `run_maintenance_script`; comandos confere `run_remote_command`).
   - **Backend feito (fase 2a, 2026-11-11):** `GET /remote-access/direct/agents` mantém
     `unsupported_reason` (comandos) e ganhou `scripts_unsupported_reason` (scripts), mesmo vocabulário.

8. **Bug anterior corrigido (fase 2a, 2026-11-11):** `POST /governed/authority-delegations` recusava
   `remote_access.execute` (422 "Unknown delegated actions": só aceitava `SENSITIVE_ACTIONS`), então a
   permissão de scripts nunca pôde ser dada pela tela. Agora vale `DELEGABLE_ACTIONS` (catálogo + essa ação),
   só para admin humano; `remote_access.direct` continua recusado ali.

## Fase 3 — Ciclo com o chamado da Darckware (lacunas 7 e 8)

1. **Do chamado para a manutenção:** no detalhe do chamado (Clientes › Demandas), o botão "Pedir
   manutenção ao agente" abre o painel do "Pedir ao agente" com as máquinas do cliente e o
   chamado já preenchidos.
2. **Da manutenção para o chamado:** quando a tarefa termina, o detalhe do chamado mostra as
   execuções ligadas a ele (máquina, agente, resultado) e propõe uma nota com os minutos. Marcelo
   confirma, e só então o ForgeHub chama `:log-time` (e `:resolve`, se ele escolher). Nada é
   gravado na Darckware sozinho: a franquia do cliente é consumida por decisão humana, e e-mail
   ao cliente continua passando pela aprovação da Darckware.
3. **Testes:** a proposta não grava nada; a confirmação grava uma vez (idempotente por tarefa).

Progresso (2026-11-12, branch `feat/remote-access-ticket-loop`, sem migração):

- [x] Botão "Pedir manutenção ao agente" no detalhe (Clientes › Demandas › "Manutenção remota"):
      abre o painel do "Pedir ao agente" com as máquinas do cliente (`servers.darckware_client_id`),
      desmarcáveis (ao menos uma fica), e o item pré-selecionado. Desligado, com o motivo, sem
      cliente ou sem máquina cadastrada.
- [x] O "Pedir ao agente" grava o item no `AuditEvent agent_maintenance_request`; toda execução
      de agente nessa tarefa (`launch_execution`: script, `run_remote_command`, proposta aprovada
      -- que roda numa tarefa nova e herda o item da tarefa de origem) herda o item; outro item
      dá 422 `DARCKWARE_ITEM_MISMATCH`. Transferência de arquivo não grava execução: fora.
- [x] `GET /client-ops/work-items/{kind}/{id}/maintenance`: execuções e tarefas do item; por tarefa
      terminada e não registrada, nota + minutos propostos (soma das durações das execuções,
      arredondada para cima em blocos de 30 min, mínimo 30). Não grava nada.
- [x] `POST .../maintenance/{demand_id}:record` (`log_time` ou `resolve`): só após a confirmação.
      `resolve` passa pelo mesmo `_resolve` da rota `:resolve`, que já aponta as horas (uma vez).
      Idempotência: `AuditEvent maintenance_recorded` (payload `agent_demand_id`) na mesma
      transação do audit da ação, só depois de a Darckware aceitar, sob advisory lock da tarefa;
      a segunda vez é 409 `MAINTENANCE_ALREADY_RECORDED`. Nenhum e-mail sai daqui.
- [x] Execuções feitas por uma pessoa aparecem na lista mas não entram na proposta: registram-se
      pelo "Apontar horas" de sempre.
- [x] Revisão (mesmo dia): resultado ambíguo nunca aponta duas vezes -- a tentativa
      (`maintenance_recording`) é gravada e commitada antes de qualquer escrita na Darckware;
      recusa explícita antes de escrever a descarta sozinha; timeout, 5xx ou falha depois da
      entrada de horas a deixa aberta (409 `MAINTENANCE_RECORD_UNCERTAIN`) até um admin dizer, com
      motivo, "foi registrado" ou "descartar tentativa" (`:settle`, auditado). A nota proposta é
      para o cliente (sem número de tarefa, agente, comando ou id). `:record` exige todas as
      execuções contadas em máquinas do cliente do item (409 `MAINTENANCE_CLIENT_MISMATCH`) e
      todas encerradas; o "Pedir ao agente" recusa (422) item de outro cliente. Do chamado, o
      painel abre sem máquina marcada. Execução em que nada rodou não conta; execuções
      sobrepostas contam pela união dos intervalos; "repetir nas que falharam" herda o item.

## Fase 4 — Alerta de máquina (lacuna 10)

- Um loop de 15 min reaproveita a prontidão com o cache de 5 min da sondagem (sem rajada de login
  nas estações) e cria uma `Notification` quando uma máquina sai de `complete`, ou fica
  `offline`, `unknown` ou `not_prepared`. Deduplica por `event_key` (máquina + estado) e avisa
  quando a máquina volta.
- Fonte não lida resulta em `unknown`, nunca em alerta falso de "offline". O loop não roda sob
  `ENVIRONMENT=test`, que já desliga todos os loops.

Progresso (2026-11-12, worktree `remote-access-machine-alerts`, sem merge nem deploy):

- [x] `compute_readiness` extraído de `GET /servers/readiness` (mesma tabela de decisão e mesmo
      cache de 5 min); `core/machine_status_monitor.py` + `_machine_status_poll_loop` (15 min).
- [x] Tabela `machine_status_observations` (migração `1994f24fd6e1`, ON DELETE CASCADE): primeira
      leitura é linha de base silenciosa, com um único resumo por dia na primeira passada.
- [x] Alerta ao sair de `complete` ou cair em offline/não preparada/desconhecido; "voltou" ao
      retornar; `event_key` com o instante da transição (offline → volta → offline avisa duas vezes).
- [x] Fonte ilegível (tailnet ou ponte da sondagem SSH): nenhuma transição gravada, um aviso
      "monitoramento indisponível" por dia.
- [x] "Desde <hora>" no tooltip do estado na tabela de Máquinas (`status_since`).
- [x] Revisão: degradação só após duas passadas seguidas; proteção de massa (≥ 5 máquinas ou mais
      da metade: um resumo só, e as voltas agrupadas); tailnet legível só com a VPS `online`;
      "Motivo:" em pt-BR; leitura sem transação aberta e trava só para gravar; máquina excluída no
      meio da passada é ignorada.
- [ ] Publicação (deploy próprio; a ponte não foi tocada).

## Fase 5 — Documentação

Feito em 2026-11-11 (registro: Foundation `47_migrations/2026-11-11-remote-access-docs-sync.md`,
backup em `/root/.hermes/profiles/athos/state-snapshots/remote-access-docs-2026-11-11/`):

- [x] `52_policies/REMOTE_ACCESS_RULE.md`: copiada de novo a regra atual (configuração por
      agente, 0 h, regras 8 a 10).
- [x] `30_docs/ACCESSING_SERVERS.md`, `EXECUTING_COMMANDS.md`, `server-management.md`: marcados
      como SUPERSEDED (ensinavam SSH direto com a chave do `aegis`); o texto antigo fica como
      histórico.
- [x] `43_map/ECOSYSTEM_MAP.md`, `ECOSYSTEM_KNOWLEDGE_MAP.md`, `14_agents/ATHOS.md`: o
      `SERVERS_SSH_REGISTRY.md` aposentado foi trocado por ForgeHub › Acesso Remoto.
- [x] Skill `remote-access-governance` do Athos 2.0.0 → 2.1.0: sem o vocabulário de "abertura".
- [x] Skill compartilhada **`remote-access`** 1.0.0 criada (Marcelo: "uma skill somente para o
      acesso remoto ... não sobrecarregando a skill forgehub"). A §4.1 da `forgehub` (1.4.0) só
      aponta para ela; a `remote-access-governance` do Athos foi para `.archive`; a ECO-059
      (`_tools/shared_skills_lock.py verify`) agora também cobra o link nos perfis. Registro no
      adendo da mesma migração.

Depois da fase 2:

- [ ] Skill `remote-access` 1.1.0: cartão único (scripts e/ou comandos), aba Agentes e chamado
      da Darckware no comando. As shared-skills são imutáveis: destravar, editar e travar com
      `_tools/shared_skills_lock.py` (a ECO-059 confere).
- [x] `CLAUDE.md`: registrar o cartão único, a aba Agentes e o chamado no comando. (Fase 2b: uma frase
      no tópico de Remote Access sobre abas, cartão único e Somente leitura.)
- [ ] Ajustar `REMOTE_ACCESS_RULE.md` (regra 5) se o texto da tela mudar, e copiar de novo para a
      Foundation.

## Decisões pendentes de Marcelo

- **Lacuna 11:** transferência de arquivo para Windows nesta etapa, ou continua recusada.
- ~~**Lacuna 12**~~ — **decidida em 2026-11-11** (Marcelo: "eu acho que todos os agentes dos hermes
  exceto: Lara e Maia"): todos os agentes podem fazer manutenção, menos Lara e Maia. Os 9 perfis
  Hermes já estão aptos (o ForgeHub não acusa impedimento); falta só Marcelo configurar cada um
  na tela. Skill `remote-access` 1.0.1 atualizada.

## Execução

- Ordem: fase 1 → 2 → 3 → 4, com a 5 ao final de cada fase que mudar a regra ou a tela.
- Desenvolvimento nesta sessão (Marcelo, 2026-11-11: sem agentes externos, por causa dos
  limites de cota): um subagente executor, um subagente revisor separado, e a sessão como
  supervisora, que homologa com testes, build e navegador em 390/1440 px no ambiente de teste.
  Worktree em `/root/project/forgehub/.claude/worktrees/remote-access-side-panel`. Sem merge
  nem deploy sem Marcelo.
- As fases 1 e 2 são publicadas juntas, num único deploy; as fases 3 e 4, cada uma no seu.
- Publicação: as fases 2 a 4 mudam o backend. Se a ponte for tocada,
  `systemctl restart forgehub-chat-bridge` antes do backend.
