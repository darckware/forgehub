# Planejamento: recuperação e gestão de tarefas dos agentes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** permitir que Marcelo identifique e resolva tarefas com falha e incubações na tela Pessoal, preservando histórico e evitando execuções duplicadas.

**Architecture:** criar a aba “Tarefas dos agentes” em Pessoal usando os registros e serviços de Messages. Centralizar as validações das ações no backend para que Pessoal, Messages e MCP respeitem as mesmas regras. A gestão de tarefas de projeto continua no domínio `project_tasks`, com vínculo visível quando existir.

**Tech Stack:** FastAPI, SQLAlchemy assíncrono, PostgreSQL/schema `company`, React, TypeScript, TanStack Query, Vitest e pytest.

**Spec:** requisitos de Marcelo nesta conversa em 19/10/2026: analisar falhas e incubação e planejar uma aba em Pessoal para arquivar, excluir ou executar. Este documento apresenta a proposta de comportamento e o plano de implementação para revisão; implementação e tratamento dos registros existentes são etapas posteriores.

## Diagnóstico confirmado

Consulta somente de leitura em `company.agent_demands`, no banco `forgehub` do container `forgehub_postgres`, em 19/10/2026:

| Situação | Quantidade |
| --- | ---: |
| Falhas não arquivadas | 27 |
| Resultado incerto, exigindo reconciliação | 11 |
| Bridge temporariamente indisponível | 7 |
| Execução terminou como `failed` | 4 |
| Execução terminou como `stale` | 3 |
| Execução terminou como `timed_out` | 1 |
| Falha sem mensagem de erro | 1 |
| Falhas não arquivadas com três ou mais tentativas | 7 |
| Incubações não arquivadas | 12 |
| Incubações não arquivadas com prazo vencido | 12 |
| Arquivadas ainda marcadas como execução ativa | 0 |

As sete falhas com tentativas esgotadas são um recorte das 27, e não um grupo adicional. As contagens representam a consulta, podendo mudar antes da execução do plano.

O código já oferece timeout de 45 minutos, limite de três tentativas, retentativa de determinadas falhas de conexão, arquivamento, exclusão e reprocessamento. A maturação de uma incubação muda seu estado para `decision_pending` e a recoloca na fila consultada pelo agente; não executa o trabalho.

### Lacunas observadas no código

- Pessoal possui Tarefas, Agenda, Anotações, Demandas, Contatos, Maia e Sugestões, mas não uma aba de acompanhamento das execuções dos agentes.
- O dispatch manual chama `_execute_dispatch` sem aplicar nessa rota os limites de concorrência usados pelo agendador. Também não apresenta ali uma barreira geral contra iniciar novamente uma execução ativa.
- O reprocessamento recusa resultado incerto e tentativas esgotadas. Falta uma ação de recuperação para o operador resolver esses casos com evidência; insistir no mesmo botão não resolve.
- A rota de exclusão remove o registro e anexos sem uma validação explícita de execução ativa ou resultado incerto.
- O sweep de maturação não filtra `status != 'archived'`. Uma incubação arquivada ainda em `incubating` pode gerar uma nova pendência ao vencer.
- Os hooks de Messages inspecionados não expõem ações próprias de receber e descartar incubação. As rotas existentes de decisão exigem identidade do agente e token do bridge; a interface humana precisa de um caminho autenticado próprio.

Essas constatações não demonstram a causa histórica de cada falha. O diagnóstico individual precisa consultar o run e sua evidência, principalmente nas 11 execuções incertas. Logs técnicos e saídas brutas não devem ser publicados no documento.

## Proposta funcional

Nova aba **Pessoal → Tarefas dos agentes**, com filtros **Precisam de atenção**, **Incubação**, **Na fila**, **Em execução**, **Concluídas** e **Arquivadas**. A entrada padrão é Precisam de atenção: falhas e incubações vencidas. Uma mesma pendência pode aparecer no filtro específico e no consolidado, sempre com o mesmo identificador.

Cada linha mostra número, assunto, agente responsável, tipo, situação, idade/prazo, tentativas e um resumo do erro. O detalhe mostra conteúdo, resultado, vínculo com tarefa de projeto e histórico das ações. Busca por número/assunto e filtros por agente e período devem usar paginação no servidor.

