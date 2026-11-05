# Organização das decisões e tarefas dos agentes — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar Aprovações Moodle, Incubações e Tarefas dos agentes, tornando explícitas as decisões e o arquivamento de tarefas.

**Architecture:** Manter os registros, identificadores, histórico e mecanismos de autorização existentes. Criar três subabas na área atual de trabalho dos agentes, com consultas e contagens por grupo no servidor. Reutilizar o fluxo exclusivo Moodle e o endpoint de decisões de demandas; a organização visual não cria autorização para executar.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, React, TypeScript, TanStack Query, React Router e react-i18next.

**Spec:** A especificação funcional está nas seções abaixo, baseada na conversa de 05/11/2026 e no código consultado. Este documento é uma proposta para revisão, sem autorização implícita para implantação ou execução das tarefas listadas.

## Requisitos e decisões

Marcelo solicitou planejar a divisão em três grupos e incluir botão de arquivamento nas tarefas. Também autorizou arquivar tarefas antigas; o conjunto exato ainda depende da definição de “antigas” e da conferência do estado atual. Nenhum registro deve ser arquivado apenas por ter aparecido numa captura de tela.

Proposta de navegação: manter a entrada atual **Tarefas dos agentes** em Pessoal e acrescentar três subabas:

| Subaba | Conteúdo | Decisão principal |
|---|---|---|
| Aprovações Moodle | Solicitações registradas no fluxo exclusivo de autorização Moodle | Aprovar operação / Recusar |
| Incubações | Demandas ainda em incubação, inclusive as que aguardam decisão ou estão arquivadas | Transformar em tarefa / Adiar decisão / Descartar |
| Tarefas dos agentes | Trabalhos executáveis e seu acompanhamento no ForgeHub | Aprovar e liberar / Acompanhar / Revisar conclusão / Arquivar |

Manter “Aprovações Moodle”: o módulo não administra toda a plataforma Moodle. Manter “Tarefas dos agentes”: distingue esses trabalhos das tarefas pessoais existentes na aba Tarefas.

Abordagens consideradas: apenas adicionar um filtro mantém decisões diferentes na mesma superfície; três páginas independentes aumentam a dispersão. Recomenda-se três subabas na área atual, com estado preservado na URL e links entre registros relacionados. A escolha das subabas é proposta de implementação, sujeita à revisão do plano.

## Situação atual verificada

- `AgentTasksTab.tsx` reúne o painel Moodle, a tabela de demandas, aprovações de conclusão e perguntas bloqueantes.
- `useAgentTasksViewModel.ts` consulta todas essas fontes no mesmo fluxo. Perguntas e aprovações de conclusão não compõem a contagem da tabela; hoje o número de atenção não representa tudo que a página exibe.
- `demand_management.py` calcula filtros e contagens sem separar esses três grupos.
- `demand_workflow.py` já converte uma incubação em tarefa ao receber `approve`, valida contexto de execução e registra auditoria. Não falta uma operação de promoção: falta clareza na apresentação.
- `work_item()` pode anunciar ações genéricas para uma demanda Moodle que `decide_demand()` recusa depois. A apresentação deve respeitar o mesmo fluxo exclusivo aplicado pelo backend.
- Arquivamento individual e em lote já existem. O individual aparece nos detalhes após abrir a tarefa; o lote aparece após seleção. Melhorar sua visibilidade e feedback, preservando a implementação segura.
- Aprovação de conclusão usa hoje o mesmo texto “Aprovar e liberar” usado para autorizar execução. Corrigir essa diferença de significado.
- O briefing de 23/10 da imagem é uma pergunta bloqueante. Sua idade ou conteúdo não comprovam o estado atual das tarefas Moodle.

## Regras funcionais

### Classificação e contagens

1. Classificar por vínculos e tipos persistidos, nunca por palavras como “Moodle” no assunto.
2. Uma demanda vinculada diretamente a `MoodleApproval.message_id` pertence ao fluxo Aprovações Moodle. Esse vínculo tem precedência sobre `origin_type`.
3. Sem vínculo direto Moodle, `origin_type=incubation` pertence a Incubações; demais trabalhos executáveis pertencem a Tarefas dos agentes.
4. Uma checagem derivada de uma operação Moodle continua sendo uma tarefa de acompanhamento. Exibir a ligação com sua origem e o que a aprovação autoriza; não apresentá-la como uma nova autorização da operação Moodle.
5. Aplicar a classificação no banco antes da paginação e das contagens. Nunca separar apenas os 25 registros já recebidos pelo navegador.
6. A mesma mensagem não ocupa duas filas de decisão. Vínculos podem aparecer como referências entre grupos, preservando identidades distintas de solicitação, checagem e tarefa.
7. Pendências de conclusão e perguntas bloqueantes ficam em seções nomeadas da subaba Tarefas dos agentes. Manter contagens separadas: “Tarefas que precisam de atenção”, “Conclusões para revisar” e “Perguntas para responder”. Não somar fontes com sobreposição nem mostrar um total parcial como total geral.
8. Contagem indisponível aparece como indisponível, nunca como zero. Desativação do recurso Moodle deve ser distinta de fila vazia.

