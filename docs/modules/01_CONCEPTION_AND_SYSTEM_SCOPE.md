# Módulo 01 — Concepção, Product e System Scope

> Estado em 2026-07-13: primeira fatia implementada e validada. Este documento continua sendo o contrato-alvo; a seção 11 distingue o que está disponível agora do que permanece planejado.
>
> 2026-08-01: adicionada a extensão de Screen Registry (telas, regra de negócio por tela e
> derivação de banco de dados) — ver as novas entidades em §3, commands em §4, APIs em §6 e
> o estado em §11. Esta fatia é o primeiro de um roadmap maior de redesenho da pipeline
> Software Factory (classificação de tipo de aplicação por Project, planejamento por agente
> responsável, Governance/Version Closure conectados a backend real, telemetria de execução
> de agentes) — as próximas fatias ainda não têm spec própria neste diretório.
>
> 2026-08-01 (mesmo dia): adicionada a extensão de classificação de tipo de aplicação por
> Project (`solution_type`) — `:authorize-delivery-planning` passa a criar um Project por
> tipo solicitado sob a mesma ProductVersion. Diverge deliberadamente da recomendação de
> Tracks de `docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md` §2.2 (nota registrada lá).
> Também adicionada a ação de sincronizar os artefatos gerados da Concepção para o
> repositório real de um Project (host-bridge `fs/write`).

## 1. Objetivo

Transformar uma ideia em Product conceitual, mapa versionado e proposta de escopo; após aprovação, criar ProductVersion e Project sem iniciar implementação automaticamente. O módulo serve a sistemas completos e componentes isolados.

## 2. Ownership

- Conception: DevelopmentRequest, ProductConcept, ConceptRevision e decisão de conceito.
- Product: Product, ProductModule/capability e ProductVersion.
- System Map: SystemBlueprint, revisões, elementos e relações.
- Project Scope: ProjectScope, itens e critérios de aceite.
- Governance decide aprovação; este módulo solicita e consome a decisão.

## 3. Entidades-alvo

### `development_requests`

`id`, `product_id`, `request_type`, `title`, `description`, `source_type`, `source_ref`, `requested_by`, `priority`, `status`, `triage_result`, `created_at`, `updated_at`.

- `request_type`: `new_product|feature|bug|maintenance|research|compliance|incident_follow_up`.
- `status`: `received|triaging|accepted|rejected|converted|cancelled`.
- Para nova ideia, a command cria Product `concept` e request na mesma transação.

### `product_concepts`

`id`, `product_id` único ativo, `status`, `current_revision_id`, `created_by`.

- `status`: `draft|in_review|approved|rework|hold|rejected|superseded`.

### `product_concept_revisions`

`id`, `concept_id`, `revision`, `problem_statement`, `vision`, `stakeholders`, `personas`, `objectives`, `success_metrics`, `constraints`, `assumptions`, `risks`, `scope_summary`, `created_by`, `content_hash`.

- Imutável após submissão.
- Unique `(concept_id, revision)` e hash canônico.

### Product

Ampliar `Product.status` para `concept|active|inactive|archived`. Product aprovado passa a `active`; rejeitado pode ficar `archived`, preservando a origem.

### `system_blueprints` e revisões

- `system_blueprints`: `id`, `product_id` unique, `name`, `current_revision_id`.
- `system_blueprint_revisions`: `id`, `blueprint_id`, `revision`, `status`, `concept_revision_id` nullable, `product_version_id` nullable, `content_hash`, `created_by`.
- Status: `draft|in_review|approved|superseded`.
- Uma revisão pode nascer na concepção sem ProductVersion; após aprovação, ProductVersion referencia a revisão-base.

### `system_elements`

`id`, `product_id`, `stable_key`, `family`, `element_type`, `name`, `description`, `lifecycle_status`, `criticality`, `owner_ref`, `parent_id`.

- Unique `(product_id, stable_key)`.
- `lifecycle_status`: `proposed|active|deprecated|removed`.
- Famílias/tipos seguem o catálogo da arquitetura; inclusão de tipo exige catálogo versionado, não valor livre.

### `system_element_revisions`

`id`, `system_element_id`, `blueprint_revision_id`, `spec_snapshot`, `source_ref`, `content_hash`, `status`.

- Unique `(blueprint_revision_id, system_element_id)`.
- Snapshot JSON possui schema por `element_type`.

### `system_element_relations`

