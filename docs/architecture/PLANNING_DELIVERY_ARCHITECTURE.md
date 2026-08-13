# ForgeHub — Arquitetura de Planning e Delivery

## 1. Objetivo e status deste documento

Este documento é a referência de arquitetura para os módulos **Products, Projects, Pipelines, Templates, Planning, Execution, Artifacts, Governance, Policies, Release e Deploy**. Ele descreve:

- o que o código implementa hoje;
- onde o modelo atual perde rastreabilidade ou permite estados inválidos;
- a estrutura-alvo para controlar toda a linha de produção de software;
- um exemplo completo de desenvolvimento;
- o contrato operacional que agentes CLI devem seguir.

Legenda usada na análise:

- **Implementado**: modelo e API sustentam a regra.
- **Parcial**: a entidade existe, mas a integração ou a regra ainda depende de operação manual.
- **Proposto**: mudança necessária; não deve ser presumida por agentes como funcionalidade existente.

O código é a fonte de verdade sobre o estado atual. Este documento é a fonte de verdade sobre a direção arquitetural.

Para a hierarquia completa dos documentos, consulte `docs/README.md`. O contrato operacional-alvo para execução por qualquer LLM está em `docs/architecture/ENGINEERING_LOOP.md`; a auditoria de lacunas e a ordem recomendada de implementação estão em `docs/architecture/IMPLEMENTATION_READINESS.md`.

O objetivo final é uma **plataforma universal de engenharia de software**, não um gerador restrito a aplicações web. O mesmo núcleo deve conduzir desenvolvimento novo, manutenção e evolução de um sistema completo ou de uma unidade menor, como módulo, tela, componente, serviço, API, biblioteca, automação, integração, pipeline de dados, solução de IA, infraestrutura ou pacote de configuração. A classificação determina quais elementos, stages, artifacts, Policies, verificações e formas de Delivery são aplicáveis.

O processo pode ser gerenciado diretamente pelo usuário, assistido por agentes ou delegado com autonomia limitada. Humanos e agentes operam os mesmos comandos e estados; permissões, delegações, risco, orçamento e Policies determinam quem pode executar ou aprovar cada ação. O usuário pode pausar, assumir ou devolver o controle sem apagar o histórico.

Athos é o operador-orquestrador padrão do ForgeHub. Ele acompanha o Cockpit, conduz os três macrofluxos, prepara decisões, monta equipes, gera planos, propõe/ativa ExecutionWaves dentro da delegação e monitora producer–reviewer loops. O usuário é a autoridade final e pode reservar approvals, pausar ou assumir o controle. Athos não substitui Agents especialistas nem se torna executor universal de implementação.

## 2. Decisão central de arquitetura

ForgeHub deve tratar desenvolvimento como uma cadeia de produção rastreável, e não como cadastros independentes:

```text
Product
  └─ ProductVersion
       └─ Project
            ├─ ProjectPlan ── PlanBaseline ── ChangeRequest
            ├─ ProjectPipeline (instância imutável de um template versionado)
            │    └─ PipelineStage
            │         ├─ StageWorkItem ── PlanningItem ── ProjectTask
            │         │                                  └─ TaskExecution
            │         ├─ RequiredArtifact ── Artifact ── ArtifactVersion
            │         └─ Gate ── Approval
            └─ ReleaseCandidate ── Release ── Deployment
                                      └─ DeploymentEvidence
```

Invariante pretendido:

> Todo trabalho executável e todo entregável deve ser resolvível até Product, ProductVersion, Project, Pipeline e Stage; toda conclusão deve possuir evidência, revisão e auditoria; toda entrada em produção deve apontar para uma Release aprovada e para o conjunto exato de artefatos implantados.

Nem todos esses vínculos existem hoje. As seções seguintes distinguem o modelo atual do modelo necessário.

## 2.1 Três macrofluxos do ciclo de vida

O ForgeHub deve organizar o desenvolvimento de um produto em três macrofluxos. Eles compartilham o mesmo System Blueprint e a mesma trilha de auditoria, mas possuem objetivos, gates e registros diferentes.

```text
1. Concepção e Definição
   ideia -> contexto -> produto -> mapa do sistema -> escopo -> viabilidade -> aprovação

2. Construção e Entrega
   planejamento executável -> baseline -> implementação -> testes -> release -> deploy

3. Operação, Manutenção e Evolução
   observar -> suportar -> corrigir -> adaptar -> melhorar -> nova implementação
                                      |                         |
                                      +---- novo ciclo ---------+
```

### Macrofluxo 1 — Concepção e Definição

Transforma uma ideia incerta em uma proposta compreendida e apta a receber investimento de entrega:

```text
Intake da ideia
  -> contextualização e problema
  -> objetivos, stakeholders e personas
  -> capabilities, módulos, jornadas e processos
  -> System Blueprint inicial
  -> requisitos, regras e critérios de sucesso
  -> escopo proposto da primeira versão
  -> UX e arquitetura de alto nível
  -> viabilidade, riscos e estimativa preliminar
  -> Concept Approval: go | rework | hold | reject
```

O `Product` nasce em estado conceitual para ancorar documentos e decisões. `ProductConcept` e suas revisões preservam a evolução da ideia. Uma concepção rejeitada ou suspensa não precisa gerar Project. A decisão `go` autoriza criar ou confirmar ProductVersion e Project para planejamento da entrega; não autoriza codificação diretamente.

### Macrofluxo 2 — Construção e Entrega

Transforma a concepção aprovada em uma versão verificável e entregue:

```text
Concepção aprovada
  -> ProductVersion + Project
  -> classificação e delta do System Blueprint
  -> pipeline, tracks, equipe e Policies
  -> Planning Items, Tasks, dependências e estimativas
  -> design/arquitetura detalhados
  -> PlanBaseline + Delivery Authorization
  -> implementação e integração
  -> revisão e verificação
  -> build + Release Candidate
  -> Release Approval
  -> deploy/publicação/ativação
  -> verificação operacional
```

Existem três autorizações distintas: Concept Approval permite planejar; Delivery Authorization aprova a baseline e permite implementar; Release Approval permite entregar no ambiente-alvo. Após a baseline, mudança relevante de escopo usa Change Request.

Delivery Authorization não precisa liberar todas as Tasks simultaneamente. Ela autoriza o plano; a execução é aberta por `ExecutionWave` ou por liberação individual governada. Somente Tasks baselined, completas e com dependências satisfeitas podem passar de `planned` para `ready`. O usuário ou agente delegado decide quais ações elegíveis entram na próxima onda, respeitando WIP, capacidade, risco, orçamento e Stage.

### Macrofluxo 3 — Operação, Manutenção e Evolução

Começa depois da primeira entrega e dura enquanto o Product existir. Ele preserva disponibilidade, segurança e valor do sistema, além de originar novas implementações.

| Classe | Finalidade | Exemplos |
|---|---|---|
| operação | manter e observar o serviço em funcionamento | monitoramento, suporte, backup, capacity, custos, SLO |
| manutenção corretiva | corrigir comportamento defeituoso | bug, hotfix, incidente, correção de dados |
| manutenção preventiva | reduzir probabilidade de falha futura | atualização de dependência, hardening, testes, remoção de risco |
| manutenção adaptativa | responder a mudança externa | versão de SO, API de terceiro, regra legal, navegador, infraestrutura |
| manutenção evolutiva | melhorar comportamento existente | performance, acessibilidade, UX, refactoring com benefício mensurável |
| nova implementação | acrescentar capability, processo, tela, integração ou canal | novo módulo, app mobile, automação, relatório, API pública |

Fluxo operacional:

```text
Telemetria / Feedback / Incidente / Demanda
  -> triagem e associação ao elemento do System Blueprint
  -> classificação da mudança e impacto
  -> resposta operacional imediata, quando aplicável
  -> manutenção ou nova implementação
  -> novo Project/versão ou ciclo abreviado governado
  -> release/deploy
  -> comparação dos resultados com a baseline operacional
```

Nova implementação não altera silenciosamente uma versão já entregue. Ela atualiza o System Blueprint por uma nova ProductVersion e um novo Project, mesmo quando reutiliza contexto e arquitetura existentes. O que varia é a profundidade da reconcepção:

| Situação | Caminho obrigatório |
|---|---|
| correção interna sem mudança de contrato | intake/triagem -> pipeline corretivo ou hotfix -> release/deploy |
| melhoria de elemento existente dentro da visão aprovada | revisão de impacto leve -> nova versão/Project -> construção e entrega |
| nova tela dentro de processo já aprovado | atualizar processo e System Blueprint -> escopo/versionamento -> construção e entrega |
| nova capability, persona, processo, canal ou integração relevante | retornar à Concepção e Definição antes da construção |
| mudança de arquitetura, dados sensíveis, risco ou regra regulatória | reconcepção e aprovações de arquitetura/governança obrigatórias |
| incidente emergencial | hotfix com controles mínimos não dispensáveis e revisão/baseline retrospectiva auditável |

O macrofluxo 3 fecha o ciclo:

```text
Conceber -> Construir/Entregar -> Operar/Manter/Evoluir
    ^                                      |
    +---------- nova necessidade ----------+
```

Assim, manutenção não fica escondida em Tasks avulsas e “nova implementação” não contorna produto, escopo, planejamento ou governança. Ambos reutilizam a linha de produção com templates proporcionais ao impacto e ao risco.

## 2.2 Classificação universal do desenvolvimento

> **Decisão registrada (2026-08-01):** esta seção recomenda um único Project por entrega com
> Tracks internos por frente técnica (ver "Projeto híbrido e tracks" abaixo). O ForgeHub
> **optou pelo caminho oposto**: um Project por tipo de aplicação (`Project.solution_type`,
> `backend/app/db/models/project.py`), criados juntos por `:authorize-delivery-planning` a
> partir da mesma Concepção/versão. Cada Project recebe só os elementos do Blueprint cuja
> camada (`FAMILY_LAYER_LABELS`) corresponde ao seu tipo. Motivo: manter o modelo mental atual
> de Project como escopo independente (com seu próprio `working_directory_path`/repositório),
> em vez de introduzir o conceito de Track agora. Limitação conhecida: `web_app` e
> `mobile_app` mapeiam para a mesma camada (`Frontend`) — sem um atributo de plataforma por
> elemento, as mesmas telas entram no escopo dos dois tipos quando ambos são pedidos na mesma
> autorização. Detalhe completo: `docs/modules/01_CONCEPTION_AND_SYSTEM_SCOPE.md`. O restante
> desta seção permanece como referência de arquitetura-alvo caso o modelo de Tracks venha a
> ser adotado depois.

