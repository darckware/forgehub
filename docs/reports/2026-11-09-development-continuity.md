# Continuidade do desenvolvimento: Missões, Messages e Service Factory

Atualizado em 2026-11-09, America/Sao_Paulo. Este é o ponto de retomada da
implementação, incluindo pedidos posteriores ao plano aprovado. Não é um
relatório de conclusão nem uma autorização adicional.

## Objetivo que deve sobreviver à sessão

Amadurecer o fluxo existente para levar demandas autorizadas até entrega
verificada e aceite, com rapidez, qualidade e excelência. Preservar contexto,
responsabilidade, decisões, dependências, evidências e próximo passo durante
esperas, trocas de executor, respostas humanas, falhas e reinícios.

O contexto é parte central do desenvolvimento: o escopo não pode encolher ao que
coube na última sessão ou ao subconjunto que já tem testes passando. Histórico
de conversa ajuda a localizar decisões; o plano e as evidências versionadas
precisam permitir a retomada sem depender dele.

Missão/Task mantém a gestão do trabalho; Messages administra comunicação e
execução; Operação 24x7 supervisiona os mesmos registros; Pessoal recebe as
decisões reais de Marcelo. Service Factory acompanha desenvolvimento de sistemas
e rotinas de todos os serviços aplicáveis. O pedido é amadurecer a solução
existente, preservando seus contratos, e não redesenhá-la.

## Fontes e autorização recuperadas

- Sessão anterior: `01a1bd34-87d4-7960-b66c-7ca14db326c3`, título
  “Verificar última implementação”, iniciada em 08/11. Última atualização útil
  em 09/11 às 23h37. Horários deste documento são locais.
- [Especificação](../superpowers/specs/2026-11-09-mission-messages-maturation.md).
- [Plano em sete tarefas](../superpowers/plans/2026-11-09-mission-messages-maturation.md).
- [Revisão do planejamento](2026-11-09-mission-messages-plan-review.md), que
  registra duas revisões independentes e as correções incorporadas.
- Aprovação de Marcelo em 09/11 às 16h13: “aprovado, pode implementar”.
- Às 16h59: publicar a correção do terminal com commit/push/deploy e depois
  continuar a implementação. Às 22h56: “continue até finalizar”.
- Pedidos adicionais entre 18h51 e 19h17: execução contextual dos codificadores,
  skills, subagentes, aprendizagem, Service Factory, SSH e navegador interno.
- Nesta retomada, Marcelo reforçou que é preciso corrigir a queda, continuar a
  implementação e preservar todo o contexto e o planejamento.

Esses pedidos adicionais estavam registrados na arquitetura e nas análises,
mas não estavam todos decompostos no plano original. Nesta retomada foram
acrescentados os pacotes T8–T13, com dependências, âncoras de código e critérios
de aceite. Continuam pendentes de refinamento/qualificação por etapa e revisão;
a aprovação original antecede esses acréscimos. Não presumir aprovação para
ampliar permissões nem apresentar a extensão como já implementada.

## Matriz de pedidos, cobertura e pendências

“Preparado” significa código encontrado, ainda sujeito a revisão e qualificação.
Contagens históricas de testes não equivalem a uma regressão final atual.