`id`, `blueprint_revision_id`, `from_element_id`, `to_element_id`, `relation_type`, `attributes`.

- Unique por revisão/origem/destino/tipo.
- Proibir self relation salvo tipo explicitamente permitido.
- Validar compatibilidade pela matriz de relações.

### `project_scopes`

`id`, `project_id`, `blueprint_base_revision_id`, `revision`, `status`, `content_hash`, `created_by`.

- `status`: `draft|in_review|baselined|superseded`.

### `project_scope_items`

`id`, `project_scope_id`, `system_element_id`, `base_element_revision_id`, `target_element_revision_id`, `change_type`, `applicability`, `rationale`.

- `change_type`: `add|modify|remove|deprecate|verify`.
- `applicability`: `required|optional|not_applicable`.
- `not_applicable` exige rationale.

### `scope_item_acceptance_criteria`

`id`, `project_scope_item_id`, `criterion`, `verification_type`, `required`, `order_index`.

### Screen Registry (extensão 2026-08-01 — sem tabela nova)

Uma tela é um `system_element` (`element_type="screen"`, família `experience`) escopado a
um Project via `project_scope_items` (`change_type="add"`). Screens e as tabelas/campos
derivados deles vivem numa única `system_blueprint_revision` compartilhada por produto,
sempre `status="draft"` e `concept_revision_id IS NULL` — separada da linhagem de revisões
governadas pela Concepção, para que cadastrar uma tela nunca reabra a aprovação do
Blueprint/Concept. Get-or-create por `(blueprint_id, status=draft, concept_revision_id=NULL)`.

`system_element_revisions.spec_snapshot` de uma tela guarda:

```json
{
  "attributes": [{"name": "email", "type": "string", "required": true, "description": "..."}],
  "prototype_html": "<div>...</div>",
  "css_framework": "plain",
  "template_ref": null,
  "image_refs": []
}
```

`attributes[].type`: `string|number|boolean|date|relation`. `prototype_html`/`css_framework`
e `template_ref`/`image_refs` são dois modos alternativos de protótipo **conceitual** — nunca
o código final da implementação; a tela usa um dos dois, nenhum é obrigatório.

Regra de negócio por tela: arquivo `.md` versionado (não uma tabela) em
`/docs/projects/<project-slug>/business-rules/<screen-stable-key>.md`, mesmo mecanismo de
`/docs` (`DOCS_ROOT`/`resolve_doc_path`) que os artefatos gerados da Concepção já usam.

Derivação de banco: `table`/`field` são `system_elements` de família `data` propostos a
partir de `attributes` (1 `table` por tela + 1 `field` "id" uuid PK + 1 `field` por
atributo), relacionados por `contains` (table→field) e `persists_as` (screen→table) —
mesma convenção que `dataSpec.ts`/`buildErdSchemaFromBlueprint` (System Map, Entities view)
já usa para converter o grafo em `SchemaOut` e renderizar via `buildMermaidERD`. Determinístico
(sem LLM), idempotente por `stable_key`.

## 4. Commands e transições

| Command | Precondições | Resultado |
|---|---|---|
| `CreateIdea` | título/problema mínimos | Product concept + DevelopmentRequest + ProductConcept revision 1 |
| `ReviseConcept` | concept draft/rework | nova revisão imutável |
| `SubmitConcept` | revision/mapa válidos | concept `in_review`, solicita Approval |
| `DecideConcept` | approval authority | approved/rework/hold/rejected |
| `CreateBlueprintRevision` | product existente | nova revisão draft clonada ou vazia |
| `UpsertElementDraft` | blueprint draft | elemento/revisão no draft |
| `RelateElements` | tipos compatíveis | relação na revisão draft |
| `ApproveBlueprintRevision` | sem erros estruturais | revisão approved/supersede anterior |
| `AuthorizeDeliveryPlanning` | concept + blueprint approved | Product active + ProductVersion planned + **N** Project planned (um por `solution_type` pedido) + N ProjectScope draft |
| `ReviseProjectScope` | scope não baselined | nova revisão/delta |
| `BaselineProjectScope` | planning/gates posteriores completos | scope baselined via PlanBaseline |
| `CreateScreen` | scope existente | screen element + revision + `project_scope_item` (`add`) |
| `UpdateScreen` | screen no scope | patch direto de nome/descrição/`spec_snapshot` — sem agente, sem gate |
| `RemoveScreen` | screen no scope | remove só o `project_scope_item`; element/revision permanecem (catálogo compartilhado) |
| `WriteScreenBusinessRule` | screen no scope | grava `.md` versionado, sem abrir revisão de Blueprint |
| `DeriveDatabase` | scope com telas | propõe/atualiza `table`/`field` a partir dos atributos das telas, idempotente |
| `SyncArtifactsToProject` | project com `working_directory_path` | copia os documentos gerados/gravados da Concepção para `<working_directory_path>/docs/` via host-bridge, reexecutável |