O planejamento deve funcionar para qualquer produto de software: aplicação web, aplicativo mobile, site institucional/e-commerce, API, automação, integração, pipeline de dados, solução de IA, desktop, biblioteca/SDK ou infraestrutura. Para isso, **tipo de projeto e pipeline não podem ser o mesmo conceito**.

Também não se deve confundir **Product** com “aplicação monolítica”. Product é a identidade duradoura daquilo que recebe evolução e versões. Um Project pode entregar o produto inteiro ou somente um recorte do System Blueprint. O menor elemento governável continua rastreável ao Product e à ProductVersion, evitando criar um processo paralelo para telas, componentes ou serviços isolados.

Separação recomendada:

```text
Project Classification
  ├─ Solution Types      o que está sendo construído
  ├─ Delivery Strategy   que natureza de mudança será entregue
  ├─ Target Platforms    onde executa/é distribuído
  └─ Risk Profile        quais controles mínimos são necessários
             ↓
Pipeline Resolver
  ├─ escolhe um template-base
  ├─ inclui tracks técnicos aplicáveis
  ├─ inclui gates impostos por risco/policy
  └─ materializa o ProjectPipeline
```

### Eixos de classificação

| Eixo | Valores iniciais sugeridos | Finalidade |
|---|---|---|
| `solution_type` (M:N) | `web_app`, `mobile_app`, `website`, `api_service`, `automation`, `integration`, `data_pipeline`, `ai_ml`, `desktop_app`, `library_sdk`, `infrastructure` | Determina disciplinas, artefatos e verificações técnicas. Um projeto pode ter vários tipos. |
| `delivery_strategy` (um principal) | `greenfield`, `feature`, `maintenance`, `hotfix`, `migration`, `modernization`, `experiment`, `compliance` | Determina a profundidade e velocidade do fluxo. |
| `target_platform` (M:N) | `browser`, `ios`, `android`, `server`, `cloud`, `on_prem`, `edge`, `marketplace` | Determina build, assinatura, compatibilidade e deploy. |
| `risk_class` | `low`, `standard`, `high`, `critical` | Impõe gates e separação de funções. Não deve reduzir controles abaixo de uma Policy obrigatória. |
| `data_classification` | `public`, `internal`, `confidential`, `restricted` | Define segurança, privacidade, retenção e evidências. |

Esses valores devem ser catálogos controlados e extensíveis, não um único enum gigantesco dentro de `Project`. O vínculo M:N permite classificar corretamente produtos híbridos.

Exemplos:

| Projeto | Classificação | Resultado no pipeline |
|---|---|---|
| Site institucional | `website + greenfield + browser + low` | UX/content, implementação web, SEO/acessibilidade, build e publicação. Não exige migration de dados se não houver persistência. |
| SaaS web | `web_app + api_service + greenfield + browser/server + standard` | UX, API, data, segurança, frontend/backend, testes e deploy. |
| App de entregas | `mobile_app + api_service + feature + ios/android/server + high` | Tracks mobile e backend, device testing, assinatura, store review e rollout. |
| Robô de conciliação | `automation + integration + feature + server + high` | Mapeamento do processo, credenciais, idempotência, observabilidade, dry-run e rollback. |
| Pipeline analítico | `data_pipeline + migration + cloud + high` | Contrato/qualidade de dados, lineage, backfill, reconciliação e rollback. |
| SDK público | `library_sdk + feature + marketplace + standard` | API compatibility, multi-version tests, documentação, package signing e publish. |

### Projeto híbrido e tracks

Um projeto como “lançar o AgendaFácil” pode entregar `web_app`, `mobile_app` e `api_service` na mesma ProductVersion. Não se deve criar três projetos apenas para satisfazer a classificação. O Project continua sendo a unidade de entrega da versão; dentro dele são criados **workstreams/tracks**:

```text
Project AgendaFácil 1.0.0
  ├─ Track Product/UX
  ├─ Track Web
  ├─ Track Mobile
  ├─ Track Backend/API
  ├─ Track Data
  └─ Track Platform/Deploy
```

Os tracks organizam Planning Items, Tasks, Artifact Requirements e stages paralelas. `ProductModule` continua representando a decomposição funcional (`Agenda`, `Clientes`, `Billing`); track representa a disciplina/plataforma (`Mobile`, `Backend`, `Data`). Misturar os dois conceitos dificultaria responder tanto “qual função mudou?” quanto “qual equipe/tecnologia executa?”.

### Relação correta com Templates e Pipelines

- Classificação descreve o projeto.
- Template é uma receita reutilizável compatível com determinada classificação.
- Policy adiciona controles obrigatórios por risco, dados, plataforma ou ambiente.
- ProjectPipeline é a instância materializada e congelada dessa decisão.
- Stage controla a fase.
- Track controla a frente técnica, que pode atravessar ou especializar stages.

Não é recomendável manter um template monolítico para cada combinação possível (`web+mobile+API`, `web+automation`, etc.). Isso causaria explosão de templates. O desenho flexível usa composição:

```text
Core lifecycle
  Context → Definition → Planning → Implementation → Verification → Release

+ solution packs
  Web pack       → UX, accessibility, browser matrix, web build
  Mobile pack    → native design, device matrix, signing, store rollout
  Automation pack→ process map, dry-run, idempotency, scheduler/credentials
  Data pack      → contracts, lineage, quality, reconciliation
  API pack       → API contract, compatibility, integration/security tests

+ policy packs
  Restricted data → privacy/security approvals
  Production      → release approval, rollback and smoke evidence
```

O resolvedor deve gerar uma prévia antes da instanciação: fases incluídas, fases omitidas, tracks paralelos, artefatos, gates e justificativa. O usuário aprova essa configuração junto do plano. Depois da baseline, mudar classificação ou pipeline exige Change Request.

### Onde cada classificação deve morar

| Nível | Pergunta respondida | Exemplo |
|---|---|---|
| Product | “Que tipo de solução este produto é de forma duradoura?” | AgendaFácil possui web app, mobile app e API. |
| ProductModule | “Quais capacidades de negócio existem?” | Agenda, Clientes, Billing. |
| Project | “Qual recorte e estratégia esta entrega usa?” | Versão 1.1 adiciona mobile por estratégia feature, risco high. |
| ProjectTrack | “Quais frentes técnicas executarão esse recorte?” | Mobile, Backend/API, Data, QA. |
| PipelineTemplate | “Qual receita é compatível com essa classificação?” | Feature multi-platform v2. |
| PipelineStage | “Em qual fase do ciclo estamos?” | Solution Design, Implementation, Verification. |
| PlanningItem | “Qual mudança de negócio/técnica foi aceita no escopo?” | Reserva recorrente no módulo Agenda, tracks Mobile e Backend. |

No estado-alvo, o Product mantém seus tipos de solução suportados; o Project faz um snapshot dos tipos/plataformas realmente incluídos naquela versão e acrescenta estratégia/risco. Isso evita repetir toda a identidade do produto, mas permite que uma versão entregue somente web enquanto outra introduz mobile.

### Fluxo de interface recomendado

Na criação do projeto, a classificação deve aparecer antes da escolha do pipeline:

1. Selecionar Product e ProductVersion.
2. O sistema pré-carrega os solution types e módulos cadastrados no Product.
3. Selecionar o recorte da entrega, estratégia, plataformas, risco e classificação de dados.
4. O resolvedor sugere template-base, packs, tracks, artefatos e gates.
5. A tela mostra uma explicação: “incluído porque…” e “não aplicável porque…”.
6. O usuário ajusta apenas opções permitidas pelas Policies.
7. Confirmar cria ProjectPlan draft e ProjectPipeline draft.
8. Aprovar o plano/baseline congela classificação, versão do template e pipeline resolvido.

Para facilitar o uso, a tela inicial pode ter escolhas simples (“Web”, “Mobile”, “Site”, “Automação”, “Dados/IA”, “Outro”) e abrir detalhes progressivamente. Internamente, porém, o sistema persiste os eixos separados. Uma única lista chamada `project_type` seria fácil na primeira tela, mas insuficiente para projetos reais e híbridos.

### Atributos propostos

Novas estruturas recomendadas:

| Estrutura | Atributos principais |
|---|---|
| `development_types` | `key`, `name`, `description`, `is_active` |
| `project_development_types` | `project_id`, `development_type_id`, `is_primary` |
| `project_targets` | `project_id`, `platform`, `minimum_version`, `distribution_channel` |
| `project_classification` | `project_id`, `delivery_strategy`, `risk_class`, `data_classification` |
| `project_tracks` | `project_id`, `key`, `name`, `track_type`, `owner`, `status` |
| `planning_item_tracks` | `planning_item_id`, `track_id` |
| `pipeline_template_applicability` | `template_version_id`, filtros de classificação e prioridade |
| `pipeline_stage_tracks` | `pipeline_stage_id`, `track_id`, `is_required` |

Regras:

1. Todo Project tem ao menos um `solution_type`, uma `delivery_strategy` e um `risk_class`.
2. Apenas um solution type é primário; os demais são componentes da solução.
3. O template selecionado precisa declarar compatibilidade ou exigir override justificado.
4. Policies podem acrescentar stages/gates, nunca ser removidas silenciosamente pelo template.
5. Classificação e pipeline resolvido entram na baseline.
6. Planning Item precisa de ao menos um módulo funcional ou track, quando aplicável.
7. Um stage genérico pode servir a todos os tracks; stages especializados indicam seu track.

### O que existe hoje

O modelo atual não possui tipo de desenvolvimento, estratégia, plataforma, risco de projeto nem tracks. `stage_type` é texto livre e não substitui essa classificação. Portanto, hoje a escolha do pipeline precisa ser feita manualmente e registrada na descrição do Project/ProjectPlan. A implementação dessa classificação deve preceder a automação de seleção de templates.

## 2.3 Escopo do sistema: mapa completo do que será construído

Classificação e pipeline respondem, respectivamente, **que tipo de entrega é esta** e **como ela será produzida**. Ainda falta uma terceira dimensão: **quais partes concretas formam o sistema e quais delas entram nesta entrega**.

