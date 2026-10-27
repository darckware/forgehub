# Consolidado da revisão crítica (Fase 0, tarefa 0.13)

**Data:** 2026-10-25
**Aplicação em 27/10:** relatório histórico preservado. A versão normativa consolidada está em 01/04/07/08/09/10/12; decisões e limites em 09. O aceite desta edição não equivale à implementação das propostas. D-1 refere indisponibilidade observada em 24/10; a capacidade atual deve ser revalidada no despacho.
**Pareceres recebidos:** 11 de 12 (mensagens #41540–#41551). Os textos completos estão no resultado de cada mensagem no Messages.
**Pendente:** Dartan (#41542, telas e testes no navegador). A execução falhou porque **a cota do agy (Google) acabou**
("Individual quota reached… Resets in 67h55m", 24/10 21:05). Não é falha do parecer. Ver decisão D-1.

**Como ler:** os problemas foram agrupados por tema. Cada linha diz quem levantou, a análise do
Claude Code e a proposta (**aceitar**, **ajustar** ou **rejeitar**, sempre com motivo). Os itens marcados
**[decisão]** precisam do Marcelo. Os demais seguem a proposta, salvo objeção dele.

## Resumo

| Revisor | Bloqueia | Importante | Melhoria |
|---|---|---|---|
| Porthus (arquitetura) | 4 | 7 | 6 |
| Aramis (backend) | 1 | 4 | 2 |
| Athos (governança) | 2 | 3 | 4 |
| Atlas (planejamento) | 1 | 4 | 3 |
| Daedalus (especificação) | 5 | 5 | 5 |
| Hephaestus (infra) | 2 | 2 | 3 |
| Aegis (segurança) | 2 | 6 | 3 |
| Themis (LGPD) | 3 | 5 | 6 |
| Mnemosyne (memória) | 1 | 3 | 4 |
| Scriba (documentação) | 1 | 5 | 4 |
| Kairos (captação) | 2 | 4 | 4 |

**Conclusão geral:** nenhum revisor contestou a direção. Os problemas convergem em quatro pontos:
1. **o plano tem contradições internas**, porque a especificação da Missão ficou com o modelo antigo;
2. **a regra de validação pode ser contornada no código atual**: tarefa vai a `done` sem execução;
3. **o orquestrador não tem autoridade nem ferramentas** para conduzir de fato uma missão;
4. **as tarefas descrevem o objetivo, mas não a especificação executável** (contratos, schemas, testes).

Os quatro são corrigíveis no próprio plano, antes de implementar.

## Verificações feitas antes de consolidar

| Afirmação | Quem | Resultado |
|---|---|---|
| "Padrão 19 da Foundation não existe" | Scriba #1 | **Falsa.** `44_marcelo/stack/19-PROJECT-STRUCTURE.md` existe. O `find` foi feito em `/root/.hermes/foundation`, que é um link simbólico, sem `-L` |
| "Tarefa sem execução vai a `done` sem evidência" | Porthus #4 | **Verdadeira.** O próprio docstring de `api/routes/task.py` diz: "a task with no executions at all … is unaffected" |
| DbUp, Iris, Soteria no deploy | Hephaestus #1, #2, #7 | **Não se aplica ao ForgeHub.** O ForgeHub usa Alembic. Iris e Soteria são subagentes descritos na Foundation (`14_agents/IRIS.md`, `SOTERIA.md`), não serviços em produção |
| "A política de classificação não existe" | Themis #1 | **Verdadeira, mas esperada.** É a entrega da tarefa C.1, e a C.2 já depende dela. Não é falha do plano; o que a Themis pediu para dentro dela é aceito (tema H) |

## A. Coerência do plano (bloqueia)

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| A1 | Porthus 1, Aramis 3, Atlas 2 | Quatro versões de qual é a primeira missão e onde ela é registrada | **Aceitar.** Primeira missão = **C.0 + C.1** (linha de base da memória e política de classificação), no produto **Ecossistema Foundation**. O plano integrado vira **projeto comum** (não missão) no mesmo produto, para acompanhamento. Corrigir 01, 04 (M0.5), 07 e 09 |
| A2 | Porthus 2 | "Missão = extensão do Projeto" não comporta missão de várias linhas ou produtos (projeto pertence a uma versão de produto) | **Aceitar.** A missão é um **projeto de coordenação** no Ecossistema Foundation, com ligação explícita aos projetos executores (tabela de ligação missão ↔ projetos). Os critérios ligam-se a tarefas de qualquer projeto ligado. A condição "nenhuma tarefa aberta" vale para todos os projetos ligados |
| A3 | Porthus 3 | Quatro fontes de estado da missão (04, spec, "status derivado", `Project.status` e o pipeline) | **Aceitar.** O 04 vale: a missão tem estado próprio, com gates. `Project.status` é derivado dele por um dicionário explícito, e os estágios do pipeline são a visão desses estados, não uma segunda máquina de estados |
| A4 | Porthus (resp. 1), Athos (resp. 2) | `missao-especificacao.md` ficou com o modelo antigo (tabela `missions`, estados, fases próprias) | **Aceitar.** Marcar seção por seção da spec como "vale" ou "substituída por 04/07" |
| A5 | Porthus 11 | Três referências à Q.4, que foi substituída pela Fase T | **Aceitar.** Trocar por T.1/T.2 no 01, no 09 e na Q.5 |
| A6 | Porthus 12 | "M0" é ao mesmo tempo fase e nível de autonomia; duas escalas de autonomia; "Fase 0" na spec colide com a do 07 | **Aceitar.** Níveis da Missão passam a se chamar **N0–N3**, com a relação explícita com A0–A2. A §5 da spec é marcada como substituída pelo 07 |
| A7 | Porthus 13, 14, 15, 16, 17 | Dois mecanismos de documento obrigatório; dois desfechos para `PARTIAL`/`BLOCKED`; regra "só a Missão declara concluído" contradiz linhas sem missão; `mission_id` redundante com `project_id`; 05 desatualizado | **Aceitar todos.** Vale a D.1 (documentos pelo pipeline). `PARTIAL`/`BLOCKED` → tarefa `blocked` com motivo, retorno por reprocesso. Regra reescrita: "num trabalho de missão, só a missão declara concluído". Usar `project_id` e `entity_type="project"`, sem colunas novas. Atualizar o 05 |
| A8 | Mnemosyne 1 | A tabela da Fase C chama de "camadas" o que é ordem de precedência, em conflito com as 4 camadas da Foundation | **Aceitar.** Separar: (A) **4 camadas de armazenamento** (as da Foundation: memória do runtime, Base de Conhecimento, Hindsight, estado operacional); (B) **9 níveis de precedência** para o contexto de execução |

## B. Validação real das entregas (bloqueia)

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| B1 | Porthus 4 (verificado) | Tarefa sem execução vai a `done` sem evidência; `deployed` não passa pela checagem; "verificada" quer dizer só "existe"; auditoria grava `actor="system"` | **Aceitar, na M0 (não na G.5).** Em projeto de missão: `done`/`deployed` exigem a última execução `verified` **e** uma revisão aprovada por membro diferente do executor; bloquear `done` sem execução; gravar no `actor` a identidade da credencial. A saída da Onda 1 depende disso |
| B2 | Porthus 5 | `TaskExecutionReview`, os campos de revisão e carga do membro do projeto e o próprio vocabulário de funções moram em `orchestration.py`, que a R.1 aposentaria | **Aceitar.** A R.1 preserva e move para o domínio de tarefas: `PROJECT_AGENT_ROLES`, `ProjectAgentMembership` (com `can_review`, `can_approve`, `allocation_percent`, `max_concurrent_tasks_override`) e `TaskExecutionReview`. M.1e e G.5 são construídas **sobre** eles |
| B3 | Porthus 6 | Já existe `ScopeItemAcceptanceCriterion`; o que falta é ligar critério a tarefa | **Aceitar.** Não criar segundo modelo de critério. Criar só a ligação critério ↔ tarefa (polimórfica: critério de escopo ou de missão), com estado, quem comprovou e evidência |
| B4 | Porthus 10, Athos 4 | "A baseline autoriza as tarefas dela" não tem mecanismo, nem registro na Foundation | **Aceitar.** A `PlanBaseline` guarda os ids das tarefas e um hash do conteúdo, pelo mesmo padrão do Messages (`approved_content_hash`). O guard de despacho confere. Tarefa nova ou editada depois exige change request. Registro na Foundation (M.1l) antecipado para a M0 |
| B5 | Porthus (regras) | Critério comprovado não volta para aberto se uma tarefa ligada é reaberta | **Aceitar.** Reabertura ou change request numa tarefa ligada devolve o critério a `aberto` |
| B6 | Athos (regra 3) | A consolidação do orquestrador não tem verificador independente | **Aceitar.** Consolidação verificada por um verificador que não é o orquestrador nem o documentador |
| B7 | Daedalus 14, Hephaestus (regra 2), Atlas (regra 2) | Os verificadores de evidência por tipo não estão definidos; na Onda 1 ainda não há CI nem execução remota ligada | **Aceitar.** Validador por tipo (`git`, `file`, `db`, `host_execution`, `browser_session`), cada um com sua regra. **Modo Onda 1:** só `git:`/`file:`/`db:` com revisão independente; os demais tipos valem depois da I.5 e da N.3 |
| B8 | Porthus (regras), Daedalus 13 | Editar o brief ou um critério depois de aprovado não invalida "pronta"; os pré-requisitos não têm onde ser gravados; orçamento e datas não têm campo | **Aceitar.** Hash do brief e dos critérios aprovados (editar volta a `rascunho`); lista de pré-requisitos gravada no plano; orçamento por missão/projeto; datas planejadas obrigatórias em tarefa de missão |

## C. Condução pelo orquestrador (bloqueia)

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| C1 | Athos 1 | O orquestrador não recebe autoridade sobre o projeto | **Aceitar, na M0.** `AuthorityDelegation` automática ao nomear o orquestrador, limitada ao projeto (despachar, reatribuir, escalar, propor change request), revogada no encerramento |
| C2 | Athos 2 | Sem substituto do orquestrador | **Aceitar.** Substituto nomeado na abertura (padrão: Atlas). Vago e 24 h sem atividade do orquestrador → fila de decisões do Marcelo |
| C3 | Athos 3, 5 | Checagens de papéis e do plano não implementadas; sem canal; sem "meu papel e minhas tarefas" pelo MCP | **Aceitar.** Na M0: checagens mínimas no envio do plano (1 orquestrador, código só com externo, verificador ≠ executor) e as ferramentas `mission_get_my_role`/minhas tarefas. O canal da missão (M.1j) fica para a Onda 2 |
| C4 | Athos 6; Porthus (regras) | Reabertura sem regra; cancelamento sem regra para despachos em voo; missão parada sem decisão | **Aceitar.** Reabrir: só o Marcelo ou delegado, com motivo e auditoria. Cancelar: cancela a fila, e execução incerta segue o `confirm_inactive` existente. Sem avanço em N dias → decisão do Marcelo |
| C5 | Porthus (regras) | Aceite por "delegado" é nome livre | **Aceitar.** Delegado = `AuthorityDelegation` com ação `mission.accept` limitada ao projeto |

## D. Especificação executável das tarefas (bloqueia)

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| D1 | Daedalus (geral), Aramis (resp. 1) | As tarefas dizem o quê e o aceite, mas não o como técnico (contratos, schemas, migrations, testes, rollback). Um agente externo teria de inventar requisitos | **Aceitar como regra transversal.** Nenhuma tarefa de implementação é despachada sem uma **especificação de implementação** (padrão 18, §33–34): arquivos, contratos/schemas, migrations, testes, segurança, rollback. Quem escreve: Daedalus (Hermes, sem codar) ou Porthus; quem revisa: o executor e um verificador. Vale a partir da M0.2 |
| D2 | Porthus 7, Atlas (resp. 2) | M0.2 e P.1 constroem as mesmas ferramentas, com donos diferentes; P.1 é grande demais | **Aceitar.** M0.2 = primeira fatia da P.1, um dono só (**Aramis/Codex**, com revisão independente do **Porthus/Claude Code**; são ids distintos). A P.1 vira "o restante da lista da V-b", dividida por ferramenta |
| D3 | Aramis 4, Daedalus 9 | Ferramentas MCP sem contrato (endpoint, schema, autorização, idempotência, erros) | **Aceitar.** `MCP_MISSION_TOOLS_SPEC.md` antes da M0.2, incluindo aprovação da baseline (ou declarar que ela é feita só pela tela) |
| D4 | Daedalus 1–5, Aramis 6 | Fase Q sem especificação: quem cria o branch, nome, ligação PR ↔ tarefa, "área" de código, workflow de CI, gate de produção, segredos | **Aceitar.** Nova tarefa **Q.0 — especificação da entrega de código** (`CI_PIPELINE_SPEC.md` com workflow, jobs, limites de cobertura, varredura de segurança e de segredos; convenção de branch e evidência `git:pr:…`; `code_area` na tarefa; ambientes do GitHub com aprovadores; plano de rollback por projeto). A Q.1–Q.6 dependem dela |
| D5 | Aramis 7 | I.12 e D.11 juntam várias fontes sem contrato de evento, dedupe e fechamento | **Ajustar.** Uma especificação comum de evento operacional (fonte, chave de dedupe, abertura, fechamento, auditoria) antes da I.12; D.11 define como correlaciona documento e código |
| D6 | Daedalus 6, 7, 8, 10, 12 | Registro do "Pedir ao agente", evidência de execução remota, `TaskRequiredSkill`, mapeamento estágio da missão ↔ planning item, modelos da pasta do projeto | **Aceitar.** Cada um entra na especificação da tarefa correspondente (I.2, I.5, I.11, M0.3, D.7). Observação: `TaskRequiredSkill` **já existe** no domínio de tarefas (rota `/tasks/{id}/required-skills`), então a I.11 só faz o matching |

## E. Identidade pelo ForgeVault (bloqueia no desenho)

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| E1 | Aramis 2, 5; Aegis 1, 2, 3, 8; Hephaestus 5 | O desenho (F.1) não define algoritmo, `kid`, rotação, claims, mapeamento por sistema, propagação da revogação, alta disponibilidade, procedimento de emergência e testes de migração | **Aceitar.** A F.1 passa a ter checklist obrigatório: algoritmo (RS256 ou ES256), `kid`, rotação com sobreposição, cache do JWKS; claims padrão (`sub`, `aud`, `env`, `roles`, `scopes`, `mission_id`, `delegation_id`, `jti`); tabela de mapeamento por sistema; revogação (exp curto + lista de revogados por push com polling de reserva); HA e cache; **F.1.1 procedimento de emergência** (break-glass do Marcelo); testes de aceitação (token de teste, de produção, revogado, legado `agt_`) |

## F. Área de teste, entrega e operação

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| F1 | Hephaestus 1 | Banco de teste vago | **Aceitar, ajustado.** Postgres de teste em **container próprio** (porta e volume próprios), migrations por **Alembic** (não DbUp), seed e reset; `dev.sh` e a suíte de testes passam a usá-lo |
| F2 | Hephaestus 2, 7 | Rollback e "homologação" sem definição | **Aceitar, ajustado.** `DEPLOY.md` com seção de rollback padronizada; rollback testado na área de teste antes do gate; homologação = estágio do pipeline (deploy na área de teste, testes E2E/fumaça, aprovação). Feature flags e componentes como Iris/Soteria **só se existirem de fato**; não depender de subagente descrito mas não implantado |
| F3 | Hephaestus 3 | Incidente sem severidade, SLA e runbook | **Aceitar.** Severidades P1–P4 com SLA, runbook padrão, ligação com a saúde da missão e as Atividades. **Rejeitar** o envio por `send_client_email` (fila de e-mail de **cliente**, com aprovação): alertas internos vão por Telegram e notificação |
| F4 | Hephaestus 4 | G.12 sem inventário nem ordem de restauração | **Aceitar.** Inventário do que o backup cobre, script de restauração ordenado, teste na área de teste, RTO/RPO por camada |
| F5 | Hephaestus 6 | Máquina Windows de teste sem definição | **[decisão D-4]** VM no próprio VPS ou máquina externa |
| F6 | Porthus 8, Atlas 3 | "A missão roda no teste" não está definido; dependências de T não declaradas | **Aceitar.** O **registro** da missão fica sempre na produção. "Teste primeiro" vale **por tarefa** que muda sistema (código, manutenção, navegador), declarado como ambiente da tarefa. Essas tarefas dependem de T.2. A primeira missão (C.0+C.1) não muda sistema e não depende da área de teste |

## G. Segurança

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| G1 | Aegis 4, 9 | Política de rede do navegador de internet sem mecanismo | **Aceitar.** Saída negada por padrão, lista de domínios resolvida no host, DNS controlado, bloqueio de endereços de metadados, proxy que registra, sanitização do HTML antes do agente, limite por domínio, teste de fuga no aceite (N.1/N.4) |
| G2 | Aegis 5 | Credencial injetada no Chromium sem hardening | **Aceitar.** Perfil por sessão, sem extensões, CDP só local, processo isolado, limpeza ao encerrar (N.1/N.6) |
| G3 | Aegis 6 | Execução remota "ok" não prova integridade | **Aceitar.** Evidência inclui código de retorno, estado dos serviços tocados e hash dos arquivos alterados; o verificador confere a evidência, não só o código de saída (I.5) |
| G4 | Aegis 7 | Segredos por projeto sem ciclo de vida nem RBAC | **Aceitar.** Escopo por projeto e ambiente, leitura de produção só por `developer`/`release_manager`/`coordinator`, rotação a cada 90 dias e ao remover membro, auditoria (Q.6/F.3) |
| G5 | Aegis 10 | Checks do Darckware não listados | **Aceitar.** Lista mínima na E.8: TLS, cabeçalhos de segurança, limite de requisições em `/chat`, `/lead` e `/login`, sem painel exposto, páginas de erro sem stack, varredura de dependências, injeção de prompt no chat da Lara |
| G6 | Aegis 11 | Evidência sem prova contra fabricação; sem evidência de segurança obrigatória | **Ajustar.** Missão marcada como sensível exige critério de revisão de segurança (Onda 2). Commits assinados e auditoria com hash encadeado ficam como **melhoria da Onda 3**: alto custo e baixo risco enquanto os executores são agentes próprios |

## H. LGPD

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| H1 | Themis 1, 2, 4, 5, 7, 8 | A política da C.1 precisa de base legal por categoria, análise controlador/operador Maia/Lara, regras de lead e cliente, TTL por classe no Hindsight e transferência internacional (modelos fora do Brasil) | **Aceitar.** O conteúdo da C.1 passa a incluir esses seis pontos. A transferência internacional também gera um item para o projeto **ForgeRouter** (pseudonimizar antes de enviar ao modelo, onde couber) |
| H2 | Themis 3 | Sem fluxo de direitos do titular (acesso, correção, eliminação, portabilidade) | **Aceitar.** Nova tarefa **C.11 — direitos do titular**: canal de recepção, verificação de identidade, busca em todos os sistemas (ForgeHub, Darckware, Hindsight, KB), resposta em 15 dias, auditoria. Prazo: Onda 2 |
| H3 | Themis 6, 12, 13, 14; Themis (regras) | Coleta de dados sem checklist; documentos de cliente sem varredura de dado pessoal; metadados sem campos LGPD; checks LGPD sem catálogo; missão sem DPIA, critério ou seção LGPD | **Aceitar.** Checklist pré-coleta na N.8; varredura de dado pessoal em documento visível ao cliente (D.2/M.1i); campos `lawful_basis` e `retention_until` nos metadados (C.5); catálogo de checks LGPD no Auditor (C.7); na Missão, **condicional**: missão com dado pessoal exige avaliação de impacto, ao menos um critério LGPD e a seção LGPD no dossiê |
| H4 | Themis 11 | Painel de acessos sem registro de acesso a dado pessoal | **Ajustar.** Fica para a F.9 (Onda 3), sobre os sistemas que guardam dado pessoal (Darckware, ForgeHub) |

## I. Memória e contexto

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| I1 | Mnemosyne 2 | O `knowledge_cycle.py` ainda varre toda a base (confirma o risco da C.2) | **Aceitar** a forma proposta: o hook lê só a KB do próprio agente e `shared/approved/`; a busca completa fica só para uso deliberado na linha de comando; teste unitário de isolamento. Porthus confirma um único arquivo real (os perfis apontam para ele) |
| I2 | Mnemosyne 3, 7, 8 | Metadados sem `precedence_level`/`promotion_path`; sem formato de citação; sem visibilidade por papel | **Aceitar.** Campos nos metadados (C.5); citação canônica (`foundation:…`, `kb:…`, `hindsight:<banco>:<id>`, `memory:…`) obrigatória no brief e no contexto de despacho; matriz de visibilidade por papel (executor, verificador, documentador, cliente) na P.4/M.2 |
| I3 | Mnemosyne 4, 5, 6 | C.8 mistura compactação da sessão e `MEMORY.md`; "histórico de versões" da Foundation é o git; C.9 sem exportação definida | **Aceitar.** C.8 dividida (C.8a compactação, C.8b `MEMORY.md`); aba Foundation mostra o histórico git; exportação antes do saneamento e Hindsight incluído no backup testado (G.12) |
| I4 | Mnemosyne (regras) | Missão sem "contexto pronto" na largada, sem registro do contexto enviado e sem encerramento do contexto | **Aceitar.** Largada exige contexto injetável e teste de vazamento verde; a evidência da entrega inclui o registro do contexto recebido; o encerramento exige lições promovidas e contexto temporário limpo (nova seção no dossiê) |

## J. Documentação

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| J1 | Scriba 1 | "Padrão 19 não existe" | **Rejeitar.** Existe (`19-PROJECT-STRUCTURE.md`); veja as verificações acima. Observação válida: o próprio padrão 19 está em `Status: Draft`, então a pasta padrão deve citá-lo como proposta, não como norma aprovada |
| J2 | Scriba 2, 3, 9 | Validação documental sem as seções obrigatórias do padrão 18; sem checagem de links e identificadores; "segredos e nomes internos" sem ferramenta | **Aceitar.** Lista das seções obrigatórias em M.1i/D.11; checagem de links e identificador para documentos críticos; a checagem usa `core/secret_masking.py` + padrões de ids internos (`agt_`, UUIDs) |
| J3 | Scriba 4 | Documentos gerados por IA sem o tratamento do padrão 18 (§90–91) | **Aceitar.** Todo documento gerado por agente traz fontes, escopo, suposições marcadas, desconhecidos e revisão independente antes de aprovado |
| J4 | Scriba 5 | Política de idioma | **[decisão D-5]** Sugestão: seguir o padrão 18 §79 (governança, negócio e brief em pt-BR; especificação técnica, ADR, API e código em inglês) |
| J5 | Scriba 6, 7, 8, 10 | Donos por área documental; revisão periódica; padrão 02 na homologação; mapa assunto → documento | **Aceitar.** Donos por área no contrato do projeto; gatilhos de revisão no Auditor; homologação valida contra o padrão 02 (contraste incluído); `00-INDICE.md` passa a conter o mapa assunto → documento autoritativo (dispensa um segundo arquivo) |
| J6 | Athos 8 | Contrato do projeto e manual fora da lista de documentos aprovados pelo Marcelo | **Aceitar** |

## K. Planejamento

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| K1 | Atlas 1 | "Dependência circular" V-b ↔ P.1 | **Rejeitar o diagnóstico, aceitar a clareza.** Não é circular: a V-b usa as ferramentas que **já existem** e o que falhar vira a lista da P.1. Reescrever o aceite da V-b ("um agente percorre o roteiro com as ferramentas atuais e registra o que falta") |
| K2 | Atlas 4, 5, 7, 8 | Tarefas M.1 sem dono e aceite; C.2 e B.1 com dois donos; P.8/P.9 fora de ordem | **Aceitar.** Colunas **Dono** e **Verificador** separadas em todas as tabelas; M.1a–M.1o com dono e aceite; B.1 dividida (levantar / aprovar); renumerar P |
| K3 | Atlas 6 | O diagrama não mostra a C.2 como dependência crítica da Missão completa | **Aceitar** |
| K4 | Atlas (caminho crítico) | Aramis e Porthus são gargalo em muitas frentes; a cota do agy deixou o Dartan fora por 3 dias | **Aceitar.** Registrar capacidade por agente no plano e distribuir: especificações com Daedalus, parte do backend com Claude Code. A disponibilidade do runtime (cota) entra como pré-requisito nas tarefas de UI |
| K5 | Athos 7 | Objetivos (G.1) só na Onda 3, mas a regra pede objetivo | **Aceitar.** Objetivo **opcional** na Onda 1, com exceção explícita registrada |
| K6 | Athos 9 | Produto sem dono | **[decisão D-6]** Dono por produto. Sugestão: Ecossistema Foundation → Athos; ForgeHub → Daedalus; ForgeRouter → Atlas; ForgeVault → Aegis; Darckware → Kairos; Serviços de Manutenção → Hephaestus. A proposta do Athos (ForgeHub → Aramis) foi ajustada porque Aramis é executor de código, e dono de produto não deve ser quem implementa |

## L. Captação e crescimento

| # | Origem | Problema | Análise e proposta |
|---|---|---|---|
| L1 | Kairos 1, 5 | Funil sem métricas além do topo (CAC, LTV, taxa de conversão por etapa, valor de pipeline qualificado, atribuição por canal) | **Aceitar, ajustado.** A E.4 passa a ter estágios (visitante → lead → lead qualificado → proposta → cliente), conversão por estágio, **valor de pipeline qualificado** e origem do lead (campos UTM). CAC e LTV entram quando houver custo de mídia e histórico de receita |
| L2 | Kairos 8; Kairos (regras) | Critérios de aceite e validação para missões comerciais (resultado, não só entrega; janela de medição) | **Aceitar.** Modelos de critérios por tipo de missão (técnica, marketing, infraestrutura, documentação); missões de resultado têm **janela de medição** antes de "comprovado" |
| L3 | Kairos 2, 3, 4, 6, 7, 9, 10 | SDR e prospecção ativa, motor de conteúdo e SEO, inteligência competitiva, operação de redes sociais, programa de parceiros, painel de marketing para cliente, guia de marca corporativo | **Fora do escopo congelado.** São propostas de negócio, não lacunas do plano. Viram **itens do projeto do plano** (Incubação) para futuras missões da linha "Marketing e captação". Ponto de atenção registrado: a regra "a Lara não contata cliente por rotina" impede prospecção ativa; isso só muda por decisão do Marcelo (**[decisão D-7]**) |
| L4 | Kairos (regras) | Papel `commercial_validator` | **[decisão D-8]** Acrescentar uma função ao vocabulário único (ex.: `growth`) ou usar `reviewer` com o Kairos como verificador nas missões comerciais |

## Decisões para o Marcelo

| # | Decisão | Proposta |
|---|---|---|
| D-1 | Parecer do Dartan (cota do agy esgotada até ~27/10 17h) | Não esperar: o Porthus revisa também a camada de telas e testes no navegador, e o Dartan revisa quando a cota voltar, sem bloquear |
| D-2 | Primeira missão (A1) | C.0 + C.1 no produto Ecossistema Foundation; o plano integrado como projeto comum |
| D-3 | Missão de vários projetos (A2) | Missão = projeto de coordenação ligado aos projetos executores |
| D-4 | Máquina Windows de teste (F5) | VM no VPS se houver recurso; senão uma estação dedicada no Tailscale |
| D-5 | Idioma dos documentos (J4) | Padrão 18 §79 |
| D-6 | Dono de cada produto (K6) | Tabela em K6 |
| D-7 | Prospecção ativa pela Lara (L3) | Manter a regra atual (sem contato por rotina) até uma missão comercial própria propor e o Marcelo aprovar |
| D-8 | Validador comercial (L4) | Usar `reviewer` com o Kairos nas missões comerciais; nova função só se faltar |

## Documentos que os revisores não viram

Escritos depois do envio das tarefas, portanto fora desta revisão:
- críticas de entrega e dossiê de validação (04, seções 4 e 5; modelos);
- abertura de um novo projeto e termo de abertura (03; modelo);
- pausar, continuar e várias missões (04, seção 6).

Alguns pareceres tocam neles indiretamente: Hephaestus e Themis leram os modelos de crítica e de
dossiê, e B6, I4 e H3 já pedem ajustes no dossiê. Proposta: a rodada cruzada (0.14) os inclui
explicitamente.

## Próximos passos (Fase 0)

1. **0.14 — rodada cruzada:** Porthus e Athos leem este consolidado e apontam contradições entre as
   propostas. Com a D-1 aceita, o Porthus também revisa a camada de telas.
2. **0.15 — decisão do Marcelo** sobre D-1 a D-8 e eventuais objeções.
3. **Aplicação:** os documentos do plano são atualizados num único commit, citando o item deste
   consolidado (ex.: "A1", "B4").
4. Só então começa a Onda 1.
