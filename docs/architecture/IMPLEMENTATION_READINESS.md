# ForgeHub — Auditoria de Completude para Implementação

## 1. Parecer

A documentação atual contém uma concepção sólida do produto e da cadeia de entrega, mas **ainda não está completa para uma LLM implementar todos os módulos sem tomar decisões arquiteturais por conta própria**.

O principal documento, `PLANNING_DELIVERY_ARCHITECTURE.md`, já cobre macrofluxos, System Blueprint, escopo, pipeline, planejamento, execução, governança, agentes e release/deploy. As lacunas agora estão na transformação dessa concepção em contratos implementáveis: schemas finais, comandos de domínio, estados, APIs, permissões, eventos, telas e testes por módulo.

O desenho é adequado para uma ferramenta universal: o trabalho pode abranger um produto inteiro ou somente um componente do mapa. A implementação precisa preservar essa generalidade e evitar regras fixas que exijam frontend, banco ou deploy de servidor quando a classificação declarar outra forma de entrega.

### Estado após a consolidação

A **concepção arquitetural está completa como baseline para iniciar o planejamento técnico do Módulo 01**. Os seis contratos em `docs/modules/` definem ordem, ownership, entidades, commands, APIs-alvo, telas, eventos, migração e aceite em nível suficiente para decomposição. Eles não autorizam implementar todos os módulos em uma única onda: antes de cada módulo, Athos deve gerar o plano executável, conferir o Definition Gate, produzir Tasks `planned` e aguardar Execution Release do usuário ou de delegação válida.

```text
Arquitetura aprovada
  -> Athos detalha um módulo
  -> usuário revisa plano/baseline
  -> Tasks permanecem planned
  -> usuário/Athos delegado libera ExecutionWave
  -> Claude/Codex/Agy implementam
  -> review/evidência
  -> próximo módulo
```

Assim, detalhes locais descobertos durante implementação são resolvidos na revisão da spec/plan do módulo antes da liberação, e não por improviso da CLI.

## 2. Problemas documentais encontrados

### 2.1 Gerações diferentes da visão

- `PRD.md` e `SPEC.md` representam a primeira visão do ForgeHub e não incluem Conception, System Blueprint, ProjectScope, tracks, staffing, Policy engine, ReleaseCandidate/Deployment nem o loop governado.
- `DATA_MODEL.md` descreve o banco atual, não o modelo-alvo.
- `BUSINESS_RULES.md` mistura regras implementadas, observações de uma sessão anterior e lacunas conhecidas.
- `PROJECT_DELIVERY_GUIDE.md` descreve automações desejadas junto de funcionalidades atuais; a nota inicial reduz o risco, mas agentes ainda precisam conferir disponibilidade.
- `screens/*.md` cobre somente parte das telas existentes e nenhuma das novas telas de concepção, mapa, escopo, cobertura, release ou cockpit.
- `AGENT_CLI_DEVELOPMENT_PROTOCOL.md` define conduta e pacote, mas não substitui uma máquina de estados ou um motor de dispatch persistente.

### 2.2 Conceitos definidos sem contrato final

Ainda precisam de decisão atributo por atributo:

- ProductConcept/ConceptRevision e Concept Approval;
- SystemElement, versões, relações e especializações;
- ProjectScope e cobertura por elemento;
- DevelopmentRequest/intake comum;
- classificação, tracks e resolvedor composicional;
- versões imutáveis de templates;
- revisão completa de plano/baseline e Change Request;
- Gate derivado de PolicyEvaluation/Approval;
- state machines por domínio;
- ReleaseCandidate, manifesto, Delivery/Deployment e Environment;
- operação, incidentes, manutenção e observabilidade;
- EngineeringRun/WorkPackage, leases, heartbeats, outbox e recovery.
- modos manual/assistido/delegado, mandato de autonomia e transferência de controle humano-agente.

### 2.3 Contradições que não podem ser delegadas à LLM

- Product atual nasce `active`; arquitetura-alvo prevê fase conceitual.
- ProjectTask atual não possui `ready`/`in_review`; arquitetura-alvo usa esses estados.
- TaskExecution atual diferencia `completed` e `verified` de maneira ainda ambígua em algumas rotas/documentos.
- Gate e Approval são registros paralelos, embora o alvo determine que gate derive da governança.
- `ProjectStructureNode` é árvore por Project; System Blueprint é grafo duradouro por Product.
- Planning Item aponta para um único structure node; o alvo exige cobertura M:N.
- Release atual não possui manifesto; DeployInstallation é inventário, não evento de entrega.
- ForgeFlow propõe ledger local autoritativo, enquanto ForgeHub precisa ser autoritativo no modo gerenciado.

## 3. Readiness por módulo

Legenda:

- **Conceitual:** intenção clara, contrato técnico ausente.
- **Parcial:** existe implementação, mas não sustenta o fluxo-alvo.
- **Implementável após spec:** fronteiras claras; falta detalhamento final do módulo.