Essa dimensão é o **System Blueprint**, ou Mapa do Sistema. Ela deve existir antes da decomposição em Planning Items e Tasks. Sem esse mapa, o ForgeHub consegue controlar trabalho, mas não consegue provar se todas as telas, processos, regras, APIs, dados e unidades de deploy necessárias foram contempladas.

Escopo e linha do tempo não são sinônimos:

- o **escopo** é um grafo versionado dos elementos do sistema e suas relações;
- a **linha do tempo** mostra o estado de desenvolvimento de cada elemento desse grafo;
- o **pipeline** define os gates pelos quais a mudança passa;
- Planning Items e Tasks descrevem o trabalho necessário para criar ou alterar os elementos;
- Release e Delivery comprovam quais versões dos elementos chegaram a cada ambiente.

### Visão gráfica ponta a ponta

```text
Necessidade / Objetivo
  -> Capability / ProductModule
    -> Persona + Jornada / Processo
      -> Passo / Caso de uso
        -> Canal ou superfície
          -> Tela / Rota / Componente / Comando / Job
            -> Contrato de entrada e saída
              -> Regra de negócio + Policy de acesso/compliance
                -> API / Evento / Integração
                  -> Serviço / Classe / Método / Handler
                    -> Entidade de domínio
                      -> Repositório / Query / Procedure
                        -> Schema / Tabela / Campo / Índice
                          -> Runtime / Serviço / DeploymentUnit
                            -> Ambiente / Release / Deployment
                              -> Telemetria + evidência operacional
```

Essa linha representa rastreabilidade, não uma obrigação de implementação sequencial. Frontend, backend, dados, segurança e infraestrutura podem avançar em paralelo quando os contratos e dependências permitirem.

Nem todo produto percorre todos os nós. Uma automação pode não ter tela; um site estático pode não ter banco; uma biblioteca pode terminar em package registry; um projeto de pesquisa pode terminar em relatório e ADR. A classificação do projeto determina quais categorias são obrigatórias, opcionais ou não aplicáveis.

### Níveis do mapa

| Nível | Elementos | Pergunta respondida |
|---|---|---|
| Negócio | objetivo, stakeholder, persona, capability, ProductModule | Por que existe e para quem? |
| Experiência e processo | jornada, processo, passo, caso de uso, cenário | O que o usuário ou sistema precisa realizar? |
| Superfície | aplicação, canal, rota, tela, relatório, formulário, componente, CLI | Onde a interação acontece? |
| Contrato | ação, comando, query, API, endpoint, evento, webhook, integração | Como as partes se comunicam? |
| Domínio e governança | entidade, value object, regra de negócio, autorização, Policy, decisão | Que comportamento e restrições são obrigatórios? |
| Aplicação | serviço, handler, classe, método, workflow, job | Qual unidade executa o caso de uso? |
| Dados | datastore, schema, tabela, campo, índice, view, procedure, migration | Como o estado é persistido ou consultado? |
| Operação | runtime component, fila, cache, secret ref, deployment unit, ambiente | Onde e com quais dependências executa? |
| Observabilidade | métrica, log, trace, alerta, SLO, health/smoke check | Como saber se funciona após a entrega? |

“Backend” não deve ser reduzido a acesso ao banco. Ele contém contratos de aplicação, domínio, integrações e infraestrutura; o acesso a dados é apenas uma camada. “Policy” também não é somente permissão de tela: pode impor regra de negócio, autorização, privacidade, retenção, segurança, custo ou operação. Classes e métodos pertencem ao inventário de implementação e podem ser sincronizados do código; casos de uso, regras e contratos precisam existir antes deles no planejamento.

### Estrutura de dados recomendada

O núcleo deve ser tipado, mas extensível. Uma única árvore `ProjectStructureNode` não é suficiente porque processos cruzam telas e serviços, uma tela usa várias APIs e uma entidade pode persistir em várias estruturas. Essas relações formam um grafo.

| Estrutura | Atributos principais | Finalidade |
|---|---|---|
| `system_blueprints` | `product_id`, `name`, `current_revision_id` | identidade duradoura do mapa do Product |
| `system_blueprint_revisions` | `blueprint_id`, `revision`, `status`, `concept_revision_id` opcional, `product_version_id` opcional, `content_hash` | snapshot imutável do mapa, inclusive durante concepção anterior à ProductVersion |
| `system_elements` | `product_id`, `stable_key`, `element_type`, `name`, `description`, `lifecycle_status`, `criticality`, `owner_ref`, `parent_id` opcional | catálogo duradouro de elementos lógicos e físicos do Product |
| `system_element_revisions` | `system_element_id`, `blueprint_revision_id`, `spec_snapshot`, `source_ref`, `content_hash`, `status` | definição imutável do elemento naquela revisão do mapa |
| `system_element_relations` | `blueprint_revision_id`, `from_element_id`, `to_element_id`, `relation_type`, `attributes` | grafo de dependência, uso, navegação, persistência, execução e deploy naquela revisão |
| `project_scopes` | `project_id`, `blueprint_base_revision_id`, `revision`, `status`, `content_hash` | identidade e revisão do delta de entrega, separada do texto livre do plano |
| `project_scope_items` | `project_scope_id`, `system_element_id`, `base_element_revision_id` opcional, `target_element_revision_id` opcional, `change_type`, `scope_status`, `rationale` | recorte do mapa incluído na entrega: add/modify/remove/deprecate/verify |
| `scope_item_acceptance_criteria` | `project_scope_item_id`, `criterion`, `verification_type`, `required` | aceite por elemento do escopo |
| `planning_item_scope_items` | `planning_item_id`, `project_scope_item_id`, `coverage_role` | liga demanda planejada aos elementos afetados |
| `task_scope_items` | `task_id`, `project_scope_item_id`, `work_role` | declara exatamente o que cada Task implementa, testa, documenta ou implanta |
| `artifact_scope_items` | `artifact_version_id`, `project_scope_item_id`, `evidence_role` | liga especificações e evidências às partes cobertas |
| `release_scope_manifest` | `release_candidate_id`, `project_scope_item_id`, `element_version_id`, `evidence_ref` | congela o conjunto entregue |
| `deployment_scope_results` | `deployment_id`, `project_scope_item_id`, `status`, `verification_ref` | comprova o resultado por elemento no ambiente |

`system_elements.element_type` deve começar com um catálogo controlado por famílias, sem transformar tudo em texto livre:

```text
business:     capability, module, persona
process:      journey, process, process_step, use_case
experience:   application, channel, route, screen, form, report, ui_component
interface:    api, endpoint, command, query, event, webhook, integration
domain:       domain_entity, value_object, business_rule, authorization_rule
application:  service, handler, class, method, workflow, job
data:         datastore, schema, table, field, index, view, procedure, migration
runtime:      runtime_component, queue, cache, deployment_unit, environment_target
assurance:    test_scenario, metric, log_signal, alert, slo, health_check
```

Tipos que exigem atributos próprios podem ganhar tabelas especializadas — por exemplo `screen_specs`, `api_endpoint_specs`, `business_rule_specs`, `data_structure_specs` e `deployment_unit_specs` — mantendo `system_elements` como identidade e ponto comum de rastreabilidade. Isso evita tanto uma tabela universal sem validação quanto dezenas de domínios isolados sem relações.

### Relações controladas

As relações também precisam de semântica explícita. Conjunto inicial:

| Relação | Exemplo |
|---|---|
| `contains` | módulo contém capability; tela contém componente |
| `precedes` | passo A precede passo B no processo |
| `navigates_to` | tela Login navega para Dashboard |
| `invokes` | formulário invoca endpoint |
| `implements` | handler implementa caso de uso |
| `governed_by` | endpoint é governado por Policy de autorização |
| `reads` / `writes` | serviço lê/escreve entidade ou tabela |
| `emits` / `consumes` | serviço emite/consome evento |
| `depends_on` | componente depende de contrato/serviço |
| `persists_as` | entidade é persistida em tabela/procedure |
| `runs_on` | serviço executa em deployment unit |
| `deployed_to` | deployment unit é entregue em ambiente |
| `verified_by` | elemento é coberto por cenário/check/evidência |

### Linha do tempo por elemento

Cada `ProjectScopeItem` deve possuir cobertura calculada, e não um único status digitado manualmente:

```text
identified
  -> specified
  -> designed
  -> planned
  -> implementation_in_progress
  -> implemented
  -> verified
  -> release_ready
  -> released
  -> deployed/activated/published
  -> operationally_verified
```

O estado é derivado dos registros existentes:

| Marco | Evidência mínima |
|---|---|
| identified | elemento incluído no ProjectScope |
| specified | ArtifactVersion de requisito/especificação aprovada |
| designed | contratos e design aplicáveis aprovados |
| planned | Planning Item baselined e Tasks prontas |
| implemented | Tasks de implementação concluídas com evidência |
| verified | cenários e reviews obrigatórios aprovados |
| release_ready | stage/gates e manifesto do candidato completos |
| released | elemento presente em Release aprovada |
| delivered | Deployment/Publication/Activation bem-sucedida |
| operationally_verified | smoke, health, telemetria ou aceite pós-entrega aprovado |

Uma tela, por exemplo, só aparece como “completa” quando sua especificação, componentes, ações, regras, endpoints, persistência aplicável, testes e evidência de entrega atingirem os marcos exigidos. Isso permite uma matriz visual por linha do sistema e coluna do ciclo:

```text
Elemento             Spec  UX  API  Rule  Data  Code  Test  Release  Deploy
Login                 done  done done done  n/a   done  done  ready    pending
Dashboard             done  wip  wip  done  done  wip   pending -        -
Importação noturna    done  n/a  n/a  done  done  done  failed -        -
```

A interface deve permitir expandir uma linha: ProductModule → processo → tela/job → ação → API → regra → entidade → tabela → deployment unit. A mesma informação também deve ter visão por jornada, por módulo, por stage, por track e por ambiente.

### Experiência de uso no ForgeHub

O Mapa do Sistema deve ser um módulo próprio no contexto de Product/Project, e não um formulário gigante. Conjunto mínimo de telas:

| Tela | Rota sugerida | Responsabilidade |
|---|---|---|
| System Map | `/products/{id}/system-map` | grafo navegável de módulos, processos, superfícies, contratos, domínio, dados e runtime |
| Element Catalog | `/products/{id}/system-elements` | inventário filtrável, ciclo de vida, owner, criticidade e versões de cada elemento |
| Process Designer | `/products/{id}/processes/{element_id}` | fluxo de jornadas/processos com passos, atores, decisões, telas, jobs e integrações participantes |
| Element Detail | `/products/{id}/system-elements/{element_id}` | especificação, relações upstream/downstream, versões, regras, artifacts e histórico |
| Project Scope | `/projects/{id}/scope` | seleção do delta add/modify/remove/verify e critérios de aceite da entrega |
| Coverage Matrix | `/projects/{id}/coverage` | linhas do escopo x marcos Spec/Design/Code/Test/Release/Delivery, com lacunas e bloqueios |
| Traceability | `/projects/{id}/traceability` | caminho completo objetivo → elemento → planning → task → execution → artifact → release → ambiente |
| Release Scope | `/releases/{id}/scope` | manifesto exato de elementos/versões e evidências incluídas |

Na primeira versão, `System Map`, `Project Scope` e `Coverage Matrix` formam a fatia mínima. As demais podem começar como abas/drawers dessas três telas e ser separadas quando o volume justificar.

Fluxo recomendado de cadastro e planejamento:

```text
Product
  -> importar ou cadastrar módulos/capabilities
  -> desenhar jornadas e processos
  -> associar telas, jobs, APIs, regras, entidades, dados e runtime
  -> validar elementos órfãos e relações ausentes
ProductVersion + Project
  -> selecionar o delta do mapa
  -> revisar impactos calculados
  -> resolver pipeline, tracks, policies, artifacts e testes necessários
  -> gerar Planning Items e Tasks com cobertura explícita
  -> baselinar
Execution
  -> acompanhar matriz de cobertura
  -> revisar evidências por elemento
Release/Delivery
  -> congelar manifesto
  -> entregar e verificar no ambiente
```

O sistema deve destacar automaticamente:

- tela sem processo ou caso de uso;
- ação de tela sem contrato/API local;
- endpoint sem regra de autorização quando a classificação exigir;
- regra sem cenário de teste;
- entidade sem estratégia de persistência, ou marcada explicitamente como transitória;
- tabela sem owner lógico/entidade ou justificativa técnica;
- job/evento sem observabilidade e tratamento de falha;
- deployment unit sem health check, rollback ou ambiente-alvo;
- elemento em escopo sem Planning Item, Task, ArtifactVersion ou evidência obrigatória.

### Baseline e controle de mudança

O Product mantém o mapa duradouro. Durante a concepção, `SystemBlueprintRevision` pode apontar para `ConceptRevision` antes de existir ProductVersion. Após Concept Approval, a ProductVersion adota uma revisão aprovada como base; o Project seleciona o delta que será entregue e produz revisões posteriores. A baseline congela:

1. elementos incluídos e excluídos;
2. tipo de mudança de cada elemento;
3. relações afetadas;
4. critérios de aceite;
5. pipeline, tracks, policies e staffing aplicáveis;
6. cobertura planejada por Planning Items, Tasks e artefatos.

Adicionar uma tela, processo, integração, regra ou tabela depois da baseline exige Change Request. Descobrir uma classe ou método interno durante a implementação não exige automaticamente mudança de escopo; exige quando altera contrato, comportamento aprovado, risco, custo ou prazo.

### Regras de integridade do escopo

1. Todo ProjectScopeItem pertence ao Product alcançado por `Project -> ProductVersion -> Product`.
2. Todo elemento lógico tem `stable_key` único no Product e histórico por ProductVersion.
3. Relações só podem ligar elementos compatíveis e pertencentes ao mesmo Product, salvo integração externa explicitamente marcada.
4. Todo Planning Item baselined cobre ao menos um ProjectScopeItem, exceto trabalho administrativo justificado.
5. Toda Task técnica declara os elementos que implementa, verifica, documenta ou implanta.
6. Todo elemento em escopo possui critério de aceite ou justificativa `not_applicable`.
7. Elemento obrigatório não chega a `verified` sem evidências previstas pela classificação e Policies.
8. Release Candidate contém versões exatas dos elementos e suas evidências; não apenas uma lista de Tasks.
9. Delivery atualiza a cobertura somente dos elementos presentes no manifesto entregue.
10. Exclusão física de elemento com histórico é proibida; usar `deprecated` ou `removed` por versão.

### Relação com o modelo existente

- `ProductModule` deve evoluir para a camada de capability/módulo, não ser substituído por pastas.
- `ProjectStructureNode` é um protótipo útil do inventário técnico, mas sua árvore e seus seis tipos atuais não representam processos e relações transversais. Deve ser migrado ou projetado como compatibilidade sobre `system_elements`.
- `PlanningItem.structure_node_id` aceita somente um alvo; deve virar associação M:N com ProjectScopeItems.
- `ArtifactType` já reconhece tela, componente, schema, tabela e procedure, mas classifica entregáveis; não representa a identidade persistente do elemento do sistema.
- PipelineStage organiza quando o trabalho ocorre; não deve ser usado como catálogo das partes do produto.
- Policy e BusinessRule precisam apontar para elementos governados e ser avaliadas no contexto da ação, ambiente e versão.
- Release e Deployment precisam consumir o manifesto do escopo para fechar a rastreabilidade até produção.

### O que existe hoje

Existe uma base parcial: ProductModule, árvore ProjectStructureNode, vínculo único de PlanningItem com structure node, tipos finos de Artifact e a cadeia ProductVersion/Project/Pipeline/Task. Ainda não existem System Blueprint, relações em grafo, delta versionado do escopo, cobertura M:N, critérios por elemento nem matriz de progresso. Portanto, o ForgeHub atual não consegue listar todas as telas e processos de um produto nem provar, por elemento, o caminho completo da especificação ao deploy.

## 3. Responsabilidade de cada módulo

### 3.1 Products — identidade e evolução do produto

**Responsabilidade:** registrar o software duradouro, seus módulos funcionais e suas versões semânticas.

Entidades atuais:

| Entidade | Atributos atuais | Avaliação |
|---|---|---|
| `Product` | `name`, `description`, `status` | A identidade está correta. `name` é único e `status` tem conjunto fechado. |
| `ProductModule` | `product_id`, `name`, `description` | Insuficiente para planejamento modular: faltam `code/slug`, owner, criticidade, estado, dependências e vínculo opcional com nós reais da estrutura. |
| `ProductVersion` | `product_id`, `version`, `status`, `release_notes` | Boa raiz para o escopo de versão, mas `version` aceita qualquer string, transições não são formalizadas e `release_notes` mistura versão planejada com release efetiva. |
| `Release` | `product_version_id`, `name`, `status`, `notes` | Muito simples para governar release: não agrega commit/tag, artefatos, aprovações, ambiente, data, rollback ou deployments. |

Regras corretas já existentes:

- produto é criado com uma versão inicial;
- nome do produto e versão dentro do produto são únicos;
- a última versão não pode ser excluída;
- versão publicada não pode ser editada diretamente.

Melhorias necessárias:

1. Validar SemVer e suportar `major`, `minor`, `patch`, pre-release e build metadata.
2. Aplicar uma máquina de estados: `planned → in_development → in_test → published → deprecated`.
3. Impedir publicação sem Release pronta e sem pipeline aprovado.
4. Definir se um Project entrega exatamente uma ProductVersion. O modelo atual diz que sim; essa decisão é adequada para a primeira versão do ForgeHub.
5. Criar associação de escopo entre `ProductModule` e `PlanningItem`; o módulo funcional não deve ser inferido somente por pasta.

### 3.2 Projects — unidade controlada de entrega

**Responsabilidade:** delimitar a iniciativa que entregará uma versão, seu repositório, owner, datas, plano aprovado e mudanças posteriores.

Entidades atuais:

| Entidade | Atributos atuais | Avaliação |
|---|---|---|
| `Project` | versão, owner, status, datas, diretório, GitHub, backup | A associação obrigatória à versão está correta. A API não valida explicitamente a existência da versão antes de gravar; hoje depende da FK. |
| `ProjectPlan` | nome, resumo de escopo, datas estimadas, custo, status | É um cabeçalho de planejamento, não um plano completo. Faltam objetivos, entregáveis, riscos, premissas, critérios de sucesso e composição explícita dos itens incluídos. |
| `PlanBaseline` | snapshot de escopo, custo e data final | A ideia de snapshot imutável é correta, mas o snapshot é incompleto: não congela planning items, pipeline/template, módulos, riscos, estimativas e critérios de aceite. |
| `ChangeRequest` | justificativa, flags de impacto, deltas e status | Boa classificação inicial. Falta descrever o delta estruturado, aprovar por Governance, aplicar de forma transacional e gerar uma nova baseline. |
| `ProjectStructureNode` | árvore de pasta/módulo/componente/tela/tabela/procedure, path, lock | Útil como mapa técnico, mas não substitui `ProductModule`. Faltam tipos como API/endpoint/job/event/test/design-token e unicidade de path por projeto. |

Problemas de ciclo de vida:

- um plano aprovado pode ser aprovado de novo;
- podem ser criadas várias baselines para o mesmo plano;
- planos e baselines podem ser excluídos mesmo depois de utilizados;
- uma Change Request pode apontar para baseline de outro projeto;
- transições de Change Request aceitam saltos, por exemplo `pending → applied`;
- aplicar uma Change Request não cria nova revisão do plano nem nova baseline.

Modelo-alvo:

- `ProjectPlanRevision` versionada;
- `PlanBaseline` única por revisão, com snapshot JSON canônico e hash;
- tabela de composição `plan_scope_items` ligando baseline a Planning Items;
- Change Request com `before_snapshot`, `proposed_delta`, decisão, tarefas derivadas e baseline resultante;
- owner por `user_id`/`agent_id`, preservando nome apenas como snapshot de exibição.

### 3.3 Pipeline Templates — receita reutilizável

**Responsabilidade:** definir a receita de produção para uma classe de trabalho: produto novo, feature, hotfix, migração, pesquisa ou mudança de infraestrutura.

O template atual guarda stages, ordem, flags de aprovação/verificação e tipos de artefato requeridos. Isso é um bom início, mas é um template mutável sem versão. Se for alterado, projetos futuros e a interpretação histórica ficam ambíguos.