### Aprovações Moodle

- Reutilizar `MoodleApprovalPanel` e `/api/v1/personal/moodle-approvals`.
- Mostrar operação, resumo, destino/ambiente, executor e detalhes revisáveis antes da decisão, preservando a proteção de dados sensíveis.
- Ações: **Aprovar operação** e **Recusar**. Mostrar **Aprovada — aguardando execução** como feedback quando a resposta confirmar autorização, sem afirmar execução.
- Preservar hashes, expiração, identidade do aprovador e executor, claim e restrições do fluxo. Nunca encaminhar autorização Moodle à decisão genérica de demandas.
- Não acrescentar cancelamento de operações já autorizadas sem uma regra própria de domínio; isso não faz parte desta entrega.

### Incubações

- Estados visíveis: Em incubação, Aguardando decisão, Decisão adiada, quando demonstrável pelo histórico, e Arquivada.
- Botão **Transformar em tarefa** reutiliza a decisão `approve`. A confirmação informa que a promoção autoriza a entrada na fila de execução.
- Se faltarem remetente, executor ou contexto obrigatório, explicar a pendência e oferecer navegação para o local existente de edição. Não exigir que o operador adivinhe a configuração.
- **Adiar decisão** exige uma nova data futura. **Descartar** exige motivo e encerra a incubação, preservando o registro.
- **Arquivar** preserva o registro sem equivaler a descartar ou aprovar. Restaurar não autoriza execução.
- Após promover, retirar o item de Incubações, atualizar contagens e oferecer **Ver tarefa** no grupo de tarefas.

### Tarefas dos agentes

- Distinguir estados: Aguardando autorização, Aguardando resposta, Na fila, Em execução, Falha, Resultado incerto, Processamento concluído e Arquivada.
- **Aprovar e liberar** autoriza a execução. Dependências e capacidade continuam sendo respeitadas.
- Em revisão governada usar **Aprovar conclusão** / **Solicitar revisão**, com motivo quando exigido pelo contrato existente.
- Perguntas bloqueantes vinculadas mostram número, responsável, data, tarefa de origem e ação **Responder**. Perguntas sem vínculo ficam em seção “Perguntas sem tarefa vinculada”, sem inventar relações nem desaparecer da tela.
- Mostrar resumo do pedido e ação **Ver detalhes** na linha, evitando que um título clicável sem indicação seja a única forma de descobrir ações.

### Arquivamento solicitado por Marcelo

- Exibir **Arquivar** diretamente na linha de cada tarefa elegível. Manter a ação nos detalhes quando necessário para consistência.
- Disponibilizar seleção e **Arquivar selecionadas**, com confirmação que enumera itens e informa que o histórico será preservado.
- A seleção representa a página selecionada; não significa todos os resultados de todos os filtros.
- Estados ativos/reservados ou de resultado incerto não podem ser arquivados pelo lote para contornar as proteções existentes. Mostrar o motivo quando a ação estiver bloqueada.
- Após sucesso, retirar da fila ativa e atualizar contagens, seleção e detalhes. Em lote parcial, apresentar sucesso/bloqueio/conflito por item.
- Manter filtro **Arquivadas** dentro de Tarefas e Incubações, e ação **Restaurar sem executar**.
- Não usar “Cancelar” como sinônimo de arquivar. “Cancelar” fecha o diálogo sem alterar o registro; “Descartar” é decisão de incubação; arquivar não cancela uma execução nem comprova conclusão.
- O tratamento dos registros antigos é uma operação separada da implantação: inventariar, definir escopo, executar pelo fluxo autorizado e guardar relação de IDs e resultados. Preservar histórico, datas, autorizações, resultados e tentativas. Não excluir nem marcar concluída uma tarefa para limpar a tela.

## Global Constraints