| Situação | Ações propostas |
| --- | --- |
| Incubação | Promover e executar, adiar decisão, descartar com motivo ou arquivar |
| Falha recuperável com orçamento disponível | Ver erro, corrigir dados necessários, tentar novamente ou arquivar |
| Resultado incerto | Reconciliar execução; bloquear nova tentativa e exclusão até resolver a incerteza |
| Tentativas esgotadas | Registrar correção e autorizar novo ciclo de tentativas, preservando o total histórico; ou arquivar |
| Na fila | Executar agora, reagendar ou arquivar antes de iniciar |
| Em execução | Acompanhar resultado; impedir novo disparo, exclusão e arquivamento enquanto ativa |
| Concluída | Ver resultado, arquivar ou excluir mediante confirmação e regras de retenção |
| Arquivada | Ver histórico, restaurar sem executar automaticamente ou excluir quando permitido |

“Executar agora” coloca a tarefa na fila com prioridade temporal imediata e informa que ela pode aguardar capacidade. Incubação só se torna executável após promoção explícita, com remetente, responsável e diretório de trabalho válidos.

Arquivar preserva o registro e o remove das filas operacionais. Descartar encerra uma incubação com motivo e a arquiva. Adiar exige uma nova data futura. Excluir é permanente, exige confirmação com identificação do item e não exclui a tarefa de projeto vinculada. Mensagens de validação técnica devem ser arquivadas, conforme a regra operacional existente.

## Global Constraints

- Fonte operacional única: `company.agent_demands`; não copiar tarefas para as tabelas pessoais.
- APIs autenticadas: Marcelo usa a sessão da aplicação; agentes continuam sujeitos à identidade e às permissões existentes.
- Nenhuma credencial do bridge chega ao navegador.
- Uma execução por agente e respeito ao limite global em todos os caminhos de início.
- Nenhuma execução automática após restaurar um item arquivado.
- Nenhum reenvio enquanto uma execução anterior puder continuar ativa.
- Preservar o total de tentativas e o histórico de correções, decisões e resultados.
- Ações em lote retornam resultado por item; uma falha não pode ser apresentada como sucesso do lote inteiro.
- Textos traduzidos nos idiomas já suportados e chamadas HTTP pelo cliente central de `frontend/src/lib/api.ts`.
- As contagens acima não autorizam limpar, excluir ou reexecutar registros existentes.

## Review Focus

1. Dois cliques ou chamadas simultâneas para o mesmo item devem produzir no máximo um início externo.
2. Timeout/404 do bridge não prova que o trabalho não executou; a interface deve manter a incerteza explícita.
3. Incubação arquivada não amadurece nem reaparece na fila do agente.
4. Restaurar um registro com agendamento antigo não inicia execução automaticamente.
5. Lote com itens ativos, resolvidos e desatualizados precisa identificar recusas individualmente.

## Etapa 1 — proteger o início, arquivamento e exclusão (P0)

**Arquivos:** `backend/app/api/routes/demand.py`, `backend/app/core/agent_runs.py`, `backend/app/core/dispatch_signal.py`, `backend/app/tests/test_messages_execution_guards.py`; criar `backend/app/tests/test_demand_operator_actions.py`.

**Interface:** manter `POST /api/v1/demands/{id}/dispatch` e `POST /api/v1/demands/{id}:reprocess`; as ações humanas de execução passam pela fila e pelo mesmo controle de concorrência do agendador. A resposta continua usando `DemandOut`, inclusive quando a tarefa aguarda capacidade.

- [ ] Criar regressões para dispatch concorrente do mesmo item, agente ocupado e capacidade global esgotada; comprovar no máximo um início externo e permanência na fila quando sem capacidade.
- [ ] Reservar atomicamente os itens antes do início externo e revisar todos os caminhos que podem chamar o runner. Definir a mesma proteção entre dispatch manual e worker, inclusive após reinício.
- [ ] Recusar exclusão e arquivamento de execução ativa; recusar exclusão de resultado incerto. Validar também atualizações genéricas que alteram `status`, para impedir contorno pela API de edição.
- [ ] Na restauração, limpar o agendamento operacional e exigir nova autorização para executar; testar que um agendamento vencido não basta para iniciar.
- [ ] Filtrar arquivadas no sweep de maturação e testar que nenhuma notificação ou pendência é criada para elas.
- [ ] Executar os testes de regressão e os testes existentes de guards antes de integrar.