O template-alvo deve possuir:

- `template_key` estável e `version` imutável;
- status `draft|published|deprecated`;
- tipo de fluxo (`standard`, `feature`, `hotfix`, `data_migration`, `research`);
- critérios de entrada e saída por stage;
- papéis autorizados para aprovar/verificar;
- políticas aplicáveis;
- artefatos requeridos com tipo, cardinalidade, aprovação e regra de atualização;
- estratégia de execução: sequencial, paralela ou dependente;
- SLA opcional e instruções para agentes.

Publicar uma nova revisão deve criar uma nova versão do template, nunca alterar a receita já usada por projetos.

### 3.4 Project Pipelines — linha de produção do projeto

**Responsabilidade:** materializar uma versão do template no projeto e controlar em qual fase cada trabalho está.

O que funciona hoje:

- pipeline pertence a Project;
- a API desativa outros pipelines ao ativar um novo;
- stages têm ordem, dependências, artefatos requeridos e gates;
- conclusão de stage verifica dependências, `is_fulfilled` e gates obrigatórios;
- a conclusão produz `AuditEvent`.

Lacunas críticas:

1. Não há índice único parcial garantindo no banco um pipeline ativo por projeto; requisições concorrentes podem quebrar a regra.
2. Criar Project não cria/obriga pipeline ativo.
3. Informar `template_id` não instancia automaticamente os stages do template; o chamador precisa copiá-los.
4. A criação aninhada aceita dependências por UUID de stages preexistentes e não consegue referenciar de forma natural os novos stages do mesmo payload.
5. `status` de pipeline/stage é texto livre; não há máquina de transição.
6. É possível editar ordem, tipo, requisitos e gates de um pipeline em andamento sem Change Request ou revisão.
7. Apenas ciclos diretos são parcialmente tratados; não há detecção completa de ciclos no grafo de stages.
8. `requires_approval` e `requires_verification` duplicam informação dos gates e podem divergir deles.
9. Um requisito pode ser marcado `is_fulfilled=true` manualmente sem provar que o artefato existe, tem o tipo correto e está aprovado.
10. Não existe associação entre Task e PipelineStage. Portanto o sistema não sabe quais tarefas pertencem a uma fase nem consegue afirmar que uma fase terminou por execução.

Estados-alvo:

```text
Pipeline: draft → active → completed
                    ├→ suspended
                    └→ cancelled

Stage: pending → ready → in_progress → in_review → completed
                    └→ blocked          └→ rejected → in_progress
                    └──────────────────────────────→ skipped (com aprovação)
```

Uma stage só fica `ready` quando todas as dependências estão concluídas. Só fica `completed` quando:

- todas as tasks obrigatórias estão `done` ou `deployed`, conforme a fase;
- todas as execuções exigidas estão verificadas;
- todos os artefatos requeridos foram resolvidos por consulta, não por booleano manual;
- todas as policies aplicáveis passaram;
- gates obrigatórios possuem Approval válida.

### 3.5 Planning — decidir o que entra na versão

**Responsabilidade:** transformar demanda em escopo versionado antes da execução.

O `PlanningItem` atual possui tipo, status, prioridade, projeto, versão alvo, nó estrutural, output path e flag de baseline. Há também intake especializado para feature/bug, triagem e associação de versão.

Pontos corretos:

- item precisa de Project na API;
- intake e triagem são separados;
- item baselined não pode ser editado diretamente;
- histórico de decisões de triagem é append-only.

Lacunas:

- `project_id` é nullable no banco embora obrigatório na API;
- `target_version_id` e `VersionScopeItem.product_version_id` não são verificados contra a versão do Project;
- um item pode ser associado a várias versões, mas também possui um único `target_version_id`; as duas fontes podem divergir;
- `structure_node_id` só é verificado por existência, não por pertencer ao mesmo Project;
- prioridade não tem enum/check;
- status pode ser alterado diretamente sem validar transição;
- `baselined` e `status=baselined` são duas fontes de verdade;
- não há `product_module_id`, stage planejado, critérios de aceite, Definition of Done, estimativa, risco, dependências ou owner;
- a baseline do ProjectPlan não congela a lista de Planning Items.

Decisão recomendada:

- manter `PlanningItem` como unidade de escopo;
- remover a ambiguidade escolhendo uma única associação de versão. Como Project já pertence a uma versão, `target_version_id` deve ser derivado e validado, ou eliminado;
- criar `planning_item_modules` para permitir impacto em mais de um módulo;
- criar `stage_work_items(stage_id, planning_item_id, required)`;
- criar `acceptance_criteria` estruturados e versionados;
- baselinar por associação imutável, não por booleano no item.

### 3.6 Execution — trabalho executado e comprovado

**Responsabilidade:** decompor escopo em tasks, atribuir executor, registrar cada tentativa, revisar e concluir.

O modelo atual separa corretamente `ProjectTask`, `TaskAssignment` e `TaskExecution`. Também suporta subtasks, dependências, skills, custo, múltiplas tentativas e evidência. Toda execução é despachada nativamente via o canal Messages (`AgentDemand`), sem depender de um board externo (Kanboard foi descontinuado e removido do ForgeHub em 2026-07-28).

Lacunas críticas:

- `ProjectTask` não possui `project_id`, `pipeline_stage_id` nem `product_module_id`; tudo é inferido pelo PlanningItem e uma task de Change Request pode não ter caminho direto para stage;
- parent e dependências são validados por existência, não por pertencer ao mesmo projeto/stage;
- a verificação de dependência para conclusão considera apenas status `done`; uma dependência `deployed` é rejeitada;
- a regra documentada “task done exige execução completed/verified” não é aplicada em `update_task`;
- a task pai pode terminar com subtasks incompletas;
- ciclos com três ou mais tasks não são detectados;
- criar assignment não valida existência, atividade, capacidade ou skills do agente e não impede múltiplas assignments ativas;
- estados de assignment/execution são texto livre no banco;
- `attempt_number = count + 1` pode colidir em concorrência e não possui unique constraint;
- `started_at`, `finished_at`, `completed_at` e custos não são mantidos de forma consistente pelas transições;
- `verified` e `completed` na execução têm semântica sobreposta. O ideal é `completed` pelo executor e `verified` pelo revisor, em sequência;
- audit é gerado novamente em PATCH repetido para o mesmo estado.

Modelo-alvo mínimo para Task:

```text
project_id              obrigatório e denormalizado para consulta/segurança
pipeline_stage_id       obrigatório para trabalho de entrega
planning_item_id        obrigatório, exceto tarefa criada por Change Request
change_request_id       opcional
product_module_id       opcional ou M:N
title / description
acceptance_criteria     estruturado
definition_of_done      estruturado
task_type / priority / risk
status
review_required
planned/actual dates and cost
```

Fluxo recomendado:

```text
planned --Execution Release--> ready → assigned → in_progress → in_review → done → deployed
                              ├→ blocked      └→ changes_requested → in_progress
                              └→ failed/retry (na execução, não na task)
qualquer estado não final → cancelled (com motivo)
```

Uma Task `planned` pertence ao plano, mas não pode ser despachada. A liberação para `ready` ocorre somente depois da baseline e de um preflight de planejamento. Tasks podem ser liberadas em ondas por Stage, track, módulo, sprint ou conjunto de dependências; a onda preserva quem autorizou, critérios usados, orçamento/WIP e lista imutável de Tasks.

### 3.7 Artifacts — entregáveis, especificações e evidências

**Responsabilidade:** controlar o conteúdo versionado que entra e sai de cada fase.

Tipos atuais cobrem PRD, SPEC, data spec, regras de negócio, segurança, código, migration, teste, release notes, PR, pacote de deploy, aprovação, tela, componente, relatório, schema, tabela, procedure e documentos de referência.

Tipos que devem ser adicionados ou formalizados:

- `apr` — confirmar o significado no negócio; se for Architecture/Approval/Analysis Proposal Record, não confundir com ADR;
- `adr`;
- `api_contract`/OpenAPI;
- `domain_model`;
- `data_model` separado de schema físico;
- `wireframe`, `screen_spec`, `user_flow`;
- `design_system`, `design_token`, `component_catalog`;
- `business_rule_catalog`;
- `test_plan`, `test_case`, `test_evidence`;
- `threat_model`, `sbom`, `build`, `commit`, `tag`, `rollback_plan`.

Pontos corretos:

- Artifact e ArtifactVersion são separados;
- versão tem URI, checksum e produtor;
- lock impede alteração acidental;
- aprovação/rejeição e auditoria existem.

Lacunas:

- Artifact não possui vínculo obrigatório com Product, versão ou Project;
- links com stage e execução são opcionais, permitindo entregáveis órfãos;
- não há `current_version_id`; “versão corrente” é inferida;
- “exatamente uma current” citada na docstring não é garantida pelo modelo;
- versões antigas não são automaticamente superseded quando outra vira final;
- aprovação acontece no Artifact, mas não identifica inequivocamente qual ArtifactVersion foi aprovada;
- `requires_approval` pode divergir da existência de Policy/Gate;
- checksum é opcional e algoritmo não é registrado;
- URI não é validada contra o diretório do Project;
- o requisito de stage usa `artifact_type` string, enquanto Artifact usa enum nativo; os vocabulários podem divergir;
- `is_fulfilled` não é derivado da aprovação da versão vinculada.

Modelo-alvo:

- Artifact é o conceito lógico e pertence obrigatoriamente a Project/ProductVersion;
- ArtifactVersion é a unidade imutável revisada e aprovada;
- `Artifact.current_version_id` aponta para a revisão vigente;
- uma tabela `stage_artifact_bindings` resolve cada requisito para uma versão exata;
- aprovação aponta para `artifact_version`;
- checksum obrigatório para arquivos finais;
- conteúdo publicado/approved nunca é editado: nova mudança cria nova versão.

### 3.8 Governance e Policies — regras executáveis e decisões

**Responsabilidade:** declarar regras, avaliar conformidade, registrar decisões humanas e preservar auditoria.

O modelo atual possui Policy com JSON livre, Approval polimórfica e AuditEvent append-only. Isso funciona como registro, não como motor de governança.

Lacunas:

- `policy_type`, `entity_type`, `approval_type`, status e formato de `rules` são livres;
- Policy pode apontar para entidade inexistente e não possui escopo por produto/projeto/stage/ambiente com precedência definida;
- não há versão de Policy nem período de vigência;
- não há `PolicyEvaluation` guardando resultado, inputs e evidências;
- Approval não possui `decided_at`, expiração, grupo/papel requerido ou separação de funções;
- Approval e PipelineStageGate são fluxos paralelos: aprovar um não aprova o outro;
- gate guarda `approved_by` diretamente, duplicando a decisão de Governance;
- a API de gate não cria Approval/AuditEvent;
- AuditEvent cobre apenas parte das transições e `actor` costuma ser `system`, sem identidade real;
- referências polimórficas não têm integridade referencial e precisam de validadores/registry.

Arquitetura-alvo:

```text
PolicyDefinition(versionada)
  └─ PolicyBinding(scope_type, scope_id, stage_type/environment, precedence)
       └─ PolicyEvaluation(result, evaluated_at, input_hash, evidence)

PipelineStageGate
  └─ ApprovalRequest
       └─ ApprovalDecision(s) por usuário/papel
```

Gate deve ser uma projeção do resultado de approvals/evaluations, nunca uma segunda fonte de decisão.

### 3.9 Release e Deploy — o que realmente entrou em produção

**Responsabilidade:** fechar a cadeia entre versão aprovada, pacote exato e instalação em um ambiente.

Hoje `Release` registra somente nome/status/notas e `DeployInstallation` é um inventário de containers ligado opcionalmente a Product. Não há registro de um evento de deployment.

Consequência: o sistema não consegue responder de forma confiável:

- qual release está em homologação ou produção;
- qual commit, imagem ou migration foi implantado;
- quais tasks e artefatos entraram;
- quem aprovou e executou;
- se o deployment passou em smoke test;
- como fazer rollback.

Modelo-alvo:

- `Environment`: dev, test, staging, production, com classificação e políticas;
- `ReleaseCandidate`: versão + pipeline + conjunto imutável de ArtifactVersions;
- `Release`: candidato aprovado, tag/commit, release notes e Approval;
- `Deployment`: release, environment, instalação/alvo, status, executor e timestamps;
- `DeploymentArtifact`: imagem, manifest, migrations e checksums;
- `DeploymentEvidence`: logs, smoke tests, health checks e rollback evidence;
- `Deployment.status`: `planned → approved → deploying → succeeded|failed → rolled_back`.

`ProjectTask.status=deployed` só deve ocorrer quando a Release que contém a task tiver um Deployment `succeeded` no ambiente-alvo.

### 3.10 Agents — equipe planejada, atribuição e execução real

**Responsabilidade:** usar os agentes já cadastrados como recursos governados do desenvolvimento, associando-os ao Project, aos tracks/stages, às Tasks, às execuções e às revisões.

O catálogo atual já oferece:

- `Agent`: nome, tipo (`coordinator|executor|hybrid`), status e metadados Hermes;
- `SubAgent`: agente pai, permission scope e status;
- `Skill`, `AgentSkill` e `SubAgentSkill`;
- `AgentCostRate` e `AgentCapacity`;
- `TaskRequiredSkill`;
- `TaskAssignment` para Agent ou SubAgent;
- `TaskExecution` opcionalmente ligada a uma Assignment.

Isso é uma boa base de catálogo, mas ainda não constitui planejamento de equipe.

#### Primeira fatia implementada em 2026-07-11

O ForgeHub agora implementa o núcleo do modelo descrito nesta seção:

- `AgentRuntimeProfile`: runtime Claude/Codex/Agy, classe semântica do ForgeRouter, `model_ref` opcional para fixação avançada, finalidade, escopo e orçamento;
- `ProjectAgentMembership`: agente cadastrado autorizado no Project, papel, allocation, runtimes permitidos e capacidade de review/approval;
- `ProjectLoopPolicy`: produtor e reviewer distintos, seus perfis ForgeRouter, nota mínima, limite de iterações, aprovação humana e correção automática opcional;
- `TaskAssignment.membership_id` e metadados de runtime/loop em `TaskExecution`;
- `TaskExecutionReview` com score, feedback, evidência e decisão imutável;
- elegibilidade por Project, status/período e skills obrigatórias aprovadas;
- runner host assíncrono, limitado a Claude/Codex/Agy e sem comando shell arbitrário;
- despacho, consulta de estado, review read-only e redispatch de correção até `max_iterations`;
- telas de Project para configurar equipe/perfis/policies e de Task para atribuir/despachar/revisar.

O ForgeRouter continua sendo o gateway padrão e `auto` é o perfil principal recomendado. O planejamento pode fixar a classe pela natureza do trabalho: `simple` para utilitários curtos e baratos; `standard` para chat, resumos e tool calls rotineiras; `complex` para contexto longo e trabalho multietapas; `reasoning` para provas, planejamento e diagnóstico profundo; `vision` para imagens; `audio` para TTS e transcrições; `code` para geração e edição de código. No modo `auto`, a ordem é: imagem → `vision`; sinal de código → `code`; dica explícita de raciocínio → `reasoning`; caso contrário, tamanho aproximado (<1,5 mil caracteres → `simple`; <8 mil → `standard`; acima → `complex`), com histórico pesando 1/4 e presença de tools elevando o mínimo para `standard`. O `model_ref` só deve ser diferente de `forgerouter/auto` quando houver motivo para fixar um modelo concreto. Credenciais permanecem na configuração local protegida do Project.

#### Lacunas atuais

1. Autorização por track, stage, módulo, path ou ambiente ainda não está estruturada.
2. Allocation existe no Project, mas capacidade concorrente ainda não é calculada no dispatch.
3. Skills são consideradas na lista de elegibilidade, mas a criação direta de Assignment ainda não bloqueia todas as incompatibilidades de skill.
4. Várias assignments ativas ainda podem coexistir para a mesma Task.
5. Execuções manuais legadas ainda podem omitir Assignment; o dispatch automatizado exige Assignment com Membership.
6. O estado do runner fica em memória no host bridge; reinício preserva a TaskExecution no banco, mas perde output ainda não coletado.
7. A aprovação humana de review existe, mas separação avançada por Policy/risco ainda deve ser integrada ao motor de Policies.

#### Conceitos que não devem ser misturados

```text
Agent/SubAgent          quem é responsável e quais capacidades possui
ProjectMembership      em qual projeto pode atuar e com qual papel
TaskAssignment         qual trabalho foi atribuído e em que período
ExecutionRuntime       Codex, Claude CLI, Agy, humano ou sistema usado
TaskExecution          tentativa real, sessão, resultado, custo e evidência
TaskReview             quem revisou e qual foi a decisão
```

Um agente cadastrado pode usar mais de uma CLI, e a mesma CLI pode executar trabalho para agentes diferentes. Portanto não é correto transformar `Agent` em sinônimo de `Codex` ou `Claude`.

#### Modelo-alvo de equipe do projeto

| Estrutura | Atributos principais | Finalidade |
|---|---|---|
| `project_memberships` | `project_id`, exatamente um `agent_id|sub_agent_id`, `membership_status`, `valid_from/to`, `allocation_percent`, `max_concurrent_override`, `added_by`, `approved_at` | autoriza o agente a participar do projeto |
| `project_member_roles` | `membership_id`, `role`, `is_primary`, `can_review`, `can_approve` | define responsabilidades no projeto |
| `project_member_tracks` | `membership_id`, `track_id` | restringe/indica frentes técnicas |
| `project_member_stages` | `membership_id`, `stage_id` ou `stage_type` | restringe fases em que pode atuar |
| `project_member_modules` | `membership_id`, `product_module_id` | especialização funcional opcional |
| `agent_runtime_bindings` | `agent_id/sub_agent_id`, `runtime_type`, `profile/config ref`, `is_default`, `status` | mapeia agente lógico para Codex/Claude/Agy etc. sem armazenar segredo |
| `stage_staffing_requirements` | `stage_id`, `role`, `skill_id`, quantidade, proficiência, independência | planeja recursos antes das tasks |
| `task_assignments` ampliada | `membership_id`, `assignment_role`, `status`, `assigned_by`, datas, motivo | atribuição governada e histórica |
| `task_executions` ampliada | `assignment_id` obrigatório, `runtime_type`, `runtime_session_ref`, `executor_agent_id` snapshot, uso/custo | prova quem e como executou |
| `task_reviews` | `task_id`, `execution_id`, reviewer membership, decisão, comentários, evidência | revisão independente e auditável |

O modelo pode manter os FKs atuais de Agent/SubAgent durante a migração, mas deve adicionar `membership_id` como fonte da autorização no contexto do Project.

#### Associação durante o planejamento

O planejamento de agentes acontece em camadas:

1. **Plano de capacidade:** a partir da classificação/tracks/stages, declarar papéis e skills necessárias, sem escolher nomes prematuramente.
2. **Equipe do Project:** selecionar do catálogo apenas Agents/SubAgents ativos e aprovados; definir papéis, tracks, módulos, período e alocação.
3. **Baseline:** congelar o plano de equipe, requisitos de staffing e custos estimados. Mudança relevante de agente após baseline usa Change Request quando impactar prazo, custo, arquitetura ou segurança.
4. **Task planning:** declarar required skills, papel executor, papel reviewer e restrições de runtime/path.
5. **Scheduling:** selecionar um membro elegível e criar TaskAssignment.
6. **Execution:** iniciar TaskExecution ligada obrigatoriamente à Assignment e capturar runtime real.
7. **Review:** selecionar outro membro elegível quando houver separação de funções; registrar TaskReview.

O ProjectPlan deve conter estimativa de esforço/custo por role/track e referência aos requisitos de staffing. Nomes de agentes pertencem à equipe/alocação, não ao texto livre do plano.

#### Regra de elegibilidade para atribuição

Antes de atribuir uma Task, o backend deve verificar, nesta ordem:

1. Agent/SubAgent e membership estão ativos no período.
2. Membership pertence ao mesmo Project da Task.
3. Track, stage, módulo, paths e runtime estão autorizados.
4. Todas as skills obrigatórias estão aprovadas e disponíveis diretamente ou por herança permitida.
5. Risk level da Task não excede a autorização do agente.
6. Capacidade global e alocação do Project não foram ultrapassadas.
7. Não existe conflito de separação de funções.
8. Runtime escolhido está habilitado no Project e disponível.
9. Policy aplicável permite dispatch automático ou exige aprovação humana.

