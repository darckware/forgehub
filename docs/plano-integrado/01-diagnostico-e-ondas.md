# Diagnóstico e as três ondas

**Consolidação:** 27/10/2026, autorizada por Marcelo nesta conversa. A autorização cobre incorporar
as correções e fechar o planejamento da primeira onda. Não é evidência de implementação, aceite
final de missão, aprovação de credenciais, aumento de autonomia ou autorização para enviar mensagens
a clientes. As decisões e limites estão em [09](09-lacunas-e-decisoes.md).

## Diagnóstico e autoridade

O caminho continua sendo Service Factory → Messages → evidência → revisão independente. A Missão
acrescenta coordenação e critérios de conclusão aos projetos; a Operação 24x7 acompanha, e as
Atividades dão visibilidade. O escopo permanece congelado; novas demandas entram em planejamento
próprio, sem ampliar esta consolidação.

Os números de 24/10 (107 testes, quantidade de produtos, rotinas e despachos) são histórico, não
certificação do estado atual. Antes de cada tarefa, o executor confere o código, permissões e
serviços atuais. O dashboard publicado em 27/10 é uma entrega de monitoramento; não comprova que
Agent Activity A.1/A.2, a área de teste T ou o fechamento de missão já foram implementados.

Correções aplicadas da revisão:
- **A1/A2/A3:** primeira missão = C.0+C.1; plano integrado = projeto comum de acompanhamento no
  produto Ecossistema Foundation. Missão é projeto de coordenação ligado aos projetos executores;
  estado próprio e mapeamento explícito para Project.status estão no [04](04-missao-pipeline-e-papeis.md).
- **D2/K2:** executor de código Porthus; revisão Dartan (D-1, 28/10: Codex sem cota). Claude Code e Porthus são a mesma identidade
  e nunca satisfazem independência entre si. Comparar ids registrados, não rótulos.
- **F1/F6:** T.2+T.3 precedem V-a e qualquer validação que altere estado. O registro de missão e do
  trabalho real fica em produção; ensaios mutantes usam dados fictícios na área de teste.
- **P.6/G.11:** fila mínima G.11a fica na Onda 2; fila completa G.11b na Onda 3. P.6 não espera
  componentes da onda seguinte.
- **F4:** sucesso de um backup não prova cobertura de todos. Exigir snapshot recente por destino
  crítico e restauração de amostra antes de declarar recuperação pronta.

## Estado em 28/10/2026