**Aceite:** nenhuma ação humana contorna a fila, duplica trabalho ou apaga uma execução ainda não resolvida.

## Etapa 2 — reconciliar falhas e preservar tentativas (P0)

**Arquivos:** `backend/app/api/routes/demand.py`, `backend/app/api/schemas/demand.py`, `backend/app/db/models/demand.py`; criar `backend/app/core/demand_recovery.py` e `backend/app/tests/test_demand_recovery.py`. Caso os modelos existentes não suportem histórico durável por tentativa, adicionar uma migração em `backend/alembic/versions/`.

**Interfaces propostas:**

- `POST /api/v1/demands/{id}/reconcile`: consulta o `agent_run_id` registrado; devolve estado atualizado e evidência disponível, sem iniciar execução.
- `POST /api/v1/demands/{id}/authorize-retry`: recebe motivo da correção e referência de evidência; autoriza novo ciclo somente após resolver incerteza e confirmar ausência de run ativo. Não dispara o trabalho por si só.
- Histórico durável: ator, ação, data, run, motivo, referência de evidência, total histórico de tentativas e tentativas do ciclo atual. Reaproveitar os mecanismos existentes de auditoria quando atenderem a esses campos.

- [ ] Testar reconciliação de run ativo, concluído, falho e ausente; um 404 mantém a situação incerta, sem liberar reenvio automático.
- [ ] Implementar reconciliação usando o runner existente. Se faltarem evidências, permitir registrar a investigação, mantendo o bloqueio até confirmação operacional da ausência de execução ativa.
- [ ] Introduzir categoria estruturada de falha e estado explícito de recuperação; preservar os textos atuais para leitura e migrar registros reconhecíveis sem inferir resolução.
- [ ] Testar autorização após correção: conservar total histórico, renovar apenas o orçamento do ciclo e registrar ator/motivo/evidência. Manter três tentativas por ciclo como limite inicial.
- [ ] Para falha sem texto, mostrar uma mensagem orientando inspeção do run; não inventar uma causa.
- [ ] Executar os testes de recuperação, guards e reprocessamento existentes.

**Aceite:** cada falha explica o próximo passo; as 11 execuções incertas podem ser investigadas e resolvidas sem reenvio cego, e o limite de tentativas não apaga o histórico.

## Etapa 3 — decisões humanas de incubação (P1)

**Arquivos:** `backend/app/api/routes/demand.py`, `backend/app/api/schemas/demand.py`, `backend/app/core/demand_recovery.py`; criar `backend/app/tests/test_demand_incubation_operator.py`.

**Interface proposta:** `POST /api/v1/demands/{id}/incubation-decision`, autenticada pela sessão, com `action` igual a `promote_and_queue`, `postpone` ou `drop`. Promoção recebe remetente, destino e diretório quando faltarem; adiamento recebe `matures_at`; descarte recebe `reason` obrigatório.

- [ ] Testar promoção válida, dados faltantes, descarte sem motivo, adiamento no passado e decisão concorrente sobre item já resolvido.
- [ ] Compartilhar regras de domínio com as rotas de agente, mantendo a autenticação e a autorização próprias de cada entrada.
- [ ] Promover e enfileirar na mesma transação; acordar o worker somente após commit. Nunca iniciar o runner diretamente nessa rota.
- [ ] Ao adiar, retornar para `incubating`, atualizar o prazo e permitir uma nova notificação na próxima maturação, sem duplicá-la no mesmo ciclo. Rever a chave atual `incubation-due:{id}` para comportar ciclos.
- [ ] Registrar responsável, decisão e motivo. Arquivar uma incubação deve preservá-la sem transformar arquivamento em descarte implícito.
- [ ] Executar os testes de decisões e maturação existentes e novos.