`AuthorizeDeliveryPlanning` recebe uma lista de `{solution_type, project_name, ...}` (uma por
tipo de aplicação) em vez de um único projeto. Idempotência mudou de chave: era por `version`
(1 versão = 1 projeto), passou a ser por `(version, solution_type)` — reprocessar o mesmo par
retorna o Project existente; pedir um `solution_type` novo sob uma versão já existente cria
um Project a mais na mesma ProductVersion, sem criar uma versão nova. Cada Project só recebe
`ProjectScopeItem`/`PlanningItem`/`ProjectTask` dos elementos do Blueprint cuja camada
(`FAMILY_LAYER_LABELS`) corresponde ao seu `solution_type` (`SOLUTION_TYPE_LAYERS` no route).

**Pacote 3 (2026-08-01):** `ProjectSpec.responsible_agent_id` (opcional) auto-cria uma
`ProjectAgentMembership` (domínio Orchestration) para o Project com `role` derivado de
`ROLE_BY_SOLUTION_TYPE`, e um `TaskAssignment` para cada task criada no escopo desse Project.
Um elemento `experience`/`screen`|`route` com `spec_snapshot.target_platforms` (`["web"]` ou
`["mobile"]`) só entra no escopo de `web_app`/`mobile_app`, respectivamente, quando a
plataforma bate — sem a tag, entra nos dois (comportamento anterior preservado). Ver também
CLAUDE.md (bullet "`dispatch_task` gates on `TaskDependency`...") para as mudanças
correspondentes no domínio Task (`plan_brief`, checagem de dependência no dispatch).

