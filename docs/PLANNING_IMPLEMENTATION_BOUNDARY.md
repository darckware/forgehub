# ForgeHub — Fronteira da Implementação do Grupo Planning

## Status

Onda 01 implementada em 2026-07-13. Qualquer mudança funcional fora desta fronteira exige documentação adicional e validação do usuário antes da implementação.

## Escopo autorizado

Grupo **Planning** da sidebar:

- Products;
- Projects;
- Pipelines;
- Templates;
- Planning/Backlog;
- Execution;
- Artifacts;
- Governance;
- Policies.

Novos componentes autorizados nesta primeira onda:

1. **Conception** — intake de ideia e revisão conceitual.
2. **System Map** — System Blueprint e elementos/relações.
3. **Project Scope** — delta de elementos por Project.

Eles serão exibidos dentro do grupo Planning e reutilizarão os módulos de permissão `product` e `projects` na primeira versão, evitando alteração transversal de Access Profiles.

## Backend autorizado como suporte ao Planning

- modelos, schemas, routes, services/commands e testes dos domínios acima;
- migration no schema `company`;
- ampliação de Product status para `concept`;
- registro técnico de modelos e router;
- vínculos com Product, ProductVersion e Project;
- AuditEvents quando necessários aos commands do Planning.

Esses arquivos de infraestrutura não constituem expansão funcional para outro grupo da sidebar.

## Fora do escopo desta onda

- Dashboard, Workspace, Notifications, Inbox e Docs;
- Assistant global e ChatPane;
- Athos Control Room/browser assistido;
- Agents, Tools, Skills, Foundation, ForgeRouter e Crons;
- Kanboard e Knowledge Base;
- System Control, Hindsight, Auditor, Deploy, Servers e Database;
- Users e Access Profiles;
- host bridge, adapters Claude/Codex/Agy e runner durável;
- ExecutionWave/dispatch automático;
- Release, Delivery, manutenção e Cockpit operacional.

As specs desses itens permanecem documentação futura; não serão parcialmente implementadas nesta onda.

## Arquivos transversais que podem ser tocados

Somente para wiring:

- `backend/app/main.py` — incluir router do domínio;
- `backend/app/db/models/__init__.py` — registrar metadata;
- `frontend/src/App.tsx` — registrar rotas Planning;
- `frontend/src/components/layout/navSections.ts` — adicionar links dentro de Planning;
- documentação/manual do grupo Planning.

Mudança funcional adicional nesses arquivos ou em outros grupos exige novo registro abaixo.

## Registro de dependências fora do escopo

Nenhuma dependência funcional externa foi necessária para entregar a primeira onda. A migração, o router e o wiring foram alterações técnicas autorizadas nesta fronteira.

### Dependência externa liberada e implementada em `ER-GPA-01`

Uma decisão de conceito hoje registra `decided_by` informado pelo cliente e passa pelo middleware autenticado global, mas ainda não valida uma autoridade específica nem separação de funções. A correção plena exige alterações fora dos três novos componentes:

| Componente externo | Motivo | Alternativa temporária | Impacto |
|---|---|---|---|
| Access Profiles / identidade autenticada | derivar o ator do token e exigir permissão de aprovação | operação autenticada e AuditEvent com ator declarado | não usar aprovação autônoma em ambiente multiusuário |
| Governance / Policy evaluator | decidir quem pode aprovar por risco/projeto e impedir autoaprovação | aprovação manual pelo operador responsável | próxima onda deve integrar `ConceptDecision` a Approval/PolicyEvaluation |

Necessidades aprovadas e `ER-GPA-01` explicitamente liberada pelo usuário em **2026-07-13**. A onda implementou identidade derivada da credencial, permissões por ação, policy/evaluation determinística, ApprovalRequest/Decision, separação de funções, delegação limitada do Athos, notificações e integração mínima das telas Conception/Governance.

