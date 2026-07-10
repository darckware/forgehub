# ForgeHub — Guia de Project Delivery

## O que é o ForgeHub

ForgeHub é uma **plataforma de controle para desenvolvimento de software com agentes de IA**. Ele conecta planejamento, governança e execução em uma cadeia rastreável: toda feature, tarefa, artefato e decisão técnica fica vinculada ao produto que originou o trabalho.

Regra central: **nenhum trabalho acontece sem contexto, dono, status, evidência e rastro de auditoria.** Isso vale para trabalho humano e para trabalho de agentes de IA.

---

## Visão de uso na startup

```
Você (Product Owner)
    ↓  define contexto, aprova gates, confirma execuções
ForgeHub (controle, planejamento, governança, auditoria)
    ↓  Athos presente em cada tela como orquestrador
Athos (agente Hermes — lê contexto, gera artefatos, define agentes)
    ↓  delega execução por tipo de tarefa
Claude CLI  →  código Python/TypeScript, documentação técnica, refactoring complexo
Codex       →  testes, endpoints, geração de código repetitivo
Antigravity →  tarefas conforme perfil e contexto do projeto
    ↓  resultado registrado em
Kanboard (controle visual de execução por projeto)
    ↓  status sincronizado de volta para
ForgeHub Execution + Governance (confirmação + auditoria)
```

---

## Papel do Athos em cada tela

Athos é o orquestrador presente em **todas as telas do Project Delivery**. Ele não é apenas um chat — ele age ativamente em cada módulo:

| Tela | O que Athos faz |
|---|---|
| **Products** | Lê o contexto enviado e enriquece a descrição do produto com estrutura padronizada |
| **Projects** | Lê contexto + produto e gera o plano inicial do projeto (escopo, áreas, estimativas) |
| **Pipelines** | Configura os stages com artefatos obrigatórios e gates para o tipo de projeto |
| **Planning** | Lê os artefatos gerados e quebra em Planning Items por área (frontend/backend/db/design/deploy) |
| **Execution** | Decide qual agente ou CLI executa cada task; envia para Kanboard; confirma execução |
| **Artifacts** | Gera documentos via Claude CLI e registra os artefatos em cada stage |
| **Governance** | Verifica se gates podem ser aprovados; sugere aprovação ou aponta o que falta |

---

## Associação de CLIs por contexto de tarefa

Athos decide qual executor usar com base no tipo e contexto da tarefa. Não é arbitrário — segue critérios definidos:

| Tipo de tarefa | CLI escolhido | Por quê |
|---|---|---|
| Geração de documentação (PRD, SPEC, ADR) | **Claude CLI** | Melhor em raciocínio estruturado e escrita técnica longa |
| Implementação de backend (API, regras de negócio) | **Claude CLI** | Capacidade de manter contexto amplo de código |
| Implementação de frontend (componentes, páginas) | **Claude CLI** ou **Codex** | Depende da complexidade; Codex é mais rápido para padrões repetitivos |
| Geração de testes unitários e de integração | **Codex** | Especializado em cobertura de testes |
| Migration de banco de dados | **Claude CLI** | Requer entendimento das regras de negócio do schema |
| Refactoring pontual | **Codex** | Rápido para mudanças estruturais sem mudança de comportamento |
| Tarefas simples e repetitivas | **Antigravity** | Execução direta quando contexto é suficiente e tarefa é bem definida |
| Orquestração, análise, decisão | **Athos (Hermes)** | Sem delegação para CLI — Athos executa diretamente |

Athos documenta a decisão de qual CLI foi escolhido e por quê. Essa decisão é registrada no TaskExecution e integra o Audit Trail.

---

## O menu Project Delivery

O menu é composto por sete módulos que formam uma cadeia linear. A ordem importa — cada módulo depende do anterior.

```
Products → Projects → Pipelines → Planning → Execution → Artifacts → Governance
```

---

### 1. Products — O contexto de negócio permanente

