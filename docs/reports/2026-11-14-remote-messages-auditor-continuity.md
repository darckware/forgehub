# Continuidade: acesso remoto, Messages e Auditor

Marcelo autorizou finalizar os ajustes anteriores antes da tela de Releases
(especificação aprovada em 14/11/2026).

**Precedência recuperada:** a decisão já publicada na Foundation em
`47_migrations/2026-11-14-development-access.md` autoriza o modo direto de desenvolvimento
com Marcelo, condicionado a credencial protegida, captura confiável e escopo/validade.
Dispensa Task/run apenas nesse modo; os requisitos continuam no modo API. A feature
colaborativa API desta worktree não é pré-requisito de ativação dessa decisão.

## Causas confirmadas

- Messages #42347 retornou `STATUS: PARTIAL`: documentou a exceção, mas não entregou
  o enforcement técnico. O sistema corretamente registrou `dispatch: failed`.
- `ensure_failure_check`, em `backend/app/core/demand_failure_check.py`, arquiva a
  origem assim que cria diagnóstico. Isso conflita com o pedido de manter trabalho
  incompleto visível como falha. Correção isolada em `messages-failure-preservation`.
- O backend colaborativo da worktree exige sessão do dono, Task/run e comando exato,
  mas não revalida o grant de acesso direto do agente. Corrigir grants, elevação,
  revogação/validade e elegibilidade dos três runtimes antes de homologar.
- A feature colaborativa ainda é API sem tela/MCP e depende de dispatch. Corrigir
  enforcement não basta para afirmar que o uso colaborativo solicitado está pronto.

## Revisão do Auditor

Revisão independente, estática, identificou:

1. HIGH: ECO-064 precisa verificar a consistência histórica de sessão colaborativa,
   autorização consumida, execução, alvo, comando/hash, run e eventos obrigatórios.
   A saída deve conter somente contagens. Run atual encerrado/reprocessado não deve
   invalidar execução histórica legítima.
2. MEDIUM: ECO-023 aceita ocorrência `completed` sem evidência completa e datas
   futuras como recentes (`ops/athos/checklist_verifier.py`). Validar evidência ou
   faixa comprovadamente vazia; preservar janela inicial e fallback legado.
3. MEDIUM: runbook exige evidência de faixa trimestral vazia, cujo resultado correto
   é `completed + no_action=true + evidence_received=false` com ECO-058 desligado.
4. MEDIUM: `docs/screens/auditor.md` ainda descreve ECO-001–057 e cron semanal; código
   atual inclui ECO-001–066, ECO-021 aposentado e quatro frequências.
5. ECO-060 deve preservar identidade exclusiva de acesso às chaves; exceções históricas
   não autorizam novas leituras. ECO-059 requer confirmação do manifesto protegido
   antes de afirmar cobertura da skill remote-access.

## Ordem de conclusão

1. Executor corrige grants da colaboração e executor separado preserva falhas Messages.
2. Revisores distintos dos executores conferem os diffs e as regressões.
3. Supervisor executa homologação no ambiente isolado, nunca no banco de produção.
4. Implementar correções do Auditor e revisar novamente com evidência independente.
5. No modo API, completar fluxo utilizável da colaboração antes de ativar a feature;
   no modo direto aprovado, verificar transporte protegido e captura reais antes de operar.
6. Apresentar conteúdo exato para aprovação de integração/publicação.
7. Retomar a tela de Releases e manter regras/changelog coerentes com o estado integrado.

A homologação local abaixo não declara deploy nem feature ativada.

## Homologação local concluída

- Messages: commit `3d88492` em `fix/messages-failure-preservation`; executor Peirce,
  revisor Euler sem achados, supervisor executou 61 testes aprovados. O histórico
  arquivado não foi reaberto automaticamente; futura operação administrativa para
  corrigir apresentação da #42347 deve preservar seu dispatch `failed` e run.
- API remota: executor Anscombe corrigiu grants, runtimes, credencial revogada durante
  readiness, ordem dos locks, escopo da Task e referências ao grant. Revisor Mencius
  confirmou ausência de BLOCKER/HIGH após corrigir um HIGH e três MEDIUM.
- Auditor: executor Gauss corrigiu ECO-023/ECO-064 e documentação. Revisor Schrodinger
  identificou um HIGH na tradução de regex; corrigido por testemunho de hashes bruto
  e mascarado gerado pelo backend. Nova revisão sem BLOCKER/HIGH. A query emite apenas
  contagens e falha se o testemunho obrigatório estiver ausente ou divergente.
- Supervisor, ambiente isolado `forgehub_test` em `127.0.0.1:5439`:
  `test_remote_collaboration`, `test_direct_access`, `test_host_execution` e
  `test_audit_collaboration_integrity`: **275 passed em 65,58s**.
- Supervisor, `ops/athos/tests`, excluído somente o caso que requer conexão real de
  predicate: **171 passed, 1 deselected**. Proteção de alvo do banco: **19 passed**.
- Ruff e `git diff --check` aprovados. Alembic aponta um head: `b8e2c4a6d1f9`.

Pendente: aprovação do conteúdo exato para integração/publicação, verificação
operacional posterior e eventual correção administrativa da apresentação histórica
da #42347. A feature API colaborativa segue desligada e sem tela/MCP; a infraestrutura
de credencial/captura do modo direto não foi verificada nesta homologação local.