| Módulo-alvo | Estado | O que já existe | O que falta para implementar com segurança |
|---|---|---|---|
| Documentation Governance | implementado nesta revisão documental | hierarquia em `docs/README.md` | aplicar status/revisão nos documentos antigos e automatizar link/drift checks |
| Conception & Intake | primeira fatia governada implementada | DevelopmentRequest, ProductConcept/revisions, estados, APIs, tela Conception e approval request/decision | intake universal e ampliação das policies por risco/projeto |
| Product & Version | parcial | Product, ProductModule, ProductVersion, Release simples | estado concept, SemVer, capabilities, transições e vínculo com concepção/mapa |
| System Blueprint | primeira fatia implementada | grafo versionado, famílias/tipos, relações, validação, hash e tela agrupada | canvas, edição avançada, schemas por tipo, import/sync e matriz completa |
| Project Scope | primeira fatia implementada | revisão-base, delta por elemento, critérios e tela de cobertura | baseline, compare, M:N com planejamento/tarefas e coverage calculator completo |
| Classification & Tracks | conceitual | descrições livres | catálogos, associações, constraints, resolver e UI |
| Project Planning | parcial | ProjectPlan, PlanBaseline, ChangeRequest | revisões, snapshot canônico completo, state machine e aplicação transacional de CR |
| Pipeline Templates | parcial | template/stages/artifacts | versionamento, applicability/packs, resolução, instanciação atômica e catálogo seed |
| Project Pipeline & Gates | parcial | stages, dependencies, required artifacts, gates | commands, readiness calculator, ciclos completos e derivação de governança |
| Planning/Backlog | parcial | itens, triagem, versão, status | intake comum, critérios, módulos/tracks/scope M:N, dependências e baseline composition |
| Tasks & Dependencies | parcial | tasks/subtasks/dependencies/skills | project/stage/scope explícitos, estados finais, ciclos, DoD e transições por comando |
| Staffing & Scheduling | parcial | memberships, profiles, assignments, capacity fields | restrições por track/stage/path, capacity calculator, ranking e assignment invariants |
| Runtime Orchestration | parcial; primeira fatia de recuperação implementada | dispatch, host bridge, loop policy, reviews, checkpoints, lifecycle recovery e stale assessments | WorkPackage/lease completos, durable runner, PID/heartbeat real e outbox dos adapters |
| Human/Agent Control | primeira fatia implementada | permissões por ação, credencial de serviço revogável e delegação limitada do Athos | modos completos de operação, takeover/pause, runtime e indicação global do decisor atual |
| Artifacts & Evidence | parcial | artifacts, versions, locks, approvals | vínculo obrigatório ao projeto/versão/escopo, hash, storage contract e binding calculado |
| Policy Engine | primeira fatia implementada | Policy JSON, versões/bindings/evaluations, requests/decisions, AuditEvent e separation of duties para concepção | evaluator geral, catálogo por risco/stage, overrides e gates derivados |
| Release & Delivery | conceitual/parcial | Release simples, deploy inventory | candidate/manifest, environment, delivery events, rollback e operational verification |
| Maintenance & Operations | conceitual | audit, crons, deploy inventory, monitoring integrations | Incident/MaintenanceWork, classificação, SLO/checks, feedback loop e templates |
| Daily Cockpit / Athos Control Room | conceitual | dashboard, AssistantDrawer/ChatPane e listas isoladas | read model, browser/focus, Assistant docked, operator actions, control transfer, coverage/readiness, costs e timeline |
| Integrations | parcial | Git/System Control, ForgeRouter, Hindsight | adapters idempotentes, inbound sync governado, health, ownership e reconciliation |

## 4. Mapa dos três macrofluxos para módulos

```text
CONCEPÇÃO E DEFINIÇÃO
DevelopmentRequest
  -> ProductConcept/Revision
  -> Product + capabilities
  -> System Blueprint
  -> concept artifacts + Policies
  -> Concept Approval

CONSTRUÇÃO E ENTREGA
ProductVersion + ProjectScope
  -> classification/tracks
  -> resolved ProjectPipeline
  -> plan/baseline/staffing
  -> Planning Items/Tasks
  -> WorkPackages/Executions/Reviews
  -> Artifacts/Gates
  -> ReleaseCandidate/Release
  -> Delivery/Deployment/Verification

OPERAÇÃO, MANUTENÇÃO E EVOLUÇÃO
Telemetry/Feedback/Incident/Demand
  -> triage + affected SystemElements
  -> operational action or maintenance template
  -> new ProductVersion/Project when code changes
  -> release/delivery
  -> measured outcome
  -> new conception when capability/risk changes materially
```

## 5. Fatias de implementação recomendadas

### Fase 0 — congelar contratos