**O que é:** O registro do software que você está construindo. Existe independentemente de versões ou projetos — representa o sistema em si.

**O que contém:**
- Nome, descrição e problema que o produto resolve
- Módulos funcionais (partes do sistema: ex. "API", "Dashboard", "Auth")
- Versões semânticas (`1.0.0`, `1.1.0`, `2.0.0`)

**O que Athos faz aqui:**
Você envia um arquivo `.md` ou descreve o produto no chat. Athos estrutura o contexto seguindo o padrão: problema → público-alvo → módulos → decisões permanentes de arquitetura. Esse contexto é a base para todo o resto — PRD, SPEC, Planning.

**Regra:** O produto guarda o que **não muda por versão**. Prazo, escopo e tarefas pertencem ao projeto.

---

### 2. Projects — A iniciativa concreta

**O que é:** Um projeto é um trabalho delimitado associado a uma versão do produto. É onde o desenvolvimento acontece.

**O que contém:**
- Vínculo com uma versão do produto (ex: "MinhaApp v1.0.0")
- Objetivo específico desta versão
- Plano de projeto (escopo, estimativas, datas)
- Baseline (aprovação do escopo — após aprovada, mudanças exigem Change Request)
- Change Requests (alterações formais de escopo pós-baseline)

**O que Athos faz aqui:**
Lê o contexto do produto e gera o plano inicial do projeto: objetivo da versão, critérios de aceite, divisão de trabalho por área (frontend, backend, banco de dados, design, deploy) e estimativas preliminares. Você revisa e aprova.

**Distinção Product vs Project:**
- Produto: *o que* você está construindo (permanente)
- Projeto: *como, quando e por quem* uma versão específica será entregue

---

### 3. Pipelines — As fases de entrega

**O que é:** O pipeline define as **fases obrigatórias** que o projeto percorre. Cada fase (stage) tem artefatos obrigatórios e um gate de aprovação antes de avançar.

**Pipeline padrão de desenvolvimento:**

| Stage | Artefato obrigatório | Gate |
|---|---|---|
| **Discovery** | Context Brief | Aprovação sua |
| **PRD** | Product Requirements Document | Aprovação sua |
| **SPEC** | Technical Specification | Aprovação sua |
| **DATA SPEC** | Data Model / Schema | Aprovação sua |
| **ADR** | Architecture Decision Record | Aprovação sua |
| **Implementation** | Código-fonte (Pull Requests) | Review de Athos |
| **Migration** | Scripts de banco validados | Aprovação sua |
| **Testing** | Test report com evidências | Aprovação sua |
| **Build** | Build artifact | Automático (CI passa) |
| **Release** | Release Notes + Approval record | Aprovação sua |

**Como funciona o gate:**
Nenhum stage avança sem que seus artefatos existam e o gate seja aprovado. É o mecanismo que impede que a implementação comece sem documentação ou que o release aconteça sem testes.

**O que Athos faz aqui:**
Configura os stages do pipeline para o tipo de projeto (feature completa, hotfix, refactoring) com os artefatos e gates adequados. Para hotfix, por exemplo, o pipeline é simplificado: Discovery → Fix → Testing → Release.

**Importante:** O pipeline é dividido por **fase de entrega**, não por área técnica. A divisão por frontend/backend/design acontece nas Tasks, dentro de cada stage.

---

### 4. Planning — O backlog estruturado por área

**O que é:** Onde os itens de trabalho são registrados, classificados por tipo e divididos por área técnica antes de virarem tasks de execução.

**Tipos de Planning Item:**

| Tipo | Quando usar |
|---|---|
| **Feature** | Nova funcionalidade |
| **Bug** | Defeito em produção ou testes |
| **Hotfix** | Bug crítico urgente |
| **Improvement** | Melhoria em funcionalidade existente |
| **Technical Debt** | Débito técnico acumulado |
| **Refactoring** | Reorganização sem mudança de comportamento |
| **Security Fix** | Correção de vulnerabilidade |
| **Research** | Investigação antes de decisão técnica |
| **Documentation** | Criação ou atualização de documentação |

