# 06 — Operações e Auditor

Base: `main` em `43a6a7f`. Este guia registra comportamento observado em rotina e
checagens; a tela/documentação de Auditor ainda contém informação antiga e deve ser
atualizada separadamente.

## Rotinas e observabilidade

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| OPS-001 | IMPLEMENTADA | Rotina recorrente registra frequência, fuso, horário e próximo disparo válido; frequência mínima e unicidade da ocorrência evitam agendamento repetido. Não trate execução agendada como concluída sem resultado persistido. | `backend/app/api/routes/operations.py`; `backend/app/db/models/operations.py:85,145`; `backend/app/tests/test_cron_operational_state.py` |
| OPS-002 | IMPLEMENTADA | Gerenciar rotinas exige permissão/delegação operacional própria. Proposta ou pergunta que aguarda resposta não vira alteração ativa por timeout ou silêncio. | `backend/app/api/routes/operations.py:779,790,880`; `backend/app/api/routes/governed_approval.py`; `backend/app/tests/test_agent_activity_routines.py` |
| OPS-003 | IMPLEMENTADA | Rotina de auditoria pode executar sem criar tarefa de agente; os resultados e ocorrências são próprios da auditoria. As quatro rotinas padrão (diária, semanal, mensal e trimestral) começam desabilitadas até configuração/ativação explícita. | `backend/app/core/audit_routines.py`; `backend/app/tests/test_audit_frequencies.py` |
| OPS-004 | IMPLEMENTADA | Rotina registra frescor, ocorrência, resultado e falha/missed run. Falha persistente deve gerar alerta/incidente rastreável; retry periódico é limitado e não oculta a execução que falhou. | `backend/app/core/audit_routines.py`; `backend/app/core/audit_freshness.py`; `backend/app/tests/test_audit_incidents.py` |

## Auditor e remediação

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| OPS-005 | IMPLEMENTADA | Cada check tem identificador canônico, severidade, cadência e condição de ativação. Checks explicitamente desabilitados não devem ser reportados como verificação concluída; pré-condições de ativação precisam ser satisfeitas antes de habilitar. | `backend/app/core/audit_catalog.py`; `backend/app/tests/test_audit_catalog.py` |
| OPS-006 | IMPLEMENTADA | Falha de check cria ou atualiza demanda/tarefa de correção com vínculo ao check e responsável. Check aprovado arquiva demanda não reivindicada conforme política; falha que persiste após correção escala/notifica. | `backend/app/api/routes/audit.py:333,382`; `backend/app/tests/test_audit.py`; `test_audit_remediation.py` |
| OPS-007 | IMPLEMENTADA | Remediação é ação explícita e restrita a administrador. Valide comando/escopo, registre ator e resultado, execute por mecanismo autorizado e rode novamente o check original de forma independente. | `backend/app/api/routes/audit.py:524`; `backend/app/core/audit_remediation.py`; `backend/app/tests/test_audit_remediation.py` |
| OPS-008 | IMPLEMENTADA | Uma tarefa de remediação concluída não prova que o check passou. O check precisa ser reexecutado; persistência da falha mantém/escalona a ocorrência em vez de encerrar por texto de agente. | `backend/app/api/routes/audit.py`; `backend/app/core/audit_remediation.py`; `backend/app/tests/test_audit_remediation.py` |
| OPS-009 | GAP | `docs/screens/auditor.md` descreve catálogo antigo (até ECO-057 e cron legado), enquanto o código-base tem catálogo ECO-001–066 e quatro frequências de auditoria. Corrigir o guia de tela e referências antes de usá-lo como contrato atual. | `backend/app/core/audit_catalog.py`; `backend/app/core/audit_routines.py`; `docs/screens/auditor.md`; `docs/runbooks/auditor-frequencies.md` |
| OPS-010 | GAP | Número de checks no catálogo não é regra fixa de produto. IDs retirados, pausados ou desabilitados têm condições próprias; ao atualizar o catálogo, regenere inventário e cobertura, não replique números de um documento antigo. | `backend/app/core/audit_catalog.py`; `docs/operations/auditor-module-coverage-release.md` |

## Instruções para agentes

- Ao investigar uma falha, preserve `check_id`, ocorrência, timestamp, evidência,
  tarefa vinculada, ator e status. Não arquive para fazer a fila parecer limpa.
- Separe quatro resultados: execução do check, ação de remediação, reexecução do
  check e comunicação da ocorrência. O sucesso de um não implica os demais.
- Mantenha checks de rotina desligados até condições, owner, timezone, cron e
  mecanismo de alerta estarem configurados. Mudança de frequência não deve apagar
  histórico nem recriar ocorrências já registradas.
- Atualize o runbook e a tela Auditor junto com mudanças de catálogo, rotina,
  elegibilidade de remediação ou política de retry.

## Referências

- [Frequências do Auditor](../runbooks/auditor-frequencies.md)
- [Cobertura e release do módulo](../operations/auditor-module-coverage-release.md)
- [Runbook de recuperação de cron do Auditor](../runbooks/auditor-cron-recovery.md)
- `backend/app/core/audit_catalog.py`, `audit_routines.py`, `audit_remediation.py`.