Antes de novas tabelas:

1. aprovar glossário e ownership de entidades;
2. aprovar máquinas de estados e comandos;
3. definir IDs, revisions, hashes e eventos;
4. decidir ForgeHub/ForgeFlow managed contract;
5. publicar OpenAPI/event schemas dos primeiros módulos;
6. criar ADRs das decisões irreversíveis.

Saída: nenhuma decisão estrutural necessária fica a cargo do implementador.

### Fase 1 — espinha dorsal da concepção e escopo

Implementar:

- DevelopmentRequest;
- ProductConcept/Revision/Approval;
- Product status conceitual;
- SystemElement/Version/Relation;
- ProjectScope/ScopeItem/AcceptanceCriterion;
- telas System Map e Project Scope.

Aceite: uma ideia aprovada gera ProductVersion/Project com delta rastreável, sem Task ainda.

### Fase 2 — linha de produção determinística

Implementar:

- template versionado e resolvedor;
- tracks/classificação;
- instanciação atômica;
- state machines e command endpoints;
- PlanRevision/Baseline completa;
- PolicyDefinition/Binding/Evaluation e Gate readiness.

Aceite: o sistema calcula por que um Stage pode ou não iniciar/terminar.

### Fase 3 — decomposição e execução governada

Implementar:

- cobertura M:N de scope por Planning Item/Task/Artifact;
- dependências/ciclos e DoD;
- staffing/scheduling;
- WorkPackage, lease, heartbeat e durable runner;
- producer–reviewer loop e recovery.

Aceite: outra LLM retoma uma Task sem conversa anterior e não consegue sair do contrato.

### Fase 4 — evidência, release e entrega

Implementar:

- artifact storage/hash/bindings;
- ReleaseCandidate e manifesto;
- Environment e Delivery/Deployment;
- smoke/health/rollback evidence;
- propagação calculada até `operationally_verified`.

Aceite: qualquer elemento entregue é rastreável do objetivo ao ambiente.

### Fase 5 — manutenção, cockpit e otimização

Implementar:

- Incident/Feedback/MaintenanceWork;
- pipelines corretivo, preventivo, adaptativo e evolutivo;
- Daily Cockpit e timeline;
- métricas, custo, capacity e melhoria do scheduler;
- reconciliação robusta das integrações.

Aceite: operação gera manutenção/nova concepção sem perder origem e impacto medido.

## 6. Definition Gate por fatia

Antes de iniciar cada fase acima, produzir um pacote de especificação contendo:

```text
domain/<module>/
  glossary.md
  entities.md
  state-machines.md
  commands-and-policies.md
  api-contract.yaml
  events.yaml
  permissions.md
  ui-flows.md
  migration-and-backfill.md
  acceptance-tests.md
  rollout-and-rollback.md
```

Esses arquivos podem ser ArtifactVersions governadas dentro do próprio ForgeHub quando o módulo suportar isso. Até lá, ficam versionados no repositório.

Use `docs/templates/MODULE_SPEC_TEMPLATE.md` como estrutura mínima. Para acompanhamento e transferência de controle diária, use `docs/templates/DAILY_ENGINEERING_REVIEW.md`.

## 7. Gates para trabalho autônomo por LLM

Uma LLM só pode implementar autonomamente quando:

1. o Definition Gate do módulo estiver aprovado;
2. Work Package contiver revisões exatas e critérios testáveis;
3. paths e ferramentas estiverem delimitados;
4. migrations e compatibilidade tiverem estratégia aprovada;
5. comandos de verificação forem executáveis;
6. reviewer independente estiver configurado;
7. timeout, budget e max iterations estiverem definidos;
8. rollback/stop conditions estiverem explícitos.

Caso contrário, a ação permitida é produzir análise, proposta ou artifact draft — não modificar o sistema como se a decisão estivesse tomada.

## 8. Decisões incorporadas e review humano

As recomendações seguintes foram incorporadas como baseline documental e precisam ser confirmadas no review que precede a primeira ExecutionWave:

1. nomes finais dos três macrofluxos e seus gates;
2. modelo ProductConcept versus criação direta de Product;
3. catálogo inicial de SystemElement e relações;
4. granularidade manual versus sincronizada de classe/método/campo;
5. máquinas de estados alvo;
6. ownership ForgeHub versus ForgeFlow;
7. modelo de Policy/Approval/Gate;
8. unidade geral `Delivery` e especializações;
9. regras de autonomia, approvals humanos e emergency override;
10. conteúdo mínimo do Daily Cockpit.

Depois da confirmação, cada fase é detalhada por Athos e implementada sem improvisação arquitetural.

As decisões recomendadas e os contratos iniciais já foram materializados em `docs/modules/01_...` a `07_...`. Questões descobertas durante review devem ser registradas na spec correspondente; não devem ser resolvidas silenciosamente durante a codificação.