- Preservar aprovação por conteúdo, deduplicação, dependências, limites de execução e reconciliação.
- Não alterar plugin Moodle, MCP Moodle, skills dos perfis ou configuração do gateway nesta demanda.
- Sem migração destrutiva, classificação por título, aprovação em lote de tarefas antigas ou limpeza automática baseada apenas em idade.
- Respeitar `DESIGN.md`, `UX-CONTRACT.md`, os componentes existentes e as traduções pt-BR/en/es.
- Histórico e arquivadas continuam acessíveis; restauração exige nova autorização antes de execução quando aplicável.
- Revalidar estado e permissões no servidor; `allowed_actions` ajuda a interface e não substitui a proteção da mutação.
- O checkout contém alterações de outro trabalho em `ops/` e documentação operacional. Não incluí-las nesta entrega. Criar isolamento antes da implementação e rever os arquivos atuais, pois podem mudar após este plano.

## Review Focus

- Solicitação Moodle ou checagem com assunto semelhante: vínculo real define grupo e aprovação correta.
- Navegação entre grupos com filtros, paginação ou resposta de busca atrasada: seleção não pode afetar outro conjunto.
- Decisão concorrente ou registro alterado: preservar proteção de versão/hash e exigir atualização.
- Tarefa promovida, arquivada ou restaurada: atualizar filas e contagens sem execução duplicada.
- Pergunta antiga sem vínculo e falha parcial de uma fonte: manter visibilidade e ações honestas.

## Arquivos e limites

Modificar:
- `backend/app/core/demand_management.py`: classificação e consulta por grupo; ações compatíveis com o domínio.
- `backend/app/api/routes/demand.py`: parâmetro de agrupamento validado e compatível com consumidores atuais.
- `frontend/src/hooks/useDemands.ts`: tipos e filtros da consulta.
- `frontend/src/hooks/useAgentTasksViewModel.ts`: estado por grupo, ações, seleção e invalidação.
- `frontend/src/pages/personal/AgentTasksTab.tsx`: composição das três subabas.
- `frontend/src/pages/personal/MoodleApprovalPanel.tsx`: rótulos e estado do recurso, sem alterar autorização.
- `frontend/src/i18n/locales/{pt-BR,en,es}/personal.json`: linguagem de cada fluxo.
- `DESIGN.md` e `UX-CONTRACT.md`: registrar o comportamento aprovado após a implementação.

Criar componentes focados no diretório `frontend/src/pages/personal/` se a composição exigir: `AgentWorkGroups.tsx`, `AgentWorkList.tsx` e `AgentWorkDecisions.tsx`. Extrair apenas responsabilidades tocadas pelo trabalho.

Testes existentes a estender:
- `backend/app/tests/test_demand_management.py` e `test_demand_workflow.py`.
- `frontend/src/pages/personal/AgentTasksTab.test.tsx` e `MoodleApprovalPanel.test.tsx`.

## Etapas de implementação

### 1. Separar conjuntos no servidor

**Interface:** adicionar `group=all|tasks|incubation` a `GET /api/v1/demands/agent-work`, mantendo `all` como padrão para compatibilidade. A interface nova sempre informa `tasks` ou `incubation`; Moodle usa seu endpoint próprio. Em ambos os grupos explícitos, excluir vínculos diretos Moodle antes de contar e paginar.

- [ ] Cobrir classificação por vínculo, incubação com aprovação pendente, arquivadas e assuntos enganosos, com mais de uma página de resultados.
- [ ] Acrescentar validação do parâmetro no endpoint e filtragem na consulta, nas contagens e nos contextos disponíveis.
- [ ] Alinhar `allowed_actions` aos bloqueios do fluxo Moodle, sem afrouxar `decide_demand()`.
- [ ] Verificar compatibilidade de chamadas sem `group` e negar valores desconhecidos.
- [ ] Executar testes focados e revisar o diff antes de concluir esta etapa.

### 2. Criar as três subabas

**Interface:** preservar `tab=agent-work` e usar `workGroup=moodle|incubation|tasks`. Padrão proposto: `tasks`. Persistir situação e busca por grupo; ao mudar grupo limpar seleção e detalhes incompatíveis. Links antigos devem continuar abrindo a área e preservar o acesso à mensagem referenciada.

- [ ] Cobrir alternância de grupos, histórico voltar/avançar, URL direta e seleção após troca de filtro.
- [ ] Mostrar somente o painel, listas e decisões pertinentes ao grupo ativo.
- [ ] Separar contagens da tabela, de revisões de conclusão e de perguntas; não fabricar um total agregado.
- [ ] Manter dados anteriores estáveis durante atualização sem exibi-los como resultados de outro grupo; tratar carregamento, falha, recurso desativado, vazio e busca sem resultado separadamente.
- [ ] Confirmar que nenhuma demanda ligada diretamente a Moodle ganha uma decisão genérica.