**O que Athos faz aqui:**
Lê os artefatos aprovados (PRD, SPEC, DATA SPEC) e gera automaticamente os Planning Items com divisão por área:

```
Planning Items gerados por Athos
├── Frontend
│    ├── [Feature] Criar formulário de cadastro de produto
│    └── [Feature] Implementar listagem com filtros e paginação
├── Backend
│    ├── [Feature] Endpoint POST /api/v1/products com validação
│    └── [Feature] Regra: produto precisa de ao menos uma versão
├── Banco de Dados
│    ├── [Feature] Migration: criar tabela products no schema company
│    └── [Feature] Índice de performance em products.name
├── Design
│    └── [Feature] Protótipo de tela de produto no Figma
└── Deploy
     └── [Feature] Configurar variável de ambiente PRODUCT_MAX_VERSIONS
```

Cada item tem descrição, critérios de aceite e área. Você revisa e aprova o backlog antes de virar tasks.

---

### 5. Execution — As tarefas em execução com Kanboard

**O que é:** O módulo onde Planning Items viram tasks concretas, são atribuídas a um agente, enviadas ao Kanboard e executadas. É aqui que o trabalho real acontece e é rastreado.

#### 5.1 Ciclo de vida de uma task

```
Planning Item aprovado
    ↓
Task criada (status: planned)
    ↓
Athos decide o agente e o CLI  →  Task atribuída (status: assigned)
    ↓
Task sincronizada para Kanboard  →  card criado na coluna "Ready"
    ↓
Agente inicia execução  →  Kanboard move para "In Progress"
    ↓  TaskExecution registrada em ForgeHub
Agente conclui  →  Kanboard move para "Done"
    ↓  status sincronizado de volta ao ForgeHub
Você confirma a execução  →  TaskExecution marcada "verified"
    ↓
AuditEvent criado no Governance
```

#### 5.2 Confirmação de execução

Cada task exige **confirmação sua** antes de ser marcada como concluída no ForgeHub. O fluxo é:
1. Kanboard mostra o card como "Done" (agente concluiu)
2. ForgeHub recebe o status atualizado
3. Você vê na tela de Execution: task pendente de verificação
4. Você revisa a evidência (output do agente, pull request, arquivo gerado)
5. Você confirma → `TaskExecution.status = "verified"` → AuditEvent criado

Não há marcação automática de "concluído" sem sua confirmação explícita.

#### 5.3 Mapeamento de status entre ForgeHub e Kanboard

| Status ForgeHub | Coluna Kanboard |
|---|---|
| `planned` | Backlog |
| `assigned` | Ready |
| `in_progress` | In Progress |
| `blocked` | Blocked |
| `done` | Done |
| `deployed` | Close |
| `cancelled` | Canceled |

#### 5.4 Subtasks

Tasks complexas são divididas em subtasks. Cada subtask tem seu próprio agente, execução e card no Kanboard. A task pai só avança para "done" quando todas as subtasks estão concluídas.

---

### 6. Kanboard — Controle visual de execução

**O que é:** O Kanboard é o quadro visual onde o trabalho em andamento é administrado. Ele não substitui o ForgeHub — complementa: o ForgeHub tem o planejamento e a governança; o Kanboard tem a visão operacional do que está acontecendo agora.

**Como funciona a integração:**
- ForgeHub cria a task → envia para Kanboard via API JSON-RPC (`POST /api/v1/tasks/{id}/sync-kanboard`)
- Cada task ForgeHub tem um `kanboard_task_id` armazenado (campo na tabela `project_tasks`)
- Quando o status muda no ForgeHub, o card no Kanboard é movido de coluna automaticamente
- Kanboard é a interface que Athos e os agentes usam para ver o que está na fila

**Limpeza do Kanboard por projeto:**

