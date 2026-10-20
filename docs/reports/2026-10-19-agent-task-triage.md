# Triagem de falhas e incubações dos agentes — 19/10/2026

## Escopo e autorização

Marcelo autorizou analisar os registros de falha e incubação, excluir o que já foi implementado ou ficou obsoleto e preservar os demais para sua decisão. A triagem partiu dos 39 registros operacionais anteriores a 20/10/2026 00:00 UTC: 27 falhas não arquivadas e 12 incubações não arquivadas. Horários de referência do usuário: America/Sao_Paulo.

Exclusão aplicada somente sobre os itens de Messages, sem tarefa de projeto ou execução de tarefa vinculada e sem anexos. Cada exclusão recebeu um evento `demand_deleted_obsolete` em `company.audit_events`, com ator `codex`, autorização de Marcelo, motivo, número original e referência da evidência. As mensagens de resposta e os históricos das ocorrências de rotina foram preservados; seus vínculos opcionais com o item excluído são tratados pelo banco com `SET NULL`.

## Excluídos: cinco falhas obsoletas

| Número | Registro | Evidência para exclusão |
| --- | --- | --- |
| #27029 | Triagem das rotinas e dos agentes, ocorrência de 03/10 | Ocorrência posterior #29064 concluída em 10/10 com relatório e evidências; runner confirma que o run antigo terminou como `failed`. Não implica que todas as triagens posteriores estejam saudáveis. |
| #27040 | Triagem das rotinas e dos agentes, ocorrência de 04/10 | Mesma substituição por #29064; runner confirma `failed` para o run antigo. |
| #37231 | Retrospectiva diária, ocorrência de 12/10 BRT | Retrospectiva posterior #38742 concluída em 18/10 BRT, com relatório e pendências atuais; runner confirma `failed` para o run antigo. |
| #38690 | Retrospectiva diária, ocorrência de 17/10 BRT | Substituída pela retrospectiva #38742; runner confirma `stale`, sem processo antigo ativo. |
| #38702 | Implementar aba Sugestões e avaliar demanda de teste | `SuggestionsTab.tsx`, integração em Pessoal e redirecionamento de `/suggestions` presentes; artefato publicado `/usr/share/nginx/html/assets/index-DSkacIwr.js` contém a interface; fluxo de aceite tem cobertura nos testes de contatos pessoais que passaram na suíte geral. Runner confirma `stale`. Não foi criada demanda de teste nem alterada qualquer sugestão pessoal. |

Resultado da transação: **5 registros excluídos e 5 eventos de auditoria criados**. Os **54 registros de sugestões pessoais** existentes antes da limpeza continuaram presentes após a transação. A quantidade atual é superior às 16 sugestões mencionadas no pedido histórico; a limpeza não alterou esses dados.

## Preservados para decisão de Marcelo: 12 incubações

