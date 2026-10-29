# Primeira onda — plano de implementação

> **Para execução:** usar `superpowers:executing-plans` tarefa a tarefa. IDs abaixo são referências
> locais de planejamento, não números de Messages/ProjectTask. Nenhuma linha está marcada como
> entregue. Não criar trabalho duplicado quando já houver tarefa registrada no ForgeHub.

**Objetivo:** provar o fluxo real com uma missão C.0+C.1, impedir conclusão sem prova/revisão e
isolar testes/contexto antes de ampliar a operação.

**Arquitetura:** reutilizar Produto/Versão/Projeto/PlanningItem/ProjectTask e Messages. Acrescentar
somente a base mínima de missão, os guards e ferramentas necessários à primeira prova; implementação
completa de Missão e a racionalização do legado vêm depois. Registro real em produção; testes que
alterem dados somente na área isolada, com integrações simuladas.

**Stack:** FastAPI/Pydantic/SQLAlchemy/Alembic, PostgreSQL em contêiner separado, React/TypeScript,
TanStack Query, Vitest/Playwright e MCP Python existentes. ForgeVault em .NET permanece apenas no
desenho F.1 nesta onda.

**Especificação:** [04](04-missao-pipeline-e-papeis.md), [07](07-fases-de-implementacao.md),
[10](10-area-de-teste-e-identidade.md), revisão [CONSOLIDADO](revisao/CONSOLIDADO.md) e
[decisões/limites](09-lacunas-e-decisoes.md).

## Aprovações e pré-requisitos por etapa

| Etapa | Situação e alcance |
|---|---|
| Consolidação documental atual | Autorizada por Marcelo; esta revisão e a matriz não executam o plano |
| M0.SPEC e F.1 | Produzem especificações para revisão; a leitura/escrita documental não exige criar previamente um contêiner de teste |
| T.1 e provisionamento | Exigem especificação própria, inventário de recurso e autorização de execução; T.1 cria o alvo isolado, não pressupõe que ele já exista |
| Código/testes mutantes | T.2+T.3 e contratos da fatia antes de executar testes que alterem estado |
| Baseline de execução / M0.5 | Conteúdo exato, ids/hashes, papéis, prazo, orçamento e contexto; esta aprovação não foi simulada nesta consolidação |
| Foundation e skills | Publicação pelo dono canônico com backup/revisão/migração; nenhum arquivo imutável alterado aqui |
| Produção | Gate manual aplicável na Onda 1 com backup/restore do escopo, rollback testado e autoridade válida; futura Q.5 automatiza o controle |

Recursos e ambiente são pré-condições de provisionamento e validação mutante, não uma dependência
impossível antes de escrever a especificação ou antes de a própria T.1 criar o ambiente. Prova de
backup/restore é exigida antes da alteração de produção; não bloqueia análise documental isolada.

### Aceite mínimo persistido da M0

M0.SPEC define o subconjunto persistido dos estados do 04 e a autoridade de transição já necessária
para `pronta/ativa/aguardando aceite/concluída`; não depender da tela/gerador automático M.1n da Onda 3.
Na M0, Scriba prepara o dossiê manual versionado como Artefato; o aceite de Marcelo é uma Approval
sobre a versão/hash exatos, com trilha e autoridade verificadas pelo backend. Sem inferir aceite de
Project.status ou um nome no Markdown. A delegação futura mission.accept não cria um bypass: na
primeira missão, o aceite é de Marcelo. M.1n automatiza o que esse registro mínimo já comprova.

## Limites globais

- Porthus/Claude Code implementa; Dartan/agy revisa (decisão D-1 de 28/10: Codex sem cota). Aramis/Codex volta como executor ou revisor quando a cota voltar, por nova atribuição. Comparar identidades registradas; autor/coautor
  não valida sua própria entrega. Toda tarefa tem um dono, colaboradores e verificador distintos.
