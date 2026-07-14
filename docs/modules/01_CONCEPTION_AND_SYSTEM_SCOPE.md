# Módulo 01 — Concepção, Product e System Scope

> Estado em 2026-07-13: primeira fatia implementada e validada. Este documento continua sendo o contrato-alvo; a seção 11 distingue o que está disponível agora do que permanece planejado.

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
| `AuthorizeDeliveryPlanning` | concept + blueprint approved | Product active + ProductVersion planned + Project planned + ProjectScope draft |
| `ReviseProjectScope` | scope não baselined | nova revisão/delta |
| `BaselineProjectScope` | planning/gates posteriores completos | scope baselined via PlanBaseline |

`AuthorizeDeliveryPlanning` é idempotente pela Concept Approval; retry retorna os mesmos IDs.

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

Commands usam sufixo de ação para deixar transição explícita. Responses retornam `revision`, `etag/content_hash` e ações elegíveis.

## 7. Interface

- Idea Intake wizard.
- Concept workspace com contexto, documentos, mapa e readiness.
- System Map em grafo + árvore/lists acessíveis.
- Element drawer/detalhe com relações upstream/downstream.
- Process Designer.
- Project Scope com compare base/target e impacto.
- Coverage inicial e Concept Approval panel.

## 8. Eventos/audit

`IdeaCreated`, `ConceptRevised`, `ConceptSubmitted`, `ConceptDecided`, `BlueprintRevisionCreated`, `BlueprintValidated`, `BlueprintApproved`, `DeliveryPlanningAuthorized`, `ProjectScopeRevised`, `ProjectScopeBaselined`.

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

### Parcial ou planejado

- o endpoint efetivo de intake é `POST /api/v1/conception/ideas`; a convergência para um intake universal fica para a evolução de DevelopmentRequest;
- `UpsertElementDraft` entrega criação nesta fatia; edição versionada e remoção lógica ainda serão adicionadas;
- matriz completa de compatibilidade de relações, schemas JSON por tipo, import/sync e catálogo versionado ainda não existem;
- a UI inicial do mapa é agrupada por camada, não um canvas node-edge;
- submit/baseline do Project Scope, coverage M:N com Planning Items/Tasks e Change Request pertencem às próximas ondas;
- autorização específica de aprovador e separação de funções dependem de Governance/Access Profiles e estão registradas em `docs/PLANNING_IMPLEMENTATION_BOUNDARY.md` para validação prévia.