| ID | Pedido e intenção preservada | Onde está coberto | Estado observado / falta para aceite |
|---|---|---|---|
| R01 | Analisar Entrada, Execução e Incubação; evitar repetir trabalho já entregue por outro executor | Plano T1/T2; auditoria de Messages de 08/11 | Parte da triagem já publicada; refinamentos preparados. Provar entrega atual antes de arquivar/reencaminhar, sem apagar tentativas anteriores |
| R02 | Não gerar tarefas sem ação útil ou feedback executável para si mesmo | T1/T6; `d81933c` | Commit existe e não consta no artefato ativo `c86227f`. Qualificar supressão de diagnóstico/feedback obsoleto e preservar tarefas legítimas para si |
| R03 | Botão Analisar e encaminhar e ajuda contextual para decisões humanas em grande volume | T4; `test_message_decision_aid.py` | Enriquecimento contextual preparado; precisa revisão integrada/publicação. Recomendação não toma a decisão nem substitui fatos/autoridade |
| R04 | Tarefa já autorizada sem executor continua em Execução com etiqueta; recuperar quota, executor ocupado ou atribuição posterior | T2/T5; `test_executor_wait_recovery.py` | Reconciliação periódica e varredura justa preparadas, com migration. Qualificar reinício, evento perdido, concorrência, agenda deliberada e autorização atual |
| R05 | Etiquetas compreensíveis por grupo; ícone com legenda lateral direita | T1; `docs/product/messages-labels.md`; `messageLabels.ts` | Código, catálogo e traduções preparados. Fechar navegador desktop/mobile, teclado e revisão; não marcar arquivo/diagnóstico como entrega |
| R06 | Distinguir autorização/decisão humana de espera técnica; encaminhar ao grupo correto de Pessoal | T1/T4/T6; `AgentTasksTab.tsx` | Perguntas bloqueantes expostas nos três grupos. Falta qualificação final de destino, mesmo ID, resposta guardada e retorno do foco |
| R07 | Corrigir cadastro/CRUD e melhorar controles da missão | Histórico do plano e publicação anterior | Plano registra correção publicada. Revalidar na entrega final, distinguindo essa correção do novo ciclo automático |
| R08 | Separar gestão da missão e administração de Messages, com dependências e paralelismo | T3/T5; fluxo operacional | Guards e elegibilidade preparados. Falta revisão completa de política de origem, reservas concorrentes e recursos protegidos |
| R09 | Operação 24x7 agrega e recupera trabalho parado, incluindo planejamento e tarefas independentes | T7; `test_mission_delivery_recovery.py` | Supervisão por tarefa e recuperação de ciclo ausente preparadas. Falta cenário integrado, rotina/serviço e publicação; alerta isolado não significa recuperação |
| R10 | Encerrar somente após todas as obrigações resolvidas e produto/serviço entregue com excelência | T7; `mission_dossier.py`; fluxo operacional | Verificação de bytes do dossiê preparada. Faltam ponta a ponta, revisão independente, integração, versão exata, restauração e aceite governado |
| R11 | Telegram e handoffs mantêm contexto, responsabilidade e autorização; resposta retoma o trabalho correto | T6; `question_continuations.py`; `task_attempts.py` | Continuação canônica, contexto reconstruído, tentativas preservadas, resposta tardia e recibos preparados. Falta revisão de incerteza, consumidor e transporte completo |
| R12 | Comandos dos agentes externos contextualizados por runtime e por objetivo, com skill específica | Análise de runtime; arquitetura §§ Skills e execução | Análise/documentação, não implementação completa. `AgentRunRequest` ainda não declara seleção versionada de capacidades/skill e estratégia de delegação |
| R13 | Codificador planeja, revisa a solução, decompõe, delega executor/revisor/supervisor e trabalha em paralelo quando solicitado | Análise de runtime; T5 como base | Ainda faltam contrato estruturado de execução, limites de filhos, isolamento, agregação de resultados e qualificação por runtime; revisão local não substitui independência exigida |
| R14 | Descobrir e ler skills aplicáveis; aprendizagem verificada para reduzir alucinação | Análise de runtime; auditoria de lacunas | Grants/requisitos existentes não provam conteúdo acessível ou compatibilidade. Falta qualificação de descoberta, versões e ciclo evidência → revisão → proposta de skill → publicação/rollback |
| R15 | Agentes interagem com Service Factory para processo, documentação, acompanhamento, auditoria, entrega e versões | Arquitetura §§ Service Factory; análise de lacunas | Modelos existentes dão parte da base. Faltam provas ponta a ponta de abertura, progresso, documentação e fechamento da versão/serviço real |
| R16 | Service Factory generaliza serviços e desenvolvimento; acompanha rotinas recorrentes | Mesmas fontes; `Product.kind`, `Project.service_line_id`, `ServiceLine` | Não presumir cobertura total pelo catálogo. Qualificar adaptadores de evidência por linha, ocorrência perdida/falha, recuperação e exceção; próxima execução bem-sucedida não apaga falha anterior |
| R17 | Autonomia interna e externa por acesso remoto/SSH já governado | Arquitetura § Remote execution; implementação existente de acesso remoto | Acesso remoto anterior publicado; falta qualificar uso efetivo por cada runtime, grants atuais/expiração/pausa e resultado incerto, sem repetir aprovação já concedida |
| R18 | Usar navegador interno do Workspace para testes, documentação, consultas e entrada de dados | Arquitetura § Workspace browser automation; auditoria de lacunas | Ferramentas existentes não provam acesso efetivo de todos os codificadores. Faltam prova por runtime, exclusão da página compartilhada, intervenção humana e reconciliação de envio incerto |
| R19 | Persistir a sessão de trabalho e recuperá-la entre aparelhos/reinícios | Diagnóstico do terminal desta retomada | Causa nova confirmada: OOM do build derrubou o scope inteiro por `OOMPolicy=stop`. Teste de regressão escrito e visto falhar; correção e aplicação em produção ainda pendentes neste checkpoint |
| R20 | Não perder a ideia nem os pedidos após uma queda/compactação; planejamento é central ao desenvolvimento | Este documento, plano, arquitetura e progresso | Manter matriz, evidência, próximo passo e pendências atualizados em cada checkpoint. Não depender somente de mensagem de chat ou log em `/tmp` |

## Código e produção: onde retomar

- Implementação principal: `/root/project/forgehub/.claude/worktrees/messages-triage`,
  branch `feat/messages-triage`, HEAD `b363568` neste checkpoint.
- Alterações preparadas do backend, frontend, bridge e migrations continuam no
  worktree, em parte sem commit e em parte como arquivos novos. Não usar limpeza,
  reset ou substituição do worktree para “recomeçar”.