- T.1 → T.2 → T.3 antecede V-a/N.0 e toda validação que altere estado. Não rodar o pytest atual com
  defaults de produção. Primeiro testes unitários sem conftest (`--noconftest`) e guard explícito.
- Postgres de teste: contêiner, volume, porta/rede e credencial próprios. Seed fictício; reset
  estritamente no teste, sem cópia de clientes, segredos ou dados pessoais. Limites de CPU/RAM antes
  de subir; falta de recurso impede o provisionamento em vez de reutilizar a instância de produção.
- Nenhum teste envia e-mail/Telegram, publica portal, acessa cliente ou executa manutenção real.
- `done`/`deployed` passam a exigir globalmente, em novas transições, execução verificada e TaskExecutionReview independente. Conclusões históricas não são reabertas automaticamente; baseline/hash exige baseline vigente quando aplicável, sem bloquear projetos comuns por um estado de missão. DONE do runtime
  é relato. Membros/roles/permissões/revisões existentes não podem ser removidos por R.1.
- Aprovação liga ids/hash ao conteúdo exato da tarefa, brief e critérios; mudança exige nova
  validação/change request. A baseline não cria autorização para ações fora de seu ambiente/escopo.
- Abertura real M0.5 exige M0.R publicado, contenção C.2.R ativa e comprovada, prazo/orçamento, papéis, contexto mínimo e baseline aprovados. Datas e
  tetos são preenchidos na liberação da baseline, não inventados nesta edição. Não reaprovar uma
  ação já autorizada, mas não tratar aprovação de planejamento como aprovação de gastar/publicar.
- A allowlist do corpo de despacho não contém o hook do runtime. C.2a prepara a contenção sem esperar C.1; C.2.R ativa via Athos e comprova com canários reais antes de M0.5. O isolamento completo por política vem em C.2b/C.2b.R. Sem prova de contenção, não abrir a missão real.
- Alteração de Foundation/skill compartilhada somente pelo Athos e seu processo; registrar backup,
  migração documental e rollback. Sem restart do gateway Hermes ou rotação de credenciais.
- Produção: alteração de modelo/guard só após smoke/rollback no teste, backup elegível do escopo e
  aprovação aplicável. G.12 completo não está entregue; histórico de backups ok não libera migration.

## Foco da revisão

1. Tentativa de done/deployed sem execução ou por revisor igual ao executor: recusar por qualquer entrada.
2. Baseline velha, tarefa editada/adicionada, CR, retry ou processo incerto: não despachar duas vezes ou apagar run_id.
3. DSN/env/reset aponta produção, API externa ou dados reais: falhar antes de conectar/enviar.
4. Identidade sem escopo, revogada ou com permissão só em outro projeto: 401/403, sem vazamento ou impersonação.
5. Primeira missão depende da própria conclusão, do isolamento completo C.2b ou de ferramenta futura: detectar ciclo; ensaio usa fixtures/contexto mínimo.

## Pacotes e ordem

A [matriz JSON](onda1-tarefas.json) é canônica para a Onda 1. As tabelas de 07 e o resumo abaixo são projeções verificadas integralmente (ids, responsáveis, revisores, arestas e aceite); editar a matriz e atualizar as projeções na mesma mudança. Status inicial de tudo: planejado.