O Kanboard funciona como uma **visão limpa do projeto corrente**. A regra é:

- Ao **encerrar uma fase** do projeto (ex: stage Implementation concluído e aprovado) → tasks desse stage são movidas para "Close" no Kanboard
- Ao **trocar de versão** (projeto da v1.0.0 encerrado, projeto da v1.1.0 iniciado) → todas as tasks do projeto anterior são fechadas/arquivadas no Kanboard antes do novo projeto começar
- O novo projeto começa com o Kanboard limpo — apenas as tasks do projeto atual aparecem nas colunas ativas

Isso mantém o board focado e evita que tasks de versões anteriores poluam a visão operacional do que está sendo desenvolvido agora.

**Quem faz a limpeza:**
Athos executa a limpeza ao final de cada fase (movendo tasks para "Close") e ao iniciar um novo projeto (arquivando tasks antigas). Você confirma antes da limpeza ser executada.

**Kanboard como fonte de auditoria:**
O histórico de movimentação dos cards no Kanboard (quem moveu, quando, de qual coluna para qual) é capturado e registrado como AuditEvents no módulo de Governance. Isso garante que a trilha de auditoria inclui não apenas o que foi planejado, mas o que foi realmente executado e quando.

---

### 7. Artifacts — Os entregáveis formais

**O que é:** Artefatos são os documentos e entregas formais produzidos ao longo do projeto. São a prova de que o trabalho foi feito e está correto.

**Como Athos gera os artefatos:**

Para cada stage de documentação, o fluxo é:
1. Athos recebe o contexto do projeto (produto, versão, objetivo)
2. Athos chama Claude CLI com prompt específico para o tipo de artefato
3. Claude CLI gera o documento em `.md`
4. Documento é salvo no diretório de trabalho do projeto
5. Artefato é registrado no ForgeHub com vínculo ao stage
6. Você revisa → aprova ou solicita revisão → gate liberado

**Artefatos por stage:**

| Stage | Artefato | Formato | Gerado por |
|---|---|---|---|
| Discovery | Context Brief | `.md` | Você + Athos |
| PRD | Product Requirements Document | `.md` | Athos via Claude CLI |
| SPEC | Technical Specification | `.md` | Athos via Claude CLI |
| DATA SPEC | Data Model + Schema | `.md` | Athos via Claude CLI |
| ADR | Architecture Decision Record | `.md` | Athos |
| Implementation | Pull Requests | código | Claude CLI / Codex / Antigravity |
| Migration | Scripts de banco | `.sql` | Claude CLI / Codex |
| Testing | Test report com evidências | `.md` | Athos + agentes |
| Release | Release Notes | `.md` | Athos via Claude CLI |
| Release | Approval record | registro ForgeHub | Você |

**Versionamento:**
Cada artefato pode ter múltiplas versões. Revisões geram nova versão — o histórico é preservado. O stage não avança com a versão anterior pendente de aprovação.

---

### 8. Governance — Aprovação e auditoria

**O que é:** Governance é o módulo que garante que nenhuma entrega acontece sem validação e que tudo fica registrado de forma imutável.

#### 8.1 Approvals (Gates)

Cada stage tem um gate. Antes de avançar, uma aprovação precisa ser registrada:

```
Stage "PRD" concluído
    ↓
Athos verifica: artefato PRD existe e está aprovado?
    ↓ sim
Gate: aguardando aprovação sua
    ↓ você aprova
Approval registrada com timestamp e responsável
    ↓
Stage "SPEC" liberado
```

Sem aprovação, o pipeline fica bloqueado. Isso impede que implementação comece com especificação incompleta.

#### 8.2 Audit Trail

Cada ação relevante gera um `AuditEvent` imutável. Fontes de auditoria:

| Evento | Origem |
|---|---|
| Task criada, atribuída, concluída | ForgeHub Execution |
| Artefato criado ou aprovado | ForgeHub Artifacts |
| Gate aprovado ou rejeitado | ForgeHub Governance |
| Card movido no Kanboard | Kanboard (via sync) |
| CLI executou task (com output) | TaskExecution.evidence_ref |
| Athos tomou decisão de agente | TaskExecution.notes |