**A Fase 0 está concluída.**
- **0.14:** a rodada cruzada fechou com o Athos (#41585) e o Porthus (#41584, confirmação do delta em #41624). Os ajustes que a troca da D-1 exigiu estão no commit `fd179b2`.
- **0.15:** o Marcelo decidiu D-1 a D-8 (09), e o Athos verificou o registro (#41625).

**Onda 1:** a T.1 foi implementada pelo Porthus no branch `feat/t1-test-postgres` e aguarda a revisão do Dartan (D-1). Ainda não houve merge.
- O Postgres de teste é o `forgehub_test_postgres` (`test-env/docker-compose.yml`), em `127.0.0.1:5439`, com rede `forgehub_test_network`, volume `forgehub_test_pgdata`, 512 MB e 1 CPU. Fica fora da `foundation_network`.
- Com `ENVIRONMENT=test`, o `app/core/config.py` não lê o `.env` da produção e recusa, antes de conectar, qualquer alvo fora da allowlist (`forgehub_test@127.0.0.1:5439`).
- O `conftest.py` encerra a sessão do pytest no mesmo caso, e também sem `ENVIRONMENT=test`.
- O `test-env/reset.sh` também recusa. As migrações estão aplicadas no banco de teste.
- O `dev.sh` usa o banco de teste por padrão. `--prod-db` volta aos dados reais e mostra um aviso.

A T.2 foi implementada pelo Porthus no branch `feat/t2-test-app` e aguarda a revisão do Dartan (D-1). Ainda não houve merge.
- O backend de teste é o `forgehub_test_backend` (`127.0.0.1:8002`, 512 MB, 1 CPU) e o frontend de teste é o `forgehub_test_frontend` (`127.0.0.1:4174`, 256 MB, 0,5 CPU). O `/api` do frontend vai para o backend de teste.
- A `forgehub_test_network` passou a ser `internal`: sem saída para a internet, para o host-bridge nem para outros contêineres. As portas chegam ao host por um gateway nginx que escuta só em 127.0.0.1.
- Com `ENVIRONMENT=test`, nenhum laço de segundo plano do backend inicia. As integrações simuladas são da T.3.
- `test-env/reset.sh --seed` zera, migra e aplica um seed fictício com IDs determinísticos. Dois resets seguidos dão dados idênticos.

A T.3 foi implementada pelo Porthus no branch `feat/t3-test-integrations` (29/10) e aguarda a revisão do Dartan e do Aegis (D-1). Ainda não houve merge.
- **Credenciais.** Com `ENVIRONMENT=test`, o backend só inicia com credenciais próprias do teste: `JWT_SECRET`, `CHAT_BRIDGE_TOKEN`, a chave de criptografia (`SECRETS_ENCRYPTION_KEY`) e o segredo do webhook de atividade.
  - O `test-env/init-env.sh` gera esses valores.
  - O backend recusa um valor padrão, repetido ou igual a qualquer segredo da produção. A comparação é por hash, sem mostrar valor.
- **Integrações.** Cada integração tem um único ponto de troca, a URL no `config.py`, e só pode apontar para o stub local `forgehub_test_stubs` ou ficar vazia. Isso vale para host-bridge (despacho, Telegram e mensagens, servidores, arquivos, ForgeVault), Darckware e e-mail, ForgeRouter, Tailscale e clima.
  - O stub simula o despacho, o Telegram, a fila de e-mail e os servidores fictícios.
  - O stub recusa `/v1/exec`, `/v1/fs`, o ForgeVault e hosts de cliente ou da produção.
  - Cada chamada fica registrada, sem conteúdo, em `GET 127.0.0.1:8003/_stub/calls`.
- **Proposta, não implementada:** um ambiente "teste" no ForgeVault com segredos próprios. Nesta entrega nenhum segredo foi criado nem lido no ForgeVault.

A M0.0 foi implementada pelo Porthus no branch `feat/m0-0-mission-base` (29/10) e aguarda a revisão do Dartan (D-1). Ainda não houve merge nem migração fora do banco de teste.
- **Missão = projeto** com `project_type=mission` e a extensão `project_missions` (estado único; `Project.status` é projeção gravada na mesma transação). Criação só por `POST /api/v1/missions`; `PATCH`/`DELETE /projects` recusam mudar status/tipo ou apagar uma missão.
- **Pipeline de planejamento** (P1–P8) em `planning:advance`, só em ordem; cada tentativa, aplicada ou recusada, fica em `mission_decisions`. A P2 confere as skills exigidas (`project_tasks.required_skill_ids`) do executor e dos revisores elegíveis.
- **Recusa por falta de dado:** ambiente e pré-requisitos de ambiente, pareceres por camada, disposições, rodada cruzada, itens para decisão, verificação da aplicação e dossiê ainda não têm onde ser lidos. Essas saídas recusam com `not_recorded` até as fatias M0.2b/M0.2d/M0.6b/M0.7 criarem os dados.

A M0.6a foi implementada pelo Porthus no branch `feat/m0-6a-completion-guard` (29/10) e aguarda a revisão do Dartan (D-1). Ainda não houve merge, migração fora do banco de teste nem reinício do bridge.
- **Guard global e prospectivo:** toda transição nova para `done`/`deployed`, em qualquer projeto, exige execução `verified`, evidência `git:`/`file:`/`db:` conferida e revisão aprovada por outro agente, com dependências e subtarefas concluídas. Tarefas já concluídas continuam como estão, sem backfill.

A M0.6b foi implementada pelo Porthus no branch `feat/m0-6b-baseline-guard` (29/10, sobre a M0.6a) e aguarda a revisão do Dartan (D-1). Ainda não houve merge nem migração fora do banco de teste.
- **Baseline imutável:** `plan_baselines.content_hash`/`superseded_at` e `plan_baseline_items` (um hash por tarefa, com brief e critérios da missão; o responsável fica fora, D-M0-3). `create_mission_baseline` cria a próxima e supera a anterior; a aprovação governada que a chama é da M0.2b. Para missão, `POST /projects/plans/{id}/approve` e `POST /projects/{id}/baselines` devolvem 409 `USE_GOVERNED_PLAN_APPROVAL`.
- **Guard de despacho:** `assert_task_baseline_current` dentro do `reserve_dispatch` (todo caminho até o runner) e no topo de `_dispatch_task_by_id`; recusa com os 6 códigos da §4.2 e, na fila agendada, mantém o item sem consumir tentativa. Missão pausada fica na fila.
- **Serialização de alvos:** `task_execution_targets`; `publish:production:*` em todo o Messages, `worktree`/`branch` só em missões (D-M0-2), com o `working_path` da missão como alvo implícito.
- **Evidência no host:** `file:` e `git:` são conferidos pelo host-bridge (`/v1/evidence/verify`, `/v1/git/is-ancestor`), porque o contêiner do backend não tem `git` nem as pastas dos projetos. Bridge inalcançável = "não verificado" (409).
- **Missão:** a aprovação da revisão deixa a tarefa `in_review` até o commit estar em `develop`. `deployed` é sempre recusado com `DEPLOYED_WITHOUT_RELEASE` enquanto não houver `environment_releases`.
- **Na publicação (M0.R):** `systemctl restart forgehub-chat-bridge` antes de liberar o backend. Sem isso, nenhuma tarefa com evidência `git:`/`file:` é concluída.

A A.1 foi implementada pelo Porthus no branch `feat/a1-agents-board` (29/10) e aguarda a revisão do Dartan (D-1). Ainda não houve merge nem publicação (A.R). Sem migration.
- **Quadro = registro elegível inteiro:** todo agente com `is_active` e `status=active` aparece em `GET /agent-activity` e no stream, sem exigir carta (um agente novo aparece antes de ter carta) e sem contagem fixa ou limite de linhas. Inativos e aposentados ficam fora.
- **Externos sempre presentes:** claude/codex/agy sem despacho aparecem `idle`, só com fatos do Messages (fim do último despacho, tarefas na fila), sem telemetria inventada.
- **Canal/gateway por agente:** `channel_health` com Telegram (`agent_telegram`) e gateway (ok/parado). Bridge inalcançável = `unknown`; sem canal = `not_applicable`, sem aparecer como offline. Uma leitura do bridge em cache, a mesma dos alertas.

## Onda 1 — Provar a base e fechar os riscos imediatos

O detalhamento executável está em [12 — Primeira onda](12-primeira-onda.md), com responsáveis,
verificadores, dependências e aceites. A [matriz de execução](onda1-tarefas.json) contém somente ids
locais do plano; nenhum número de ProjectTask foi inventado ou criado por esta edição.

| Frente | Entrega da primeira onda | Dependência de segurança |
|---|---|---|
| C.0/C.1 | Levantamento sem segredos e política de contexto; execução real será a primeira missão | Missão real só é registrada após M0.4; antes, apenas especificação e leitura preparatória |
| T.1/T.2/T.3/T.4a/T.6 | Postgres em contêiner/volume/credencial próprios; app de teste, seed/reset, integrações simuladas e alvo Linux autorizado | Sem conexão ao banco ou credenciais de produção; Windows T.4b não bloqueia a validação Linux |
| V-a/N.0 | Roteiro tela/API e diagnóstico do navegador atual com dados fictícios | T.2+T.3; sem e-mail, Telegram, portal ou manutenção real de cliente |
| M0.SPEC/M0.0/M0.1/M0.2a–d/M0.6a–b | Contratos MCP, base mínima de missão, cadastro idempotente e ferramentas mínimas; revisão de execução e guard de baseline | Contrato aprovado antes de código; T.2+T.3; nenhum autoaceite ou hash fora de escopo |
| M0.3/M0.4/M0.5 | Convenção, instruções e primeira missão C.0+C.1 com acompanhamento e aceite | Guards M0.6a/b, contexto filtrado, papéis/delegações e baseline exata antes do despacho |
| C.2a/C.2.R | Contenção mínima do hook compartilhado antes da missão real, com canários no runtime | Independe de C.1; revisão e publicação canônica pelo Athos, backup do arquivo e rollback |
| C.2b/C.2b.R | Isolamento completo por política, observado/revisado/ativado | Política C.1 aprovada, contenção anterior e testes de não vazamento |
| B0/M0.R/A.R | Backup/restauração de escopo e publicações reais da base/tools/atividades | Aprovação do conteúdo exato e prova de versão ativa; código revisado não equivale a implantado |
| F.1 | Especificação da identidade assimétrica e emergência | Somente desenho; nenhuma rotação, novo login ou desligamento de token nesta onda |
| A.1/A.2 | Todos os agentes elegíveis e rotinas nas Atividades | Registro canônico ativo; testes isolados, sem dependência do novo dashboard |

**Saída:** V-a aprovada com relatório; nenhuma suíte/dev.sh alcança produção; contratos e guards
M0.6a/b aprovados; M0.R publicado e C.2.R ativo antes da missão; primeira missão C.0+C.1 registrada e aceita em produção com documentação e provas independentes; C.2b.R ativo após teste de vazamento; F.1 revisado; A.1/A.2 verificados e publicados por A.R. Ensaios
ficam no teste; o registro real de coordenação fica em produção. Não afirmar que uma missão de
política/leitura precisou executar em um sistema de teste.

A documentação consolida o planejamento; cada item acima permanece **não implementado por esta
consolidação**. O fechamento da onda exige evidência real, e não marcar checkboxes deste texto.

## Onda 2 — Agentes operam e Marcelo supervisiona

V-b usa apenas ferramentas existentes; as lacunas viram P.1 por ferramenta. Depois vêm S/R/B, P,
I, Q.0–Q.6, núcleo D, O.1–O.3, E.1/E.4, C.3/C.5/C.6 e N.1–N.5/N.10 conforme o grafo de 07.
**G.11a** entrega a fila mínima de aprovações/dúvidas com dados já disponíveis e precede P.6;
G.11a não depende de M.1 ou G.2. F.2–F.6/T.5 implantam a identidade e os demais ambientes por
sistema, após especificação e aprovação próprias. Windows T.4b depende da escolha do alvo D-4.

**Saída:** um serviço de cada linha adotada percorre o fluxo com evidência/documento e supervisão
real, sem retirar proteções existentes de membros/revisão ao aposentar a Orquestração.

## Onda 3 — Garantir e aprender

M.1 completo/M.2–M.4, documentação e contexto restantes, N.6–N.9, F.7–F.9 e G completo, incluindo
**G.11b** (fila unificada e todos os tipos de decisão). Aposentar credenciais ou subir autonomia
exige concessão específica e evidência. Recuperação G.12 depende de inventário, snapshots por
alvo crítico e restauração de amostra; não de uma contagem agregada de backups ok.

Nada da onda seguinte começa antes do aceite da anterior. Dentro de cada onda valem as arestas
explícitas de 07 e da matriz da Onda 1, não uma seta geral que as contradiga.

---
[← Índice](README.md)