| ID | Responsável | Verificador | Predecessores |
|---|---|---|---|
| 0.14 | athos | porthus | — |
| 0.15 | porthus | athos | 0.14 |
| T.1 | porthus | dartan | 0.15 |
| T.2 | porthus | dartan | T.1 |
| T.3 | porthus | dartan | T.2 |
| T.4a | hephaestus | aegis | T.2, T.3 |
| T.6 | athos | aegis | T.2, T.3 |
| F.1 | porthus | aegis | 0.15 |
| N.0 | porthus | dartan | T.2, T.3 |
| V-a | porthus | dartan | T.2, T.3 |
| M0.SPEC | porthus | dartan | 0.15 |
| M0.0 | porthus | dartan | M0.SPEC, T.2, T.3 |
| M0.1 | atlas | dartan | V-a, M0.R |
| M0.2a | porthus | dartan | M0.0 |
| M0.2b | porthus | dartan | M0.2a, M0.6b |
| M0.2c | porthus | dartan | M0.2b, M0.6a, M0.6b |
| M0.2d | porthus | dartan | M0.2a |
| M0.6a | porthus | dartan | M0.0 |
| M0.6b | porthus | dartan | M0.0 |
| M0.3 | athos | themis | M0.2c, M0.2d, T.6 |
| M0.4 | athos | dartan | M0.3 |
| M0.5 | athos | porthus | M0.1, M0.4, M0.R, C.2.R |
| C.0 | mnemosyne | dartan | M0.5 |
| C.1 | athos | mnemosyne | C.0 |
| C.2b | porthus | dartan | C.1, C.2.R, T.2, T.3 |
| A.1 | porthus | dartan | T.2, T.3 |
| A.2 | porthus | dartan | A.1 |
| B0 | hephaestus | aegis | T.2, T.3 |
| M0.R | hephaestus | aegis | M0.2c, M0.2d, M0.6a, M0.6b, M0.4, B0, V-a |
| A.R | hephaestus | aegis | A.1, A.2, B0 |
| C.2a | porthus | dartan | M0.SPEC, T.2, T.3 |
| C.2.R | athos | aegis | C.2a |
| C.2b.R | athos | aegis | C.2b |

## Especificações e passos por entrega

Os caminhos abaixo são alvos de implementação, não arquivos já entregues. Novos nomes podem ser
ajustados na especificação da fatia antes do despacho, preservando contratos/aceites. Cada fatia tem
seu PR/commit e revisão; não implementar o grupo inteiro sem verificar cada passo. Reutilizar
funções/rotas atuais onde existirem; novos endpoints são marcados como propostos em M0.SPEC.

### 1. T.1 — Guard e banco de teste separado

**Arquivos:** criar `docker-compose.test.yml`, `scripts/test-env.sh`,
`backend/app/core/test_environment.py` e `backend/tests_unit/test_test_environment_guard.py`;
alterar `dev.sh`, `backend/app/tests/conftest.py` e a configuração em `backend/app/core/config.py`.
**Contrato:** `validate_test_target(settings) -> None` falha antes de conectar se ambiente, DSN,
porta, usuário, volume ou alvo de reset não forem os exclusivos de teste. O script aceita somente
`start|status|reset|stop`, sem host/banco arbitrários. Reset exige nome exato e nunca volumes globais.

- [ ] Escrever testes negativos de DSN/usuário de produção, variável ausente, troca de porta e reset fora da allowlist; observar falha com `pytest --noconftest backend/tests_unit/test_test_environment_guard.py`.
- [ ] Implementar o guard, contêiner Postgres com volume/rede próprios e migrations Alembic. Nenhum fallback para o banco existente.
- [ ] Rodar teste positivo só com ambiente fictício e provar recusa de acesso à produção sem efetuar escrita nela.
- [ ] Documentar que dev.sh deixa de usar o banco real de propósito: identificar o uso atual (inclusive recuperação host_exec_runner), oferecer caminho de consulta separado sem ligar testes à produção e rollback explícito da transição.
- [ ] Registrar nome/porta/volume não secretos, limites de recurso, revisão e commit; rollback remove apenas recursos identificados de teste, sem apagar produção ou volumes desconhecidos.

### 2. T.2/T.3/T.4a/T.6 — App isolado, stubs e regra de ambientes

**Arquivos:** estender `docker-compose.test.yml`/`scripts/test-env.sh`; criar seed e stubs em
`backend/app/tests/fixtures/` e `backend/tests_unit/test_test_integration_policy.py`; atualizar
instruções de teste do projeto. Foundation/skill são entrega do Athos, com backup e migração próprios.
**Consome:** T.1 e `validate_test_target`. **Produz:** ambiente só de teste com health, seed/reset,
credenciais próprias e integrações desabilitadas/simuladas. T.2 já sobe sem saída para integrações;
T.3 substitui as integrações e verifica os bloqueios antes de qualquer roteiro mutante.

