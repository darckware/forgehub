# 04 — Missões e orquestração

Base: `main` em `43a6a7f`. Documentos de módulos e specs descrevem por vezes o
destino pretendido; as regras abaixo só são chamadas implementadas quando têm fonte
no código corrente.

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MIS-001 | IMPLEMENTADA | Missão muda de estado por comandos de transição válidos, com papel autorizado, `expected row_version`, motivo e precondições. Não atualize estado diretamente para contornar a máquina de estados. | `backend/app/api/routes/mission.py`; `backend/app/tests/test_mission_base.py`; `test_mission_phases.py` |
| MIS-002 | IMPLEMENTADA | Plano submetido gera pedido de aprovação; submissão não é aprovação. Aprovação é independente do executor e vinculada à versão revisada do plano. | `backend/app/api/routes/mission_plan.py`; `backend/app/api/routes/mission.py`; `backend/app/tests/test_mission_plan_approval.py`; guia 01 IAM-009 |
| MIS-003 | IMPLEMENTADA | Após baseline aprovado, mudança de escopo/cronograma/custo segue Change Request com impacto declarado e decisão registrada. Plano genérico de projeto não substitui o fluxo próprio de Missão. | `backend/app/api/routes/mission_plan.py`; `backend/app/api/routes/project.py`; guia 03 DEL-005–007 |
| MIS-004 | IMPLEMENTADA | Critérios de entrada, saída e evidência determinam avanço de etapa. Aceite final ocorre pelo fluxo de aceitação, não por mensagem `completed`, execução limpa ou status informado pelo agente. | `backend/app/api/routes/mission.py`; `backend/app/api/routes/mission_acceptance.py`; `backend/app/tests/test_mission_acceptance.py` |
| MIS-005 | IMPLEMENTADA | A execução de missão respeita o plano aprovado, gates, dependências e escopo. Uma etapa não é concluída enquanto critérios ou evidências obrigatórios estiverem pendentes. | `backend/app/api/routes/mission_phase.py`; `backend/app/tests/test_mission_phases.py`; `docs/modules/09_STAGE_COMPLETION_AND_RECOVERY.md` |
| MIS-006 | IMPLEMENTADA | Orquestração só seleciona agente elegível, membro ativo do projeto e runtime compatível; atribuição/revisão precisam obedecer os papéis exigidos. Não atribua trabalho ao agente apenas por seu nome aparecer no catálogo. | `backend/app/core/mission_cycle.py:528,538`; `backend/app/tests/test_project_executor_eligibility.py`; `backend/app/api/routes/orchestration.py` |
| MIS-007 | IMPLEMENTADA | Quando revisão independente é exigida, produtor e revisor são agentes distintos. Resultado do revisor é registro separado; o executor não se autoaprova. | `backend/app/api/routes/orchestration.py`; `backend/app/tests/test_orchestration.py`; guia 01 IAM-009 |
| MIS-008 | IMPLEMENTADA | Ciclos de coordenação têm limite configurado (1–20 iterações) e critérios explícitos de parada. Repetir uma chamada sem evidência nova não satisfaz progresso nem autoriza execução sem limite. | `backend/app/api/routes/orchestration.py`; `backend/app/tests/test_orchestration.py` |
| MIS-009 | IMPLEMENTADA | Delegação e execução de subagente herdam limites de escopo, orçamento e autonomia aplicáveis. Solicitação de aprovação permanece pendente até decisão explícita e auditada. | `backend/app/core/deps.py`; `backend/app/api/routes/governed_approval.py`; `backend/app/tests/test_governed_authority.py` |
| MIS-010 | PARCIAL | Há um fluxo comum de aprovação de plano de projeto com enforcement mais fraco do que aprovação de missão. Não use esse atalho para missão; ampliação de aprovação governada para projetos comuns ainda precisa de decisão e implementação. | `backend/app/api/routes/project.py:337,353`; `backend/app/tests/test_project.py:225`; guia 03 DEL-007 |
| MIS-011 | GAP | A especificação integrada de missão, Messages e operação contém comportamentos de alvo e atuais no mesmo documento. Agente deve validar cada etapa contra rota/modelo atual; não tratar diagrama ou seção de alvo como garantia instalada. | `docs/architecture/MISSION_MESSAGES_OPERATING_FLOW.md`; `docs/README.md#hierarquia-de-autoridade` |

## Instruções de trabalho

- Leia estado e `row_version` atuais antes de transicionar. Se houver conflito,
  recarregue o recurso e reavalie as precondições; não force atualização concorrente.
- Registre decisão, aprovador, evidência e versão do plano. Falha de notificação não
  desfaz uma decisão já persistida.
- Não marque etapa como concluída nem missão como aceita até que os gates e os
  critérios de aceite correspondentes tenham sido satisfeitos.
- Ao alterar orquestração, cubra seleção elegível, papéis distintos, limite de ciclo,
  interrupção, timeout/estado incerto e vínculo dos artefatos ao trabalho correto.

## Referências

- [Planejamento governado](../modules/08_GOVERNED_PLANNING_APPROVAL.md)
- [Execução e orquestração](../modules/03_EXECUTION_AND_ORCHESTRATION.md)
- [Recuperação e conclusão de etapa](../modules/09_STAGE_COMPLETION_AND_RECOVERY.md)
- [Fluxo de missão, Messages e operação](../architecture/MISSION_MESSAGES_OPERATING_FLOW.md)