| Número | Assunto resumido | Motivo da preservação |
| --- | --- | --- |
| #26382 | Reconhecimento da migração do Foundation | Os próprios documentos de migração ainda declaram o reconhecimento de Athos pendente. Aplicar a migração não conclui o reconhecimento solicitado. |
| #27024 | Cobertura de healthchecks Docker | Inspeção atual confirmou dez containers citados sem healthcheck; melhoria não concluída. |
| #27027 | Observabilidade da limpeza diária Docker | Não foi confirmada a entrega completa do agendamento observável e dos critérios de acompanhamento. |
| #28816 | Auditoria sem cobertura e métricas zeradas | Não há comprovação de um gate completo de sanidade e alerta cobrindo a proposta. Relatório recente ainda apresenta propostas de melhorar a cobertura do auditor. |
| #28817 | Recuperação e alerta do backup externo | `last_run.json` continua com `result=failed`, sem `snapshot_id` ou check bem-sucedido. Há um check de idade de 36h, mas isso não comprova recuperação ou restauração validada. |
| #28818 | Inventário e evidência das rotinas | Há coleta parcial de sinais, mas não foi comprovado relatório padronizado completo com inventário único, contagens e custo disponível/indisponível. |
| #28860 | Healthchecks dos containers sem cobertura | A mesma lacuna de execução permanece. Sobrepõe #27024, mas tem meta diferente; consolidar depende de decisão, sem apagar uma das metas por inferência. |
| #28990 | Quality gate para encerramento das rotinas | `operations_evolution.py` detecta evidência e propõe reforçar instruções, mas isso não equivale ao bloqueio de conclusão sem evidência pedido na incubação. |
| #29060 | Consolidar perguntas duplicadas e vencidas | Não foi comprovada deduplicação operacional completa nem o tratamento das perguntas históricas citadas. |
| #29061 | Métricas confiáveis para retrospectiva | Não foi comprovado o fallback obrigatório completo proposto. |
| #29068 | Automatizar baseline de portas | Existe check automatizado de interfaces em `checklist_verifier.py`, mas isso não comprova toda a baseline declarativa e o relatório por processo/porta/ação solicitado. |
| #29070 | Prova externa de exposição de portas | Não foi comprovada a comparação diária entre listeners, firewall e alcance externo. Não foi realizada varredura de rede nesta triagem. |

## Preservadas para decisão de Marcelo: 22 falhas

| Números | Situação e motivo |
| --- | --- |
| #26996, #28856, #29074, #29075 | Backup externo continua com evidência de falha e sem snapshot válido no registro local. A ocorrência #29030 foi marcada como processada, mas seu relatório declara `BLOCKED / CRÍTICO OPERACIONAL`; não foi usada como prova de recuperação. |
| #28288, #28846, #29065, #29079, #29088, #29109, #29126, #29128, #37595 | Resultado incerto registrado: preservar para reconciliação ou decisão humana. #28856 e #29074, já no grupo de backup, também pertencem a esta categoria. Total de incertos preservados: 11. |
| #28833, #28842, #29067, #29069 | Incidentes de exposição/permissões sem comprovação completa de encerramento. Uma varredura posterior não substitui a investigação e a contenção específica. |
| #29078, #29082 | Triagens que falharam após a última triagem concluída encontrada (#29064); não há sucessora concluída para justificar sua remoção. |
| #29084, #29086 | Há ocorrências posteriores concluídas, mas o runner devolveu 404 para os runs antigos. Foram retiradas da seleção de exclusão para evitar tratar ausência de registro como comprovação de execução encerrada. |
| #37588 | Sincronização de grupos da Maia tem implementação parcial. `sync_groups` reconstrói inventário local, mas `_bridge_group_catalog` declara que o bridge não oferece catálogo completo somente de leitura. Preservada para avaliação das limitações e do objetivo original. |

Os grupos da tabela não são somáveis diretamente, porque os dois casos incertos de backup também aparecem no primeiro grupo. Nenhum desses 22 itens foi arquivado, reexecutado ou excluído.

## Dependências e verificação de código

O ajuste de dependências solicitado antes desta triagem centraliza a regra `done`/`deployed` para todas as predecessoras, incluindo o início por Messages, agendador, tarefa, execução e Work Package. O agendador aguarda sem consumir tentativas e sem bloquear trabalho independente do mesmo agente. Mensagem e execução vinculada têm ambos os IDs de tarefa validados quando diferirem. Ciclos indiretos também são recusados.

- Suíte geral do backend: **906 testes passaram, 9 avisos**, antes do último reforço identificado na revisão.
- Verificação final dos caminhos afetados, incluindo o reforço e regressões adicionais: **83 testes passaram**.
- Ruff dos arquivos de código alterados: passou.
- Ruff geral: dois problemas fora desta alteração, `B904` em `app/mcp/personal_groups.py:246` e importação não utilizada em `app/tests/test_personal.py:7`.
- Não foi feito deploy das correções de dependências. A nova aba “Tarefas dos agentes” continua no planejamento separado.
