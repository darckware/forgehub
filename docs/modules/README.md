# ForgeHub — Especificações dos Módulos-Alvo

## Regra de uso

Estes documentos transformam a arquitetura conceitual em contratos implementáveis. A arquitetura define o porquê e as relações globais; cada spec define ownership, dados, estados, comandos, APIs, telas, eventos e aceite de uma fatia.

Ordem de leitura e implementação:

| Ordem | Spec | Dependências | Resultado verificável |
|---:|---|---|---|
| 1 | `01_CONCEPTION_AND_SYSTEM_SCOPE.md` | Product atual | ideia aprovada gera versão, projeto e escopo rastreável |
| 2 | `02_PIPELINE_AND_PLANNING.md` | 1 | escopo gera pipeline/baseline e readiness determinístico |
| 3 | `03_EXECUTION_AND_ORCHESTRATION.md` | 1–2 + `ER-SCR-01` | ExecutionWave, Work Package executável, runner retomável e revisão (`ER-RUN-01` planejada) |
| 4 | `04_GOVERNANCE_AND_EVIDENCE.md` | 1–3 | Policies/gates/evidências calculam aprovação |
| 5 | `05_RELEASE_OPERATIONS_MAINTENANCE.md` | 1–4 | manifesto entregue e verificado alimenta manutenção |
| 6 | `06_COCKPIT_AND_INTEGRATIONS.md` | 1–5 | gestão diária humana/agente e projeções reconciliáveis |
| 7 | `07_ATHOS_CONTROL_ROOM.md` | Assistant atual + 2–6 progressivamente | usuário acompanha e controla Athos em uma tela integrada |
| 8 | `08_GOVERNED_PLANNING_APPROVAL.md` | primeira fatia do módulo 01 + RBAC/Governance atuais | aprovação de concepção por identidade, política, delegação e auditoria |
| 9 | `09_STAGE_COMPLETION_AND_RECOVERY.md` | módulos 2–4, runtime e Cockpit progressivamente | checkpoint autoritativo, conclusão comprovada e retomada após interrupção |

Uma fase pode criar migrations preparatórias para a seguinte, mas não deve implementar comportamento cuja spec/dependência ainda não esteja aprovada.

## Convenções comuns

- UUID Python-side e `TimestampMixin` em todas as tabelas.
- FKs cross-domain em forma string, conforme convenção atual.
- Constraints de coluna/linha no banco; validações cross-row nas commands/services de domínio.
- Escrita por comandos explícitos; PATCH de status é compatibilidade transitória, não API-alvo.
- Erros possuem `code`, `message`, `entity_id`, `details` e status HTTP estável.
- Mutação aceita idempotency key quando pode ser repetida por runtime/integrador.
- Eventos e AuditEvents são append-only e versionados.
- Toda listagem oferece paginação/filtros antes de produção em escala.
- Toda tela implementa loading, empty, error, forbidden, stale e success.
- Toda alteração pós-baseline preserva histórico.
- O código atual continua autoritativo até a migration de cada módulo.

## Gates transversais

Cada spec só está aprovada quando:

1. migrations e backfill possuem estratégia;
2. comandos e transições inválidas estão testáveis;
3. autorização humana/agente está definida;
4. audit/events estão definidos;
5. UI não exige UUID digitado;
6. integração tem timeout/retry/reconciliation;
7. rollout e rollback estão definidos;
8. critérios de aceite ponta a ponta possuem evidência.