- Diretório principal: branch `develop`, mesmo HEAD, com outras alterações de
  plano integrado, Filenest e ECO047. São trabalho separado; não misturá-las
  automaticamente à publicação desta implementação.
- Containers observados nesta retomada: backend e frontend
  `forgehub-*:fh-c86227f`. Bridge ativo em
  `/root/.forgehub/releases/messages-triage-c86227f/forgehub/host-bridge`.
- Último checkpoint de flags documentado: workers comuns ligados,
  `MESSAGE_TRIAGE_ENABLED=false`, `MISSION_CYCLE_ENABLED=false`. Esse registro
  histórico não substitui nova leitura antes de publicar/ativar.
- Manter a autonomia do gestor desabilitada até qualificação dos gates do plano.
  Não habilitar por inferência a partir de testes selecionados ou documentação.

## Verificação interrompida: evidência e limites

- Última atualização da sessão anterior relatou 58 testes selecionados da UI
  passando. Há outras contagens de testes por etapa no
  [progresso de implementação](2026-11-09-maturation-implementation-progress.md).
  São evidências históricas, não resultados reexecutados nesta retomada.
- `/tmp/fh-maturation-backend-full.log`: regressão interrompida, uma marca de
  falha e nenhum resumo final. Recuperar o caso exato; não declarar a suíte verde.
- `/tmp/fh-maturation-ui-build.log`: compilação chegou a renderizar chunks e
  terminou em `Killed`. Não houve build final válido.
- `/tmp/fh-maturation-bridge.log`: sem resumo final. Tratar como inconclusivo.
- `/tmp/forgehub_maturation_browser.py` foi preparado; não há evidência final de
  sua execução neste levantamento.
- Kernel, 09/11 às 23h38m01: OOM matou o processo Node `2053938`. O journal
  registra o scope `run-r66f57f07f1d84e6682eb8cabbb82d639.scope` encerrando com
  `oom-kill` às 23h38m03. Sessões tmux foram recriadas às 23h38m03–04.
  A política consultada no novo scope é `OOMPolicy=stop`. Isso explica esta
  interrupção e é distinto do diagnóstico anterior de seleção de aba no celular.

Logs em `/tmp` servem como pistas. Promover resultados finais e resumos
sanitizados a documentos versionados antes de depender deles para continuidade.
Nunca copiar credenciais ou histórico bruto privado para esses documentos.

## Ordem de continuidade e gates

1. Preservar este mapa e o trabalho existente. Implementar, revisar e publicar
   separadamente a correção pontual da política OOM do terminal; verificar também
   o scope já ativo, para não esperar uma futura criação de tmux. Guardar rollback
   e evidência de que sessões atuais sobreviveram. Não provocar OOM real no host.
2. Recuperar a regressão interrompida; executar build e testes pesados em
   sequência, sem reproduzir a concorrência que esgotou a memória. Diagnosticar a
   falha do backend. Qualificar a UI/teclado nos três grupos de Pessoal.
3. Auditar os sete itens originais contra código, critérios de aceite, migrations
   e resultados atuais. Atualizar checklists com evidência, sem marcar concluído
   por mera existência de arquivos ou por uma atualização de chat.
4. Executar o backlog T8–T12 que preserva R12–R18, refinando cada pacote contra
   arquivos e contratos atuais, dependências, teste que prova a lacuna, critério
   de aceite, revisão e publicação. Análise e arquitetura são entradas desses
   pacotes, não sua implementação. Não inventar nova autoridade, registry,
   orquestrador ou política para preencher informações ausentes.
5. Fechar cancelamento/resultado incerto de runtime, continuidade real de serviço,
   isolamento e evidência, além dos gates originais. O gap de cancelamento está em
   [auditoria do pipeline](2026-11-09-pipeline-gap-audit.md).
6. Revisar independentemente o conjunto; registrar artefatos/versões exatos,
   backup/restore, flags e rollback; executar commit/push/deploy autorizados apenas
   para o escopo qualificado. Não habilitar gestor não qualificado.
7. Verificar a entrega publicada contra cada R01–R20 e os critérios do plano.
   Trabalho pendente continua com motivo, responsável pelo próximo passo e
   evidência necessária; não transformar bloqueio externo em sucesso.

## Como atualizar este checkpoint

Ao concluir uma etapa ou interromper a sessão, registrar: requisito afetado,
decisão e motivo, arquivos/commit, comando de verificação e resultado, estado
real de publicação/flags, pendências e primeira próxima ação. Preservar o
histórico de critérios/decisões alterados em vez de reescrever o objetivo.

Próxima ação no instante desta escrita: corrigir `host-bridge/app.py` para criar
o scope tmux com `OOMPolicy=continue`, depois do teste de regressão já observado
falhando; qualificar e aplicar sem derrubar o tmux existente. Em seguida, voltar
à regressão e à implementação principal, mantendo R12–R18 como escopo pendente.