**Por que o Kanboard alimenta o Audit Trail:**
O Kanboard registra *quando* o trabalho aconteceu de fato (não apenas quando foi planejado). Ao sincronizar o histórico de movimentação do Kanboard de volta ao ForgeHub, o Audit Trail tem o registro completo: planejado em X, iniciado em Y, concluído em Z, verificado por você em W.

---

## Fluxo completo de uso — do zero ao release

```
ETAPA 1 — PRODUTO
Você cria o produto com contexto de negócio
Athos estrutura: problema → módulos → decisões permanentes
Produto registrado com versão inicial (ex: 1.0.0)

ETAPA 2 — PROJETO
Você cria o projeto vinculado à versão
Athos lê contexto e gera plano inicial
Você aprova o plano → baseline criada

ETAPA 3 — PIPELINE
Pipeline criado com stages padrão
Athos configura artefatos obrigatórios e gates por stage

ETAPA 4 — DISCOVERY E DOCUMENTAÇÃO
Athos chama Claude CLI para gerar Context Brief
→ Você revisa → Gate aprovado → próximo stage
Athos chama Claude CLI para gerar PRD
→ Você revisa → Gate aprovado → próximo stage
[repete para SPEC, DATA SPEC, ADR]

ETAPA 5 — PLANNING
Athos lê todos os artefatos aprovados
Athos gera Planning Items por área (frontend/backend/db/design/deploy)
Você revisa o backlog → aprova

ETAPA 6 — EXECUTION (Implementation stage)
Athos quebra Planning Items em Tasks
Para cada task, Athos decide: Claude CLI / Codex / Antigravity
Tasks sincronizadas para Kanboard (coluna "Ready")
Agentes executam → Kanboard atualizado ("In Progress" → "Done")
ForgeHub recebe status atualizado
Você confirma cada execução → TaskExecution "verified"
AuditEvent criado por task confirmada

ETAPA 7 — MIGRATION E TESTING
Athos coordena migration scripts via Claude CLI
Athos coordena geração de testes via Codex
Você aprova Migration gate → Testing gate

ETAPA 8 — BUILD E RELEASE
Build executado (CI/CD)
Athos gera Release Notes via Claude CLI
Você aprova o Release gate final
Approval record registrado
Audit Trail completo disponível

ETAPA 9 — PRÓXIMA VERSÃO
Athos arquiva tasks do projeto encerrado no Kanboard
Kanboard limpo para o próximo projeto
Novo projeto criado vinculado à versão 1.1.0
Ciclo reinicia
```

---

## Resumo das responsabilidades

| Quem | O que faz |
|---|---|
| **Você** | Define contexto, aprova gates, confirma execuções, toma decisões de produto |
| **Athos** | Orquestra em cada tela, gera artefatos, divide planning, decide qual CLI usar, gerencia Kanboard |
| **Claude CLI** | Documenta, implementa código complexo, gera migrations |
| **Codex** | Gera testes, implementa padrões repetitivos, refactoring |
| **Antigravity** | Executa tarefas simples e bem definidas |
| **Kanboard** | Visão operacional do trabalho em andamento; alimenta auditoria |
| **ForgeHub** | Registra tudo, controla os gates, mantém o Audit Trail, garante rastreabilidade |

---

## Princípio de exibição de entidades relacionadas

Toda tela do ForgeHub que exibe ou coleta referência a outra entidade deve seguir esta regra:

**Nunca exibir um UUID cru. Sempre resolver para nome legível.**

### Exibição (telas de lista e detalhe)

Quando uma entidade referencia outra pelo ID, a tela deve resolver e exibir o nome:

| Campo exibido | Formato correto |
|---|---|
| Produto + versão | `"MinhaApp — v1.0.0"` |
| Projeto | nome do projeto |
| Planning Item | título do item |
| Agente / executor | nome do agente |
| Task pai (subtask) | título da task pai |
| Stage do pipeline | nome do stage |

### Formulários de criação e edição

Quando um formulário precisa coletar uma referência a outra entidade, deve usar **combobox com busca**, nunca input de texto livre:

- O combobox carrega as opções via fetch da API correspondente
- Exibe o nome legível, armazena o UUID internamente
- Suporta busca por texto quando a lista é longa
- Quando há dependência entre campos (ex: selecionar versão depende do produto selecionado), o segundo combobox só é habilitado após o primeiro ser preenchido

**Exemplo do fluxo correto em ProjectForm:**
```
[Combobox Produto]  →  seleciona "MinhaApp"
    ↓  filtra versões do produto selecionado
[Combobox Versão]   →  seleciona "v1.0.0"
    ↓  armazena product_version_id internamente
```

---

## Crítica técnica — Ajustes necessários no sistema

Esta seção mapeia todos os problemas identificados no estado atual da implementação, organizados por categoria e prioridade.

---

### A. Exibição de UUIDs crus nas telas (crítico — impacto direto na usabilidade)

Telas que exibem IDs no lugar de nomes legíveis — o usuário não consegue identificar a qual entidade o registro pertence sem consultar o banco manualmente.

| Arquivo | Campo exibido | Correção necessária |
|---|---|---|
| `project/index.tsx:142` | `project.product_version_id` | Resolver para "Produto — vX.X.X" |
| `project/[id].tsx:611` | `project.product_version_id` | Resolver para "Produto — vX.X.X" |
| `pipeline/index.tsx:145` | `pipeline.project_id` | Resolver para nome do projeto |
| `pipeline/[id].tsx:180` | `pipeline.project_id` | Resolver para nome do projeto |
| `artifact/index.tsx:172` | `artifact.project_id` | Resolver para nome do projeto |
| `artifact/[id].tsx:162` | `artifact.project_id` | Resolver para nome do projeto |
| `task/[id].tsx:98` | `task.project_id` | Resolver para nome do projeto |
| `task/[id].tsx:112` | `task.planning_item_id` | Resolver para título do planning item |
| `task/[id].tsx:137` | `task.parent_task_id` | Resolver para título da task pai |
| `task/[id].tsx:222` | `execution.executor_id` | Resolver para nome do agente |
| `backlog/[id].tsx:203` | `scope.product_version_id` | Resolver para "Produto — vX.X.X" |

---

### B. Inputs de UUID livre nos formulários (crítico — impede uso sem conhecimento técnico)

Formulários com campos de texto livre esperando UUIDs — o usuário precisa saber o UUID da entidade para preencher, tornando o sistema inutilizável sem acesso direto ao banco.

| Arquivo | Campo | Correção necessária |
|---|---|---|
| `project/ProjectForm.tsx` | `product_version_id` | Combobox: Produto → Versão (dependente) |
| `pipeline/PipelineForm.tsx` | `project_id` | Combobox: lista de projetos ativos |
| `pipeline/PipelineForm.tsx` | `pipeline_template_id` | Combobox: lista de templates |
| `artifact/ArtifactForm.tsx` | `project_id` | Combobox: lista de projetos |
| `artifact/ArtifactForm.tsx` | `pipeline_stage_id` | Combobox: stages do projeto selecionado |
| `artifact/ArtifactForm.tsx` | `task_execution_id` | Combobox: execuções do projeto |
| `backlog/PlanningItemForm.tsx` | `product_version_id` | Combobox: Produto → Versão (dependente) |
| `backlog/PlanningItemForm.tsx` | `project_id` | Combobox: projetos da versão selecionada |
| `task/TaskForm.tsx` | `project_id` | Combobox: lista de projetos ativos |
| `task/TaskForm.tsx` | `planning_item_id` | Combobox: items do projeto selecionado |
| `task/TaskForm.tsx` | `parent_task_id` | Combobox: tasks do mesmo projeto (para subtasks) |
| `governance/ApprovalForm.tsx` | `entity_id` | Combobox filtrado por `entity_type` selecionado |
| `governance/ApprovalForm.tsx` | `policy_id` | Combobox: lista de políticas ativas |