- [ ] Testar tentativa de e-mail/Telegram/portal, origem de segredo real, acesso ao bridge e a host de cliente; observar recusa em fixtures, sem enviar rede real.
- [ ] Subir T.2 com rede isolada, portas locais explícitas e limites documentados; executar seed e dois resets reproduzíveis.
- [ ] Implantar T.3 com segredos apenas de teste; validar stubs e rastrear que nenhuma chamada saiu para produção.
- [ ] T.4a: inventariar alvo Linux de teste e comprovar delegação/script inofensivo; alvo não autorizado deve falhar. T.4b não é esta entrega.
- [ ] T.6: publicar regra única pelo Athos; registrar revisão, contratos e rollback do ambiente/política; não habilitar identidade nova F.2.

### 3. V-a/N.0 — Validação atual por tela/API

**Arquivos:** reutilizar `backend/app/tests/test_software_factory_e2e.py`,
`test_factory_cockpit.py`, `test_task_governed_approval.py` e `test_factory_mcp.py`; criar relatório
versionado e roteiro Playwright do projeto em `frontend/e2e/service-factory.spec.ts`.
**Consome:** T.2+T.3. **Produz:** matriz V.1–V.15 com passou/falhou/não disponível, execução de teste,
evidência e defeitos. Não concluir capacidades a partir de um teste antigo ou com mocks que não
provam o fluxo declarado.

- [ ] Primeiro confirmar o guard e os stubs ativos; não rodar a suíte com `.env` de produção.
- [ ] Percorrer V.1–V.15 com fixtures; dispatch/incidente/ticket e publicação são simulados. Registrar falhas reais antes de corrigir cada defeito em tarefa própria.
- [ ] N.0 usa página local de teste e sessão dedicada, sem ler/fechar abas do operador; documenta o que o browser atual permite e o que falta.
- [ ] Conferir 390px e desktop, permissões e rollback do teste; Porthus entrega relatório, Dartan verifica. V-b fica para a Onda 2 e usa somente ferramentas existentes.

### 4. M0.SPEC/F.1 — Contratos antes de código

**Arquivos:** produzir `docs/architecture/MCP_MISSION_TOOLS_SPEC.md`, incluindo a base M0.0,
modelo de segurança/erros, e a especificação F.1 no projeto ForgeVault. Se o caminho de especificações
vigente diferir, o índice do projeto aponta uma única versão autoritativa.
**Consome:** código atual e 04/07/10. **Produz:** schemas/assinaturas/rotas, contenção C.2a, escopo de guards/importação e testes aprovados;
nenhum endpoint escrito apenas neste plano é apresentado como já existente.

- [ ] Inventariar e reutilizar `project.py`, `task.py`, `governance.py`, `orchestration.py` e `factory_server.py`, distinguindo endpoints existentes dos propostos.
- [ ] Para cada tool mínima, fixar input/output, ator/escopo, status HTTP e erro MCP, idempotency key e conflito, auditoria, limite/timeout e rollback.
- [ ] Fixar `project_type=mission` como migration planejada e a projeção de estado do 04; preservar creation/maintenance e ProjectAgentMembership/TaskExecutionReview.
- [ ] Especificar contexto mínimo por allowlist, sem recuperação ampla antes do isolamento completo C.2b; teste com canários fictícios Maia/Lara antes da missão real. O ensaio usa runner simulado, banco/MCP de teste e credenciais agt_ próprias do teste, nunca os perfis/bridge reais; a identidade assimétrica F.2 é futura.
- [ ] Na Onda 1, `submit_project_plan` somente submete: aprovação/baseline pela tela e usuário autorizado. Não inventar um token de aprovador nem aceitar aprovação passada na tool.
- [ ] Definir guards comuns M0.6a/b e cobrir hash/ids, replay, permissão revogada, cancelamento incerto e rollback.
- [ ] F.1 define algoritmo, kid/JWKS, claims, revogação, transição e emergência conforme 07. Revisar com executor/revisor independentes antes de habilitar as tarefas dependentes; não emitir/rotacionar credencial agora.