Entre candidatos elegíveis, o scheduler pode ranquear por afinidade de skill, carga atual, experiência no módulo, custo, desempenho histórico e continuidade de contexto. Esses fatores servem para ranking; nunca contornam autorização ou Policy.

#### Fluxo de estados

```text
ProjectMembership: proposed → approved → active → suspended → released

TaskAssignment: proposed → active → executing → completed
                     ├→ declined
                     ├→ revoked
                     └→ released/reassigned

TaskExecution: pending → running → completed → verified
                           ├→ failed → nova tentativa
                           └→ blocked

TaskReview: pending → approved
                    └→ changes_requested → nova execução
```

`completed` na Assignment significa que o agente terminou sua responsabilidade; `verified` pertence à execução revisada. Task só chega a `done` depois da revisão/policies exigidas.

#### Exemplo de equipe no AgendaFácil

```text
Project AgendaFácil 1.0.0
  ├─ Agent Athos       role=coordinator, tracks=all
  ├─ Agent A           role=architect/backend, tracks=Backend/API,Data
  ├─ Agent B           role=mobile_executor, track=Mobile, runtime=codex
  ├─ Agent C           role=web_executor, track=Web, runtime=claude
  ├─ Agent D           role=qa_reviewer, tracks=Web,Mobile,Backend
  └─ Agent E           role=security_reviewer, stages=Design,Verification,Release
```

A Task mobile solicita skills React Native e testes de acessibilidade. Somente membros ativos do track Mobile com essas skills são candidatos. O Agent B recebe a Assignment; a execução registra que usou Codex. O Agent D revisa. A aprovação de Release continua com papel autorizado e não é concedida automaticamente ao executor.

## 4. Fonte de verdade e relacionamentos obrigatórios

| Pergunta | Fonte de verdade recomendada |
|---|---|
| A qual produto o trabalho pertence? | `Project → ProductVersion → Product` |
| Em qual versão entra? | `Project.product_version_id`; não duplicar sem validação |
| Qual módulo é impactado? | associação explícita PlanningItem/Task ↔ ProductModule |
| Em qual fase está? | `Task.pipeline_stage_id` e estado do `PipelineStage` |
| O que foi aprovado no planejamento? | composição imutável da `PlanBaseline` |
| Qual revisão do documento foi aprovada? | `Approval.entity_type=artifact_version` |
| Um requisito de stage foi cumprido? | binding para ArtifactVersion elegível, calculado |
| O que entrou na release? | manifesto imutável do ReleaseCandidate/Release |
| O que está em produção? | último Deployment bem-sucedido por ambiente/alvo |
| Quem fez e quem revisou? | Assignment/Execution + ApprovalDecision, com identidade |
| Quais agentes podem trabalhar no projeto? | ProjectMembership + roles/tracks/stages autorizados |
| Qual CLI foi usada? | runtime binding + runtime efetivo da TaskExecution |

## 5. Pipeline padrão recomendado

O pipeline padrão deve ser distribuído como template versionado, não apenas descrito em documentação.

| Ordem | Stage | Saídas mínimas | Gate de saída |
|---:|---|---|---|
| 0 | Context | Context Brief, stakeholders, restrições | Contexto verificado |
| 1 | Product Definition | PRD, regras de negócio, critérios de sucesso | Product approval |
| 2 | Solution Design | SPEC, ADR/APR, API contracts, threat model | Architecture/security approval |
| 3 | Data Design | modelo conceitual/lógico/físico, migrations plan | Data review |
| 4 | UX/UI Design | fluxos, layouts, screen specs, design-system delta | Design approval |
| 5 | Planning | backlog, dependências, estimativas, baseline | Baseline approval |
| 6 | Implementation | código, migrations, documentação e PRs | Code review |
| 7 | Verification | test plan/report, evidências, segurança, performance | QA/security approval |
| 8 | Build | build/SBOM/image com checksum | CI policy pass |
| 9 | Release | release candidate, notes, rollback plan | Release approval |
| 10 | Deploy | deployment + smoke/health evidence | Production verification |
| 11 | Closeout | retrospectiva, métricas e dívida residual | Project close approval |

Fluxos menores devem herdar controles essenciais:

- **Hotfix:** Context/Triage → Fix Design → Implementation → Regression → Release → Deploy.
- **Research:** Context → Investigation → Decision/ADR → Closeout; não gera deploy.
- **Data migration:** Context → Data Design → Rehearsal → Approval → Execution → Reconciliation/Rollback check.

## 5.1 Fluxo de desenvolvimento ponta a ponta

O pipeline não deve começar na codificação. Ele representa todo o sistema de produção, desde a entrada da iniciativa até a comprovação do resultado:

```text
Intake
  → Product/Version/Project
  → Classification
  → Context and Requirements
  → Solution/Data/UX Design
  → Planning and Baseline
  → Task Dispatch
  → Execution
  → Review and Verification
  → Release Candidate
  → Approval
  → Deploy/Publish/Activate
  → Production Verification
  → Closeout and Feedback
                         └→ novos Planning Items / Change Request / Hotfix
```

| Passo | Ação | Registros principais | Critério de saída |
|---:|---|---|---|
| 1 | Registrar a iniciativa | Product, ProductVersion, Project, owner | identidade, objetivo e versão definidos |
| 2 | Classificar a entrega | solution types, strategy, targets, risco, dados | classificação confirmada |
| 3 | Resolver a linha de produção | template versionado, packs, tracks, ProjectPipeline draft | pipeline explicado e aceito |
| 4 | Contextualizar | Context Brief, stakeholders, restrições e métricas | contexto verificado |
| 5 | Especificar | PRD, regras, SPEC, dados, UX, segurança, ADR/APR | ArtifactVersions revisadas e gates aprovados |
| 6 | Planejar | Planning Items, módulos, tracks, critérios, estimativas e dependências | escopo revisável completo |
| 7 | Baselinar | PlanRevision + snapshot do escopo/pipeline/policies | Approval da baseline e hash imutável |
| 8 | Preparar execução | Tasks/subtasks, stages, skills, assignments | tasks `ready`, sem dependências pendentes |
| 9 | Executar | TaskExecution por tentativa, mudanças e evidências | executor marca tentativa `completed` |
| 10 | Revisar e validar | code review, testes, segurança, ArtifactVersions e Approval | execução `verified`; task `done` |
| 11 | Fechar stages | cálculo de tasks, artifacts, policies e gates | todas as stages obrigatórias concluídas |
| 12 | Montar candidato | ReleaseCandidate e manifesto imutável | commit/build/migrations/docs identificados |
| 13 | Aprovar release | PolicyEvaluations e ApprovalDecision | candidato promovido a Release |
| 14 | Entregar | Deployment, publicação em store/package registry ou ativação da automação | entrega técnica bem-sucedida |
| 15 | Verificar operação | smoke/health/business checks e observabilidade | resultado no alvo comprovado |
| 16 | Encerrar e aprender | métricas, retrospectiva, riscos/dívidas residuais | projeto/version release fechado ou próximo ciclo aberto |

### Um fluxo, vários tipos de saída

“Ponta a ponta” não significa que todo projeto termina em um container de produção. O último ato técnico varia conforme a classificação:

| Tipo | Ato de entrega | Evidência final |
|---|---|---|
| Web/API | deployment em ambiente | digest, migration, health/smoke tests |
| Mobile | build assinado + publicação/rollout | store build, versão, aprovação e telemetry |
| Site | publicação/CDN | build hash, URL e checks de SEO/acessibilidade |
| Automação | ativação de job/workflow | versão do workflow, schedule, dry-run e primeira execução |
| Data pipeline | ativação/backfill | job version, reconciliação e data-quality report |
| Biblioteca/SDK | publicação em registry | package version, assinatura e compatibility report |
| Pesquisa/protótipo | decisão formal/experimento encerrado | relatório, métricas e ADR; sem Release de produção |

O modelo deve usar um conceito geral `Delivery` com especializações ou metadados por canal. `Deployment` é uma forma de Delivery, não a única.

### Loop de execução dos agentes

Dentro das fases de produção, cada Task percorre um loop controlado:

```text
ForgeHub prepara contexto e autorização
  → agente CLI lê Task + artifacts + locks + policies
  → cria TaskExecution
  → modifica o working directory
  → testa e produz evidência/artifacts
  → devolve resultado completed/failed/blocked
  → revisor/CI valida de forma independente
  → ForgeHub marca verified ou solicita nova execução
```

Codex, Claude e Agy são executores CLI intercambiáveis dentro desse contrato. `antigravity` permanece alias transitório de Agy no código atual. Eles não são a fonte de verdade do status, não aprovam o próprio gate e não substituem Pipeline, Governance ou Audit.

### Invariantes do fluxo completo

1. Project é criado antes de planejamento detalhado e permanece ligado a uma ProductVersion.
2. Todos os stages pertencem ao pipeline desse Project.
3. Todo Planning Item pertence ao Project e à baseline ou a uma Change Request aprovada.
4. Toda Task pertence ao Project, stage e origem de escopo.
5. Toda execução pertence a uma Task e registra executor, tentativa, resultado e evidência.
6. Toda ArtifactVersion pertence ao Project e indica stage/origem/produtor.
7. Toda decisão de gate vem de Governance e gera AuditEvent idempotente.
8. Toda Release/Delivery contém um manifesto imutável do que foi entregue.
9. “Em produção” é derivado de Delivery bem-sucedida e verificada, nunca digitado manualmente.
10. Falha, rejeição, rollback e retrabalho preservam o histórico; não reescrevem registros anteriores.
11. Toda Assignment usa membro ativo do mesmo Project e satisfaz skills, autorização e capacidade.
12. Executor, runtime e reviewer ficam separados e auditáveis.

### Intake e associação desde o início

O modelo atual cria `FeatureRequest` e `BugReport` sem Product ou Project e só ganha rastreabilidade quando converte para PlanningItem. Para atender ao fluxo ponta a ponta, o intake precisa de uma entidade comum, por exemplo `DevelopmentRequest`, ligada obrigatoriamente a Product e, quando já conhecido, a ProductVersion/Project. Quando ainda não existe Project, a decisão de triagem cria o Project antes de começar especificação e planejamento detalhados.