---

### C. Lacunas funcionais — backend existe, frontend não expõe (alto impacto)

Funcionalidades com backend completo mas sem interface no frontend — o sistema parece incompleto ao usuário mas na verdade os dados já são suportados.

| Funcionalidade | Situação | Correção necessária |
|---|---|---|
| Criação de stages no pipeline | Backend: `POST /api/v1/pipelines/{id}/stages` existe. Frontend: sem formulário | Adicionar formulário de stage na tela `pipeline/[id]` |
| Criação de gates no stage | Backend: `POST .../stages/{id}/gates` existe. Frontend: sem formulário | Adicionar formulário de gate inline na StageCard |
| Definição de artefatos obrigatórios por stage | Backend: `POST .../stages/{id}/required-artifacts` existe. Frontend: sem formulário | Adicionar checklist editável de artefatos na StageCard |
| Aprovação de ProjectPlan | Backend: `POST /api/v1/projects/plans/{id}/approve` existe. Frontend: sem botão | Adicionar ação de aprovação na tela de projeto |
| Criação de PlanBaseline | Backend: `POST /api/v1/projects/{id}/baselines` existe. Frontend: sem formulário | Adicionar fluxo de baseline na tela de projeto |
| Criação de Change Request | Backend: `POST /api/v1/projects/{id}/change-requests` existe. Frontend: placeholder estático | Substituir placeholder por formulário real |
| Decisão de Change Request | Backend: `PATCH /api/v1/projects/change-requests/{id}` existe. Frontend: sem ação | Adicionar aprovação/rejeição de CR |
| Edição de projeto | Backend: `PATCH /api/v1/projects/{id}` existe. Frontend: sem formulário de edição | Adicionar edição inline ou modal na tela de projeto |
| Edição de planning item | Backend suporta PATCH. Frontend: sem edição exposta | Adicionar edição na tela `backlog/[id]` |
| Confirmação de execução de task | Backend: `PATCH` com `status=verified` existe. Frontend: sem fluxo de confirmação | Adicionar UI de revisão e confirmação na tela `tasks/[id]` |

---

### D. Bugs e inconsistências técnicas (médio impacto)

Problemas que não travam o usuário mas causam erros silenciosos ou comportamento inesperado.

| Arquivo | Problema | Correção necessária |
|---|---|---|
| `useProject.ts:126` | `useUpdateProject` faz PUT mas backend só aceita PATCH | Corrigir método para PATCH |
| `useGovernance.ts:121` | Todas as chamadas usam `/api/v1/governance` sem `/approvals` — 404 garantido | Corrigir `RESOURCE` para `/api/v1/governance/approvals` |
| `project/[id].tsx` | `ProjectOut` do backend não retorna campo `plan` mas o frontend declara e tenta renderizar `project.plan.scope_summary` | Remover schema fantasma ou adicionar endpoint que retorne o plano junto |
| `useProject.ts:62` | Schema frontend declara `plan` com campos `start_date`, `target_date`, `is_baselined` que não existem no backend (`estimated_start_date`, `estimated_end_date`, `status`) | Alinhar nomes de campos com o backend |
| `ProjectForm.tsx` | `product_version_id` opcional no frontend mas obrigatório no backend — submissão sem o campo retorna 422 sem mensagem de campo | Tornar obrigatório no schema Zod do frontend |
| `project/index.tsx:153` | Delete de projeto sem confirmação — ação destrutiva em cascata (planos, tasks, execuções) | Adicionar dialog de confirmação |
| `task/[id].tsx` | `execution.executor_id` exibe UUID cru; sem link para perfil do agente | Resolver para nome do agente com link |