### 5. M0.0/M0.6a/M0.6b — Base mínima e gates

**Arquivos:** alterar `backend/app/db/models/project.py`, `api/schemas/project.py`,
`api/routes/project.py`, `api/routes/task.py`, `api/routes/governance.py`, `core/task_evidence.py`,
`db/models/governance.py` e, se necessário, o domínio atual de revisões em `orchestration.py`.
Criar migration Alembic com downgrade e testes de missão nos módulos de projeto/tarefa/governança.
**Consome:** M0.SPEC aprovado, T.2+T.3. **Produz:** base e guards reutilizáveis, sem duplicar executor. Guard de conclusão vale para novas transições de todo ProjectTask; guard de baseline vale quando houver baseline. Não tornar tarefas históricas concluídas inválidas por backfill automático.

- [ ] M0.0: teste falha para tipo missão não suportado e tentativa de contornar estado via PATCH; implementar somente extensão mínima e migration; provar que creation/maintenance continuam iguais.
- [ ] M0.6a: testes falham para done/deployed sem execução, evidência inventada, hash/arquivo de outro projeto, revisor igual a executor/coautor ou membro sem can_review/can_approve.
- [ ] Implementar validação tipada git/file/db e revisão usando TaskExecutionReview existente; comprovar que Approval, PATCH, MCP e conclusão/reconciliação do Messages não contornam o guard. Registrar actor autenticado.
- [ ] Importação histórica: criar TaskExecution relatada com commit/artefato/mensagem/run comprováveis e revisão por identidade independente; só então verificar/concluir pelo guard. Falta de prova permanece reported/blocked; não inventar run_id, revisão, aprovação ou autoaceite para importar 0.x/trabalho anterior.
- [ ] M0.6b: teste falha para editar/adicionar tarefa depois da aprovação, trocar brief/critério, usar baseline de outro projeto, repetir despacho e reutilizar autorização após CR.
- [ ] Implementar ids/hash/versionamento e guard comum em todas as entradas. Retry/incerteza preserva run_id; não limpar flags para forçar novo despacho.
- [ ] Validar migration ida/volta, permissões e suíte isolada, emitir commits por fatia e revisão Porthus. Uso real só após gate de publicação e prova de recuperação do escopo.

### 6. M0.2a–d/M0.1 — Tools mínimas e cadastro idempotente

**Arquivos:** `backend/app/mcp/factory_server.py`, rotas/schemas dos domínios reutilizados e
`backend/app/tests/test_factory_mcp.py`, `test_project_mcp.py`, `test_messages_factory_context.py`;
acrescentar casos novos às suítes de projeto, atribuição, dependência e DocLink.
**Consome:** schemas de M0.SPEC e guards M0.6, nunca credencial genérica compartilhada para operar
Software Factory. **Produz:** tools mínimas e ids reais documentados, sem duplicação da P.1.

- [ ] M0.2a: testes falham para criar produto/projeto duplicado, membro fora do escopo, papel inválido e autorrevisão; implementar create_internal_project/manage_project_members reaproveitando os domínios.
- [ ] M0.2b: testes falham para dependência cíclica e aprovação pela própria tool; implementar submit_project_plan/add_task_dependency, sem atalho para aprovar.
- [ ] M0.2c: testes falham para despacho com predecessor aberto/hash inválido, retry duplicado e relato fingindo verificação; implementar assign_task/dispatch_task/report_task_execution e provar os guards da fatia 5.
- [ ] M0.2d: testes falham para documento fora do projeto, caminho não permitido e leitura de papel/tarefas de outro agente sem autoridade; implementar attach_project_document/get_my_mission_role e consulta das próprias tarefas.
- [ ] M0.1: Atlas inventaria o produto/ciclo existentes; ensaio idempotente no teste precede registro real aprovado. Não fixar `2026.4`, criar cliente para projeto interno ou atribuir titularidade sem validação.
- [ ] Rodar contratos positivo/negativo/timeout e revisão por fatia; documentar rollback/desabilitação das tools preservando dados. Missing/invalid agt_ é bloqueio, sem emprestar token de outro agente.

