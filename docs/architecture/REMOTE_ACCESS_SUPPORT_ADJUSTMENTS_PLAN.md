# Acesso Remoto — ajustes do processo de suporte

Pedido de Marcelo em 2026-11-11: o Acesso Remoto gerencia todas as estações e servidores e já
tem "Agentes autorizados a fazer manutenção". Ele pediu para verificar as lacunas do processo de
suporte e planejar os ajustes. **Os formulários não devem abrir em modal, e sim à direita**
("não quero essa tela modal. O formulário precisa abrir a direita").

## Status

| Fase | Situação (2026-11-11) |
|---|---|
| 1 — Formulários à direita | **Homologada em 2026-11-11** (566 testes, build, Chrome 1440/390 no backend de teste); não commitada, sai junto com a fase 2 |
| 2 — Autorização única + reorganização da tela | Aprovada, aguarda a fase 1 |
| 3 — Ciclo com o chamado da Darckware | Planejada |
| 4 — Alerta de máquina | Planejada |
| 5 — Documentação | Sincronização da Foundation feita em 2026-11-11; skill e CLAUDE.md depois da fase 2 |

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
2. **"Pedir ao agente"** aceita agentes com qualquer uma das duas permissões. Se o agente tem
   comandos livres, o texto da tarefa cita `run_remote_command`, e não apenas
   `run_maintenance_script`. O pedido é recusado só quando o agente não tem nenhuma das duas
   permissões que a tarefa exige.
3. **`DirectCommandCreate` ganha `darckware_item_kind`/`darckware_item_id`** (as colunas de
   `host_executions` já existem), e o MCP `run_remote_command` passa a aceitá-los. Assim, o
   trabalho por comando também fica ligado ao chamado.
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
5. **Testes:** backend (pedido com agente só direto, comando com chamado, recusa sem permissão) e
   frontend (cartão único, painel, abas, menu "Ações" por perfil).

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
   - Testes: um agente com teto `read` é recusado num script `change`; o atalho grava exatamente
     esse perfil.
7. Nota da revisão da fase 1: o motivo de inelegibilidade do agente (`direct_access_problem`)
   só confere `run_remote_command`. No cartão único, dar um motivo por permissão (scripts
   confere `run_maintenance_script`; comandos confere `run_remote_command`).

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

## Fase 4 — Alerta de máquina (lacuna 10)

- Um loop de 15 min reaproveita a prontidão com o cache de 5 min da sondagem (sem rajada de login
  nas estações) e cria uma `Notification` quando uma máquina sai de `complete`, ou fica
  `offline`, `unknown` ou `not_prepared`. Deduplica por `event_key` (máquina + estado) e avisa
  quando a máquina volta.
- Fonte não lida resulta em `unknown`, nunca em alerta falso de "offline". O loop não roda sob
  `ENVIRONMENT=test`, que já desliga todos os loops.

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
- [ ] `CLAUDE.md`: registrar o cartão único, a aba Agentes e o chamado no comando.
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