---

### E. Integração Kanboard — lacunas no ciclo completo (alto impacto operacional)

A integração atual é unidirecional: ForgeHub cria cards no Kanboard, mas o Kanboard não retorna status ao ForgeHub.

| Lacuna | Impacto | Correção necessária |
|---|---|---|
| Sincronização reversa Kanboard → ForgeHub | O Execution module não sabe se uma task foi concluída sem intervenção manual | Implementar webhook ou polling: quando card move para "Done" no Kanboard, atualizar `ProjectTask.status` e criar `TaskExecution` no ForgeHub |
| Limpeza do Kanboard ao encerrar fase | Cards de fases anteriores acumulam no board | Implementar endpoint que archive tasks de um stage/projeto no Kanboard ao aprovar o gate de encerramento |
| Limpeza ao trocar de versão/projeto | Board fica poluído com histórico de versões anteriores | Ao iniciar novo projeto, arquivar todas as tasks do projeto anterior no Kanboard antes de criar as novas |
| Kanboard sem VITE_KANBOARD_URL configurado no Docker | Frontend sempre usa fallback `localhost:8081` — não funciona dentro do container | Adicionar `VITE_KANBOARD_URL` no `docker-compose.yml` com valor correto |
| Iframe sem fallback de erro | Se Kanboard estiver fora do ar, o usuário vê tela em branco sem mensagem | Adicionar detecção de falha no iframe com mensagem de erro |

---

### F. Funcionalidades de orquestração com Athos — inexistentes (planejadas)

Funcionalidades previstas no fluxo de uso mas que ainda não foram implementadas.

| Funcionalidade | Descrição | Prioridade |
|---|---|---|
| Painel Athos por tela | Athos disponível como assistente contextual em cada módulo do Project Delivery | Alta |
| Geração automática de artefatos | Athos lê contexto e aciona Claude CLI para gerar PRD, SPEC, DATA SPEC no formato `.md` | Alta |
| Quebra automática de Planning Items | Athos lê artefatos aprovados e gera backlog por área (frontend/backend/db/design/deploy) | Alta |
| Decisão de agente por task | Athos avalia tipo e contexto da task e registra qual CLI usará com justificativa | Alta |
| Confirmação de execução com evidência | Tela de revisão onde você vê o output do CLI e aprova ou solicita reexecução | Alta |
| Limpeza automática do Kanboard | Athos arquiva cards ao final de cada fase/versão, com confirmação sua antes de executar | Média |
| Sugestão de aprovação de gate | Athos verifica se todos os artefatos obrigatórios existem e sugere aprovação do gate | Média |
| Histórico de decisões do Athos | Registro de cada decisão de orquestração (qual CLI, por quê, resultado) no Audit Trail | Média |

---

### G. UX e experiência geral (baixo/médio impacto, mas degradam a usabilidade)

| Problema | Correção necessária |
|---|---|
| Nenhuma tela tem breadcrumb de navegação — o usuário perde o contexto de onde está na hierarquia Produto → Versão → Projeto → Task | Adicionar breadcrumb hierárquico nas telas de detalhe |
| Listas sem filtro por projeto — todas as tasks, pipelines e artefatos são exibidos juntos independente do projeto ativo | Adicionar filtro global por projeto ativo (contexto de trabalho corrente) |
| Deleção sem confirmação em múltiplas telas (projeto, pipeline, planning item) | Padronizar dialog de confirmação para todas as ações destrutivas |
| Formulários não fecham nem redirecionam após sucesso de criação em alguns módulos | Padronizar comportamento pós-submit: fechar form + scroll para o novo item criado |
| Status de entidades exibidos em inglês (`planned`, `in_progress`) sem tradução ou legenda | Traduzir labels de status para português ou adicionar tooltips explicativos |
| Sem indicação visual do projeto corrente ativo em nenhuma tela | Adicionar seletor de projeto ativo no header — todas as telas filtram pelo projeto selecionado |