Assim, nenhuma conversa ou demanda fica órfã e, ao mesmo tempo, o sistema não obriga a inventar um Project antes de decidir se a solicitação será aceita.

## 6. Exemplo ponta a ponta — aplicação AgendaFácil

### 6.1 Produto e versão

- Product: `AgendaFácil`
- Módulos: `Identity`, `Agenda`, `Clientes`, `Notificações`, `Billing`, `Design System`
- ProductVersion: `1.0.0`, status `planned`
- Project: `AgendaFácil — MVP 1.0.0`, associado à versão `1.0.0`
- Classificação: `web_app + mobile_app + api_service`, estratégia `greenfield`, alvos `browser/ios/android/server`, risco `high`
- Tracks: `Product/UX`, `Web`, `Mobile`, `Backend/API`, `Data`, `Platform/Deploy`
- Repositório: `/root/project/agendafacil`

### 6.2 Plano e baseline

O plano define o objetivo “permitir que um profissional publique horários e que clientes reservem um atendimento”. Inclui escopo, riscos de conflito de agenda, LGPD, custo e data-alvo.

Planning Items de exemplo:

1. `[feature][Agenda] Disponibilizar horários`.
2. `[feature][Clientes] Reservar atendimento`.
3. `[feature][Notificações] Enviar confirmação`.
4. `[security_fix][Identity] Consentimento e retenção de dados`.
5. `[documentation][Design System] Documentar estados de calendário`.

Após aprovação, a baseline congela esses cinco itens, suas estimativas, critérios e a versão do pipeline. Uma nova integração com WhatsApp depois desse ponto exige Change Request.

### 6.3 Artefatos por fase

- Context: `docs/context-brief.md`.
- Product Definition: `docs/prd.md`, `docs/business-rules.md`.
- Solution Design: `docs/spec.md`, `docs/adr/001-booking-consistency.md`, `openapi.yaml`.
- Data Design: `docs/data-model.md`, migration inicial.
- UX/UI: layout de calendário, fluxo de reserva, tokens alterados do design system.
- Verification: relatório de testes, evidência de concorrência e threat model atualizado.
- Release: release notes, manifest com commit/tag/imagem e rollback plan.

Cada arquivo é uma Artifact lógica. Cada revisão do arquivo é uma ArtifactVersion imutável. A aprovação se refere à versão, por exemplo “PRD v3”, e não apenas ao PRD genérico.

### 6.4 De Planning Item a execução

O item “Reservar atendimento” gera tasks vinculadas à stage Implementation:

- criar constraint/estratégia contra double booking;
- implementar endpoint `POST /bookings`;
- implementar tela de confirmação;
- integrar notificação;
- criar testes de concorrência e integração;
- revisar acessibilidade e regras LGPD.

Cada task tem critérios de aceite, dependências e executor. Um agente abre uma TaskExecution, registra início, realiza mudanças no working directory, executa verificações e encerra com `evidence_ref` apontando para PR, commit, relatório ou logs. Outro ator revisa. Somente então a task chega a `done`.

### 6.5 Release e produção

A Release Candidate `1.0.0-rc.1` fixa:

- commit Git;
- imagem e digest;
- migrations e checksum;
- ArtifactVersions aprovadas;
- Planning Items/Tasks incluídos;
- resultado dos gates.

Após aprovação, nasce a Release `1.0.0`. Um Deployment em `staging` passa por smoke tests; depois uma Approval de produção autoriza o Deployment em `production`. O sucesso registra ambiente, horário, executor, digest e evidência. Só nesse momento os itens incluídos podem ser reportados como “em produção”.

## 7. Como operar o sistema a partir de agora

### 7.1 Enquanto a arquitetura-alvo não estiver implementada

1. Crie Product, módulos e ProductVersion.
2. Crie Project associado à versão e preencha owner, diretório e repositório.
3. Crie ProjectPlan, aprove e gere uma baseline.
4. Crie o ProjectPipeline e copie explicitamente os stages do template; não suponha que `template_id` faça isso.
5. Registre Planning Items com Project e valide manualmente que versão e structure node pertencem ao mesmo projeto.
6. Crie tasks a partir dos Planning Items. Registre no título/descrição a stage e o módulo enquanto os FKs não existirem.
7. Crie Assignment e TaskExecution antes de alterar a task para `done`.
8. Registre evidência real e auditável; não use texto fictício ou “done” sem arquivo/PR/log.
9. Crie Artifact e ArtifactVersion vinculadas a stage/execution sempre que possível.
10. Marque requisito de stage como cumprido somente depois de conferir tipo, versão e aprovação do artefato.
11. Use Approval de Governance e gate juntos, registrando a mesma decisão, até eles serem unificados.
12. Não trate `Release.released` como prova de deploy. Registre manualmente a evidência de implantação em Artifact/Audit até existir `Deployment`.

### 7.2 Regra para mudança pós-baseline

- Não edite o escopo baselined.
- Abra Change Request com justificativa e impacto.
- Crie tasks associadas à Change Request.
- Registre aprovação em Governance.
- Após execução, crie uma nova revisão do plano e baseline; hoje essa etapa é manual.

### 7.3 Regra para agentes CLI

Antes de codificar, o agente deve obter ou receber:

- Product, versão e Project;
- stage atual e gate esperado;
- Planning Item/Change Request;
- Task e critérios de aceite;
- working directory e caminhos permitidos;
- artefatos vigentes e locks;
- policies aplicáveis;
- comandos de verificação;
- local onde registrar evidência.

Se algum dado estiver ausente, o agente deve apontar a lacuna; não deve inventar UUID, aprovação, estado de gate ou evidência.

## 8. Backlog de implementação priorizado

### P0 — integridade da linha de produção

1. Criar System Blueprint, relações tipadas e ProjectScope versionado; migrar a cobertura única de `ProjectStructureNode` para associações M:N.
2. Criar intake comum ligado a Product e conversão governada para ProductVersion/Project/ProjectScope/Planning Item.
3. Adicionar `project_id` e `pipeline_stage_id` a ProjectTask, com backfill e validação de consistência.
4. Exigir que Planning Items, Tasks, ArtifactVersions e evidências cubram explicitamente ProjectScopeItems.
5. Adicionar vínculo obrigatório de Artifact a Project/ProductVersion e aprovação por ArtifactVersion.
6. Unificar Gate e Approval; gate deriva das decisões de Governance.
7. Versionar templates e implementar `instantiate template` de forma atômica.
8. Criar máquinas de estados e constraints para pipeline, stage, gate, assignment e execution.
9. Fazer `stage completion` calcular cobertura de escopo, tasks, execuções, artefatos e approvals; remover confiança em `is_fulfilled` manual.
10. Garantir que Task `done` exige execução concluída/verificada, evidência e subtasks/dependências completas.
11. Validar sempre que referências cruzadas pertencem ao mesmo ProductVersion/Project/Pipeline/System Blueprint.
12. **Parcialmente concluído:** ProjectMembership, dispatch elegível e validação por Project implementados; tornar membership obrigatório também no CRUD manual legado.
13. **Concluído no fluxo automatizado:** executor, runtime e TaskExecutionReview independentes; fazer backfill/constraint para execuções antigas em etapa posterior.

### P1 — versionamento, release e deploy

1. Criar manifesto de ReleaseCandidate, Release e Deployment por Environment.
2. Ligar Release a artifacts, tasks, approvals, commit/tag/build e rollback.
3. Criar baseline completa e versionada, com lista imutável de Planning Items.
4. Aplicar Change Request gerando revisão e baseline novas.
5. Criar PolicyDefinition/Binding/Evaluation versionadas.
6. Adicionar critérios de aceite/DoD e módulo a Planning Items/Tasks.
7. Criar detecção completa de ciclos para stages e tasks.
8. Criar classificação de projeto e tracks; congelá-los na baseline.
9. Planejar staffing/capacidade/custo por role e track; integrar required skills ao scheduler.

### P2 — flexibilidade e experiência operacional

1. Catálogo oficial de templates: conception, standard delivery, feature, corrective maintenance, preventive maintenance, adaptive maintenance, evolutionary maintenance, hotfix, research e data migration.
2. Resolvedor composicional de pipeline por solution type, delivery strategy, plataforma e policies.
3. Dashboard por produto/versão/projeto com mapa expansível do sistema e matriz elemento x ciclo, mostrando stage, tracks, WIP, lacunas, bloqueios e readiness.
4. Seletor global de projeto e nomes legíveis no lugar de UUIDs.
5. Integração Git/CI para coletar commits, PRs, builds, checksums e testes.
6. Dispatch controlado para Codex, Claude e Agy com idempotência e orçamento.
7. Métricas de lead time, retrabalho, taxa de aprovação, custo e falhas de deploy.

## 9. Critérios de aceite da arquitetura-alvo

A estrutura estará coerente quando o ForgeHub conseguir responder, somente a partir dos dados persistidos:

1. Qual produto, versão, projeto, módulo, stage e item originaram qualquer task?
2. Qual execução produziu cada revisão de artefato e qual revisão foi aprovada?
3. Quais itens estavam na baseline e quais entraram por Change Request?
4. Por que uma stage está bloqueada e qual requisito falta?
5. Quem executou, quem revisou e qual evidência sustenta a conclusão?
6. Qual conjunto exato de commits, builds, migrations e documentos compõe uma release?
7. Em quais ambientes essa release está instalada e qual foi o resultado?
8. Quais policies foram avaliadas e com quais inputs?
9. É possível reconstruir a linha do tempo sem depender do GitHub ou memória de conversa?
10. Quais telas, processos, APIs, regras, entidades, estruturas de dados e unidades de deploy formam cada versão do produto?
11. Para cada elemento do sistema, em qual marco ele está e qual evidência sustenta esse estado?
12. Quais partes do mapa ficaram sem especificação, implementação, teste, release ou verificação operacional?
13. Partindo de uma tela, job ou integração, é possível navegar até objetivo, processo, regra, código, dado, release e ambiente — e voltar?
14. Toda manutenção ou nova implementação pode ser rastreada até telemetria, feedback, incidente ou demanda que a originou?
15. O sistema consegue explicar por que uma mudança seguiu hotfix, manutenção abreviada ou nova concepção completa?

Enquanto alguma resposta depender de inferência manual, a cadeia ainda está parcialmente implementada.