**Pacote 4 (2026-08-01):** `_assert_version_editable(db, project_id)` bloqueia (409) as
rotas de Escopo (`add_project_scope_item`) e Telas (`create_screen`/`update_screen`/
`remove_screen`/`write_screen_business_rule`/`derive_database`) quando a `ProductVersion`
do Project já está `published`. Deliberadamente **não** aplicado a Concept/System
Blueprint (são por Produto, não por versão — ver CLAUDE.md, bullet "Publishing a
`ProductVersion`..." para o raciocínio completo e a trava equivalente em `backlog.py`).

## 5. Validações do mapa

- elemento órfão permitido somente para raiz/catálogo ou com justificativa;
- tela/processo/API/regra/dado sem relações esperadas gera warning ou erro conforme Policy;
- ciclo em `contains` e `precedes` é inválido;
- integração externa usa elemento marcado external;
- remoção mantém identidade e revisão histórica;
- revisão aprovada é imutável;
- ProductVersion/ProjectScope apontam para revisão aprovada.

## 6. APIs-alvo

- `POST /api/v1/development-requests/ideas`
- `GET /api/v1/products/{id}/concept`
- `POST /api/v1/products/{id}/concept/revisions`
- `POST /api/v1/product-concepts/{id}:submit|:decide`
- `GET|POST /api/v1/products/{id}/system-blueprint/revisions`
- `GET|POST|PATCH /api/v1/blueprint-revisions/{id}/elements`
- `POST|DELETE /api/v1/blueprint-revisions/{id}/relations`
- `POST /api/v1/blueprint-revisions/{id}:validate|:submit|:approve`
- `POST /api/v1/product-concepts/{id}:authorize-delivery-planning`
- `GET|POST /api/v1/projects/{id}/scope/revisions`
- `POST /api/v1/project-scopes/{id}:validate|:submit|:baseline`
- `GET|POST /api/v1/project-scopes/{id}/screens`
- `PATCH|DELETE /api/v1/project-scopes/{id}/screens/{element_id}`
- `GET|PUT /api/v1/project-scopes/{id}/screens/{element_id}/business-rule`
- `POST /api/v1/product-concepts/{id}/sync-artifacts-to-project/{project_id}`
- `POST /api/v1/project-scopes/{id}/derive-database`

Commands usam sufixo de ação para deixar transição explícita. Responses retornam `revision`, `etag/content_hash` e ações elegíveis.

## 7. Interface

- Idea Intake wizard.
- Concept workspace com contexto, documentos, mapa e readiness.
- System Map em grafo + árvore/lists acessíveis.
- Element drawer/detalhe com relações upstream/downstream.
- Process Designer.
- Project Scope com compare base/target e impacto.
- Coverage inicial e Concept Approval panel.
- Screen Registry (`/screen-inspector`): lista de telas do escopo, editor de atributos,
  protótipo (HTML livre com preview sandboxed ou template+imagens), editor de regra de
  negócio, ação "Solicitar ao agente" (compõe uma Mensagem `Tipo=Task`).
- Database Modeling (`/concept-erd`): tabelas/colunas derivadas das telas, diagrama Mermaid,
  ação de validação da modelagem.
- Conception, aba "Entrega" (visível só com concept aprovada): formulário de versão + lista
  de `{tipo de aplicação, nome, working directory}` a criar, botão "Autorizar Entrega",
  resultado por Project (link + contadores) e botão "Sincronizar docs para o repositório"
  por Project.

## 8. Eventos/audit

`IdeaCreated`, `ConceptRevised`, `ConceptSubmitted`, `ConceptDecided`, `BlueprintRevisionCreated`, `BlueprintValidated`, `BlueprintApproved`, `DeliveryPlanningAuthorized`, `ProjectScopeRevised`, `ProjectScopeBaselined`, `ScreenCreated`, `ScreenBusinessRuleWritten`, `DatabaseDerived`, `ArtifactsSyncedToProject`.

## 9. Migração

1. adicionar `concept` ao Product status sem alterar produtos atuais;
2. criar novas tabelas;
3. para Product atual, criar Blueprint revision 1 draft/approved conforme regra de migração explicitamente escolhida;
4. converter `ProductModule` em elementos module/capability preservando IDs por mapping;
5. importar `ProjectStructureNode` como elemento/revisão e guardar `legacy_structure_node_id` durante transição;
6. manter `PlanningItem.structure_node_id` até associations M:N da fase 3;
7. não apagar tabelas/colunas legadas antes de reconciliação e métricas de uso.

## 10. Critérios de aceite

1. Criar ideia não exige UUID técnico e gera todas as raízes transacionalmente.
2. Ideia rejeitada não cria Project.
3. Aprovação repetida não duplica Version/Project.
4. Blueprint aprovado não pode ser editado.
5. Relações inválidas/cíclicas são rejeitadas com código estável.
6. ProjectScope mostra add/modify/remove/verify contra revisão-base.
7. Um componente isolado pode ser escopo sem exigir tela/banco, com `not_applicable` explícito.
8. Toda ação produz evento/audit e respeita autorização humana/agente.

## 11. Estado da primeira fatia implementada

### Disponível

- tabelas e migration `d8a4f1c2e630` no schema `company`;
- status `Product.concept`;
- commands/API de ideia, revisão de conceito, submissão/decisão, revisão e grafo do Blueprint, elementos, relações, validação, autorização idempotente e itens de Project Scope;
- telas `Conception`, `System Map` e `Project Scope` dentro de `PLANNING`;
- fluxo testado: ideia → bloqueio de mapa vazio → elemento → validação → submissão → aprovação → ProductVersion/Project/Scope → critério de aceite;
- aprovação do mapa gera hash canônico e bloqueia edição;
- autorização repetida retorna os mesmos IDs e não duplica entidades.

**Screen Registry (2026-08-01):**

- CRUD de tela (element + revision no "screens revision" get-or-create por produto) e
  `project_scope_items` de vínculo com o Project Scope, testado ponta a ponta;
- edição direta de atributos/protótipo sem chamada a agente (economia de token — decisão
  explícita: só mudanças de layout/lógica passam por Mensagens);
- regra de negócio em `.md` versionado, leitura/escrita testadas;
- `derive-database` determinístico e idempotente (sem LLM), testado incluindo re-execução;
- ERD renderizado reaproveitando `buildErdSchemaFromBlueprint`/`buildMermaidERD` já existentes
  (System Map, Entities view) sobre o grafo derivado, sem endpoint de schema novo;
- telas `Screen Registry`/`Database Modeling` reais substituindo os mocks anteriores de
  `/screen-inspector` e `/concept-erd`.

**Classificação de tipo de aplicação por Project (2026-08-01, mesmo dia):**

- `Project.solution_type` (`web_app|mobile_app|api_service|database|deploy`), migration
  `190281545b4f`, testado (CHECK constraint, nullable para projetos pré-existentes);
- `:authorize-delivery-planning` aceita `projects: [{solution_type, project_name, ...}]` e
  cria um Project por tipo sob a mesma ProductVersion, idempotente por `(version,
  solution_type)`, testado incluindo "3º tipo adicionado depois" sem duplicar a versão;
  cada Project só recebe as tasks/scope items da sua camada (`SOLUTION_TYPE_LAYERS`),
  testado com 2 tipos simultâneos sem contaminação cruzada;
- aba "Entrega" na Conception — UI que faltava para disparar `:authorize-delivery-planning`
  (o hook já existia, mas nenhuma tela o chamava antes desta fatia);
- `POST .../sync-artifacts-to-project/{project_id}`: copia os documentos gerados da
  Concepção para o repositório real do Project via host-bridge `fs/write`, reaproveitando os
  helpers de `api/routes/project.py` (`_bridge_request`/`_get_working_dir_or_400`).

**Planejamento por agente responsável — núcleo (Pacote 3, 2026-08-01):**

- `responsible_agent_id` em `ProjectSpec` cria `ProjectAgentMembership` + `TaskAssignment`
  por task automaticamente, testado (membership com `role` correto, assignments cobrindo
  todas as tasks do Project, nenhuma membership criada para Project sem agente responsável);
- `target_platforms` no `spec_snapshot` de telas separa `web_app`/`mobile_app` sem duplicar,
  testado (tela tagueada só entra no tipo certo; tela sem tag entra nos dois, preservando o
  comportamento anterior);
- `dispatch_task` (domínio Task, fora deste módulo) ganhou checagem de `TaskDependency`
  (409 + lista bloqueante) e o campo `ProjectTask.plan_brief` — ver CLAUDE.md para o detalhe,
  já que o domínio Task não tem spec própria neste diretório ainda;
- retry automático e loop/iteração entre agentes ficaram fora desta fatia (risco de
  reexecução descontrolada sem guardrails próprios — ver roadmap).

### Parcial ou planejado

- o endpoint efetivo de intake é `POST /api/v1/conception/ideas`; a convergência para um intake universal fica para a evolução de DevelopmentRequest;
- `UpsertElementDraft` entrega criação nesta fatia; edição versionada e remoção lógica ainda serão adicionadas;
- matriz completa de compatibilidade de relações, schemas JSON por tipo, import/sync e catálogo versionado ainda não existem;
- a UI inicial do mapa é agrupada por camada, não um canvas node-edge;
- submit/baseline do Project Scope, coverage M:N com Planning Items/Tasks e Change Request pertencem às próximas ondas;
- autorização específica de aprovador e separação de funções dependem de Governance/Access Profiles e estão registradas em `docs/PLANNING_IMPLEMENTATION_BOUNDARY.md` para validação prévia;
- Screen Registry: sem aprovação formal de regra de negócio via Governance/Artifact (fica
  simples arquivo `.md` por enquanto), sem geração assistida por LLM do protótipo/atributos
  (hoje é edição manual + derivação determinística), e a lista de telas do Screen Registry
  ainda não é filtrada por elemento no `blueprint_base_revision_id` do scope (mostra todas as
  telas do produto vinculadas ao scope via `project_scope_items`);
- classificação de tipo de aplicação: `web_app`/`mobile_app` compartilhando a camada
  `Frontend` sem dividir as mesmas telas foi resolvido no Pacote 3 via `target_platforms`
  opt-in por elemento (ver acima) -- continua valendo só quando alguém tagueia a tela; sem a
  tag, ainda entra nos dois por padrão. `PROJECT_SOLUTION_TYPES` tem só 5 valores (não o
  catálogo completo de 11 do `PLANNING_DELIVERY_ARCHITECTURE.md` §2.2) -- estender conforme a
  necessidade real de uso;
- `ROLE_BY_SOLUTION_TYPE` mapeia `web_app`/`api_service`/`mobile_app` todos para `developer`
  (vocabulário de `PROJECT_AGENT_ROLES` é de ciclo de vida de projeto, não de camada técnica)
  -- não distingue agente de frontend de agente de backend automaticamente.