### 7. M0.3/M0.4/M0.5/C.0/C.1 — Primeira missão real

**Arquivos:** convenção e skill pelo Athos; pasta futura `docs/missions/<slug>/` com brief, índice,
plano, critérios, documentos e dossiê. C.0 gera matriz de metadados sem valores/conteúdos privados;
C.1 produz política na Foundation pelo dono canônico, com revisão e aceite específicos.
**Consome:** tools/guards revisados, T.6 e contexto mínimo; abertura real também exige M0.R e C.2.R. F.1 é desenho paralelo, não requisito do ensaio com agt_ de teste.
**Produz:** primeira missão C.0+C.1 aberta, executada e aceita; plano integrado continua projeto comum.

- [ ] M0.3/M0.4: convenção com autoridade/delegação/substituto; ensaio completo em fixtures e aprovação de contexto por allowlist sem recuperação ampla. Não contar o ensaio como missão de produção concluída.
- [ ] M0.5: preencher prazo/orçamento, papéis/critério↔tarefa, baseline/hash e artefatos; obter somente as aprovações ainda necessárias para esse conteúdo concreto. Verificar backup/gate do código de suporte antes de uso real.
- [ ] Abrir a missão real em produção depois das ferramentas; C.0 realiza o levantamento de metadados e C.1 elabora/revisa/publica a política. A execução de C.0/C.1 não precede sua abertura nem condiciona a própria abertura.
- [ ] Cada entrega segue execução→prova→revisão independente; terceiro verifica a consolidação. Marcelo aceita o dossiê e a política; não simular esse ato por token ou automação.
- [ ] Sem autorrevisão, segredos, conteúdos de clientes ou classificação inventada. Pendência real fica blocked e com motivo; não registrar done para satisfazer a saída da onda.

### 8. C.2a/C.2.R/C.2b/C.2b.R — Conter, completar e ativar recuperação de contexto

**Arquivos:** alvo compartilhado observado `/root/.hermes/shared-skills/_hooks/knowledge_cycle.py`; inventariar e confirmar symlinks e consumidores reais antes de alterar;
a localização deve constar na spec da tarefa antes de editar. C.2b reutiliza a política C.1; C.2a é contenção pré-política. Não alterar
cópias inativas. Testes com diretórios artificiais, nunca notas pessoais de produção.
**C.2a:** contenção pré-política não depende de C.1; preparar patch em área autorizada, revisar e ativar somente pelo processo de desbloqueio/publicação do Athos em C.2.R. O hook é compartilhado; uma edição não é exclusiva de um perfil. Canários comprovam o arquivo/versão efetivamente usados por todos os consumidores, sem reiniciar gateway nem alterar os perfis para simular prova.

**C.2b:** após C.1, recuperar só KB do agente e `shared/approved/` compatível com allowed_consumers,
classificação/retention; documento sem metadados fica fora do prompt. Modo observação registra
somente contagens/ids redigidos, sem texto excluído no log.

- [ ] Escrever testes de symlink/traversal, coautoria, metadados ausentes, conteúdo expirado/não aprovado e canários fictícios Maia/Lara; observar falha com guard de teste.
- [ ] Implementar primeiro observação; conferir com Mnemosyne e revisão Porthus sem expor conteúdo.
- [ ] C.2.R/C.2b.R: ativar apenas pelo processo do Athos, depois do teste de vazamento verde, backup/restauração do arquivo efetivo e autorização aplicável; registrar canários no runtime real para cada consumidor. Não editar arquivo compartilhado imutável diretamente como bypass. Testar erro da fonte como recusa segura, não fallback para a KB inteira.
- [ ] Registrar arquivo/versão efetivos, evidência de ativação e rollback; não reiniciar o gateway Hermes para aplicar por tentativa.