### 3. Tornar decisões compreensíveis

**Interface:** manter ações do backend (`approve`, `reject`, `postpone`, `drop`) e variar os textos por contexto. Revisão de conclusão mantém seu endpoint governado existente.

- [ ] Cobrir promoção de incubação e navegação para a tarefa criada, com motivo explicativo se contexto estiver incompleto.
- [ ] Aplicar os rótulos distintos definidos neste documento e confirmar efeito antes da mutação.
- [ ] Mostrar pergunta ligada à tarefa e seção para perguntas sem vínculo, incluindo itens antigos.
- [ ] Preservar os comentários e exigências do endpoint governado ao trocar seu texto para Aprovar conclusão / Solicitar revisão.
- [ ] Cobrir duplo clique, alteração concorrente e dependência ainda pendente: aprovação não pode ser apresentada como execução concluída.

### 4. Expor arquivamento individual e em lote

**Interface:** reutilizar `POST /api/v1/demands/{id}/decision` com `archive|restore` e `POST /api/v1/demands/agent-work/bulk`, incluindo a versão esperada de cada item.

- [ ] Cobrir Arquivar na linha, confirmação, cancelamento do diálogo e preservação do conteúdo/histórico.
- [ ] Cobrir bloqueios para execução ativa e incerta, visíveis na interface e exigidos pelo servidor.
- [ ] Cobrir lote parcial com registro alterado ou bloqueado sem perder os sucessos confirmados.
- [ ] Cobrir filtro Arquivadas e Restaurar sem executar, sem disparo automático ou reutilização indevida de aprovação.
- [ ] Conferir invalidação das contagens e a remoção do item dos detalhes após arquivamento.

### 5. Conferir entrega e tratar passivo autorizado

- [ ] Executar os testes backend focados com a configuração de banco descartável do projeto; não apontar testes para banco de produção.
- [ ] Executar testes frontend focados e `npm run build` no frontend.
- [ ] Exercitar no navegador as três subabas: teclado, celular, carregamento, erro, vazio, promoção, aprovação, pergunta e arquivamento/restauração.
- [ ] Atualizar contratos de UX com os fluxos efetivamente implementados e registrar evidências.
- [ ] Antes de arquivar antigos, definir o conjunto e registrar número/ID, motivo e estado atual; distinguir perguntas bloqueantes de tarefas, pois arquivar uma demanda não responde uma pergunta.
- [ ] Aplicar o arquivamento autorizado apenas a itens elegíveis, guardando resultados individuais. Reconfirmar a fila e os IDs arquivados por leitura.
- [ ] Revisar e implantar pelo procedimento do projeto; a publicação não inclui reiniciar o gateway Hermes.

## Critérios de aceite

- Marcelo consegue identificar qual dos três grupos contém cada decisão sem conhecer detalhes técnicos do sistema.
- Cada tarefa elegível possui botão visível **Arquivar**, e a seleção permite **Arquivar selecionadas**.
- Incubações têm decisões explícitas e promoção verificável, sem iniciar execução por mero acesso à tela.
- Aprovar operação, autorizar tarefa e aceitar conclusão têm textos e fluxos distintos.
- Nenhuma solicitação Moodle aparece como uma segunda autorização genérica; checagens continuam rastreáveis à origem.
- A lista de tarefas e suas contagens usam o mesmo conjunto paginado; perguntas e revisões exibem contagem própria.
- Arquivar conserva evidências; restaurar não executa; bloqueios de atividade, incerteza e concorrência permanecem eficazes.
- Perguntas antigas continuam visíveis até uma decisão específica; não são respondidas, canceladas ou aprovadas por arquivar uma tarefa relacionada.

## Publicação e retorno

Registrar versão anterior e nova; implantar backend compatível antes da interface que envia o filtro `group`. Não é prevista alteração de esquema. Em caso de falha, retornar código/imagens pela rotina do projeto; arquivamentos feitos pelo operador permanecem fatos auditados e não devem ser revertidos automaticamente pelo rollback de código.

## Estado deste planejamento

Implementação autorizada por Marcelo após a análise de aprovação em lote. Código e testes preparados nas branches isoladas, com revisão independente e verificação em navegador. Evidências e decisões: `2026-11-05-personal-work-groups-execution.md` e `../../runbooks/personal-work-groups-2026-11-05.md`. Implantação, sincronização da skill instalada e arquivamento do passivo não executados. O conjunto exato das tarefas antigas permanece indefinido.