**Aceite:** cada uma das 12 incubações vencidas oferece uma decisão humana explícita; só a promoção autoriza execução.

## Etapa 4 — aba em Pessoal e ações consistentes (P1)

**Arquivos:** `frontend/src/pages/personal/index.tsx`, `frontend/src/hooks/useDemands.ts`, `backend/app/api/routes/demand.py`, `backend/app/api/schemas/demand.py`; criar `frontend/src/pages/personal/AgentTasksTab.tsx`, `frontend/src/hooks/useAgentTasksViewModel.ts` e testes correspondentes. Atualizar `frontend/src/i18n/locales/*/personal.json` e os componentes de Messages que exibem ações de recuperação.

**Interfaces propostas:** `GET /api/v1/demands/agent-work` com `view`, `agent_id`, `search`, período, `page` e `page_size`; resposta `{items, total, counts}`. Contagens seguem os mesmos filtros de agente, busca e período; `view` seleciona a lista. Registrar essa rota antes de `/{demand_id}`.

Cada item inclui `allowed_actions` e motivos de bloqueio calculados no backend. A execução de uma ação sempre revalida as condições atuais; a lista não funciona como autorização permanente.

- [ ] Implementar a consulta paginada sem alterar o contrato da listagem atual de Messages. Testar classificação, sobreposição no filtro de atenção e exclusão de arquivadas dos filtros ativos.
- [ ] Adicionar a aba e os filtros descritos, com contagens, responsável, erro resumido e detalhe navegável para Messages e tarefa de projeto.
- [ ] Reaproveitar o cliente de API e hooks existentes; invalidar consultas de Pessoal, Messages e atividade após cada alteração.
- [ ] Implementar confirmações específicas, motivo obrigatório quando previsto e bloqueios acompanhados de explicação visível.
- [ ] Implementar seleção e ações em lote apenas sobre IDs selecionados, mostrando sucessos e recusas por item. Exclusão fica fora da primeira versão dos lotes.
- [ ] Testar estados vazio, carregando, erro de consulta, tarefa alterada por outro operador e lote parcialmente recusado; verificar navegação por teclado e layout móvel.
- [ ] Rodar os testes frontend afetados e `cd frontend && npm run build`.

**Aceite:** Marcelo consegue identificar e tratar falhas e incubações pela aba, com as mesmas regras usadas em Messages.

## Etapa 5 — validação integrada e tratamento do passivo (P2)

- [ ] Executar testes backend afetados e `cd backend && ruff check app`; executar testes frontend afetados e build. Registrar comandos e resultados reais.
- [ ] Validar com registros de teste: incubar → vencer → decidir → enfileirar → executar → concluir → arquivar → restaurar sem disparo.
- [ ] Validar falha → reconciliar → corrigir → autorizar novo ciclo → tentar novamente; simular indisponibilidade e resultado incerto sem executar trabalho externo real.
- [ ] Preparar relatório dos registros existentes por ID, agente, categoria e ação recomendada. Revisar primeiro os 11 casos incertos, depois as falhas com tentativas esgotadas e as demais falhas.
- [ ] Apresentar as 12 incubações para decisão de promover, adiar, descartar ou arquivar. Vencimento sozinho não autoriza execução nem exclusão.
- [ ] Após a aprovação das ações concretas sobre o passivo, aplicá-las com trilha de auditoria e conferir as contagens finais.
- [ ] Atualizar a documentação operacional com as novas ações, restrições e procedimento para futuras falhas.

## Ordem de entrega e limites

Sequência: **proteções → recuperação → decisões de incubação → aba e ações → validação e passivo**. As etapas 1 a 3 fornecem os contratos que a interface usa; a nova aba deve ser entregue com esses contratos funcionando.

Cancelamento de processo ativo, mudanças no runtime Hermes e reformulação da gestão de projetos ficam fora desta entrega. Caso o runner existente já ofereça cancelamento comprovável, sua exposição pode ser planejada depois; marcar um registro como arquivado não equivale a parar um processo.

Não foram alterados código de aplicação, dados, configurações ou serviços durante este planejamento. A consulta ao banco foi somente de leitura; não foram executados testes de implementação porque as mudanças ainda são propostas.