### 9. A.1/A.2 — Agentes e rotinas nas Atividades

**Arquivos:** `backend/app/core/agent_live_state.py`, a rota de Agent Activity existente,
`frontend/src/pages/agent-activity/index.tsx` e `index.test.tsx`, hooks e catálogos de tradução usados.
A spec fixa o arquivo de rota após inventário; não duplicar SSE/timeline ou usar o novo Dashboard
como prova dessas tarefas.
**Consome:** registro canônico, rotinas atuais e T.2+T.3. **Produz:** lista de agentes elegíveis e
ocorrências de rotina com origem/resultado, inclusive externos ociosos.

- [ ] Testar agente externo ativo ocioso, aposentado, canal não aplicável e fonte desconhecida; registrar falha antes de corrigir A.1.
- [ ] Testar próxima ocorrência, executada/falhou/perdida e fuso horário; A.2 deduplica e não mostra inexistência de canal Telegram como agente offline.
- [ ] Implementar sem contagem fixa de agentes e sem acionar rotinas reais. Verificar 390px/desktop, acessibilidade e pt-BR/en/es.
- [ ] Revisão independente e evidência por fatia; rollback da interface/API sem apagar histórico.

### 10. B0/M0.R/A.R — Recuperação e publicação reais

**Consome:** código/contratos e testes revisados; permissões específicas para dados de produção,
backup e publicação. **Produz:** provas de recuperação e versões efetivamente implantadas. Nada
disso é executado por esta consolidação.

- [ ] B0: inventariar o escopo forgehub_postgres, RPO/RTO e responsáveis; obter snapshot recente identificável e testar restauração/integridade antes da migration de produção.
- [ ] Restauração real usa quarentena de recuperação dedicada, sem aplicações/agentes comuns, sem egress e sem compartilhar volumes/dados com seed ou suíte. Expor somente metadados de integridade; dados reais não viram fixtures. Acesso/retorno/descarte seguem aprovação e retenção próprias.
- [ ] M0.R: após ensaio M0.4, publicar M0.0/guards/tools com aprovação do conteúdo exato, backup elegível e rollback testado; registrar migrations, versões e smoke autenticado. M0.1/M0.5 dependem deste nó, não apenas do commit.
- [ ] A.R: mesmo gate para A.1/A.2, revalidando backup do escopo quando aplicável; registrar a versão realmente em uso. C.2.R e C.2b.R têm seus próprios gates de publicação do hook e backup/restauração do arquivo.
- [ ] Falha de backup, rollback, aprovação, smoke ou contexto real bloqueia o uso; não reduzir o gate porque G.12 completo só vem na Onda 3.

## Aceite da primeira onda

- [ ] V-a/N.0 com relatório atual; testes/envs isolados e sem envios externos.
- [ ] M0.SPEC, F.1 e convenção revisados; tipo missão/guards migrados e verificados antes de uso real.
- [ ] Done/deployed (guard global prospectivo) e baseline/hash protegidos em todas as entradas, com evidências e revisões.
- [ ] Missão real C.0+C.1 aceita, política aprovada e registro real preservado em produção.
- [ ] B0 comprova recuperação do escopo e M0.R publica o suporte antes do cadastro/uso real. C.2.R contém antes da missão; C.2b.R ativa política completa ao final, com canários reais. A.R publica A.1/A.2 após teste e gate, sem inferir release do build.
- [ ] Dossiê com fontes, identidades de revisão, links, escopo das publicações e pendências remanescentes.

Este checklist é critério de entrega futura. A consolidação atual não marca nenhum desses itens
como executado. Windows, tokens assimétricos implantados, fila G.11b, saneamento/descarte de memória
e contato comercial permanecem fora desta primeira entrega conforme 01/09.