As Tasks `GPA-01` a `GPA-10` estão concluídas. Essa exceção transversal está documentada em [Módulo 08 — Governed Planning Approval](modules/08_GOVERNED_PLANNING_APPROVAL.md) e não amplia o escopo para runner, dispatch ou execução de Tasks por Claude/Codex/Agy.

Itens deliberadamente adiados:

| Dependência | Motivo do adiamento | Spec futura |
|---|---|---|
| Athos Control Room + Assistant docked | pertence ao controle/orquestração, não ao mapa inicial | `modules/07_ATHOS_CONTROL_ROOM.md` |
| Claude/Codex/Agy | Tasks ainda não serão liberadas/executadas nesta onda | `modules/03_EXECUTION_AND_ORCHESTRATION.md` |
| ExecutionWave | depende de baseline/classificação/pipeline das próximas ondas | `modules/02_PIPELINE_AND_PLANNING.md` |
| Policy engine final | `ER-GPA-01` entrega apenas a policy estruturada de aprovação da concepção; engine geral vem depois | `modules/04_GOVERNANCE_AND_EVIDENCE.md` |
| Release/Operations | depende da cadeia anterior | `modules/05_RELEASE_OPERATIONS_MAINTENANCE.md` |

### Nova necessidade: controle de conclusão e retomada

Registrada, aprovada e implementada sob `ER-SCR-01` em 2026-07-13, conforme [Módulo 09 — Controle de Conclusão, Checkpoint e Retomada](modules/09_STAGE_COMPLETION_AND_RECOVERY.md). A interface inicial pertence aos detalhes de Project/Pipeline no grupo Planning; a onda também recebeu autorização explícita para integração limitada com runtime lifecycle, Notifications, Audit/Event infrastructure e delegação do Athos.

As Tasks `SCR-01` a `SCR-09` estão concluídas. Continuam fora do escopo o runner durável, dispatch/ExecutionWave, heartbeat de processo real e Athos Control Room completo; os adapters Claude/Codex/Agy ainda não receberam autorização de execução por consequência desta release.

### Dependência externa liberada e implementada em `ER-RUN-01`

O recorte foi consolidado em [Módulo 03 — Execução e Orquestração via CLI](modules/03_EXECUTION_AND_ORCHESTRATION.md) sob o identificador reservado `ER-RUN-01`.

- `RUN-01` a `RUN-10` estão em estado `completed`;
- a interface permanece em **Planning > Execution**, com projeções em Task/Pipeline;
- `host-bridge`, adapters, RBAC, Policy evaluation, secrets, Notifications e Audit são dependências externas documentadas;
- o dispatch direto antigo foi bloqueado; `/v1/agent-runs` agora persiste estado seguro, PID, heartbeat e resultado redigido para reconciliação;
- `ER-RUN-01` foi liberada e implementada em **2026-07-13**, sem autorizar release ou deploy dos produtos produzidos pelas CLIs.

## Regra de mudança

Se a implementação revelar necessidade de alterar componente fora deste escopo:

1. não realizar a mudança;
2. registrar arquivo/componente, motivo, alternativas e impacto;
3. atualizar esta documentação ou criar ADR/spec específica;
4. solicitar validação do usuário;
5. somente depois criar/liberar Tasks correspondentes.

## Resultado entregue nesta onda

- `Conception`: intake, revisão versionada por API, submissão, decisão e autorização idempotente do planejamento de entrega;
- `System Map`: revisão versionada, elementos tipados em nove famílias, relações, grafo agrupado, validação estrutural e hash na aprovação;
- `Project Scope`: escopo versionado, seleção de delta por elemento e critérios de aceite;
- Product conceitual não ganha ProductVersion/Project antes da aprovação;
- nenhuma Task ou execução é criada/liberada por este módulo.

Limites conscientes da interface inicial: o mapa é uma visualização agrupada por camadas, ainda sem canvas node-edge; edição avançada de elemento, compare entre revisões, importação e baseline do Project Scope permanecem nas specs das ondas seguintes.
