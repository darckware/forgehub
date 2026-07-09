# ForgeHub — Manual do Sistema

## Índice

- [Propósito deste manual](#propósito-deste-manual)
- [O que é o ForgeHub](#o-que-é-o-forgehub)
- [Política do Assistente](#política-do-assistente--leia-isto-antes-de-operar-qualquer-coisa)
- [Como o sistema está organizado (sidebar)](#como-o-sistema-está-organizado-sidebar)
  - [General](#general) — Dashboard, Workspace, Notifications, Inbox, Docs
  - [Planning](#planning) — Products, Projects, Pipelines, Templates, Planning, Execution, Artifacts, Governance, Policies
  - [Agents & AI](#agents--ai) — Agents, Agent Tools, Chat Commands, Skills, Crons, Foundation, ForgeRouter
  - [Integrations](#integrations) — Kanboard, Knowledge Base
  - [Operations](#operations) — System Control, Hindsight, Auditor, Deploy Control, Servers, Database
  - [Administration](#administration) — Users, Access Profiles
- [Documentação técnica por tela](#documentação-técnica-por-tela)
- [Regras de negócio centrais](#regras-de-negócio-centrais)

Dica de uso rápido: use Ctrl+F pelo nome da tela (ex.: "Hindsight", "Templates") — cada linha da tabela correspondente tem a rota exata e uma frase do que a tela faz, então costuma ser mais rápido que navegar pelas seções.

## Propósito deste manual

Este é o documento de referência que o **assistente embutido em cada tela** (quando essa funcionalidade for adicionada ao ForgeHub) deve ler para explicar ao usuário como o sistema funciona. Ele cobre: o que o ForgeHub é, para que serve cada módulo/tela, como os dados se conectam entre si, e — mais importante — **os limites do que o assistente pode fazer**.

Este manual é a visão geral. Detalhe técnico por tela (rotas, hooks, endpoints, regras de negócio aplicadas, estados de erro/loading) vive em `docs/screens/*.md`, um arquivo por tela — quando existir, o assistente deve ler o arquivo da tela específica além deste manual antes de responder.

## O que é o ForgeHub

ForgeHub é um **console de desenvolvimento de projetos** — um plano de controle para planejar, governar e executar projetos de software com agentes de IA: cadastro de produto/versão/projeto, pipeline com estágios e aprovações obrigatórias, itens de planejamento (features/bugs/etc.) desdobrados em tasks, execuções de task por agentes, e uma trilha de auditoria ligando cada entidade de volta a uma versão de produto.

Invariante central: nenhuma feature, bug, task, skill, execução ou artefato pode existir sem rastreabilidade até produto, versão, projeto, planejamento, pipeline, responsável, status, trilha de auditoria e critério de validação. A maior parte das tabelas existe para manter essa cadeia intacta, não só para guardar dado solto.

## Política do Assistente — leia isto antes de operar qualquer coisa

O assistente é tratado como um **usuário avançado** do sistema — tem acesso amplo pra ler e explicar, mas seu poder de ação é deliberadamente estreito (veja o que ele nunca pode fazer, abaixo).

**O assistente pode:**
- Ler este manual e os arquivos em `docs/screens/*.md` para explicar ao usuário como qualquer tela/funcionalidade funciona.
- Ler dados do sistema (consultar produtos, projetos, tasks, planejamento, artefatos, etc.) para responder perguntas.
- **Operar o sistema, mas exclusivamente via importação e exportação de dados** — ex.: exportar um relatório, importar uma planilha/CSV para popular registros através de um fluxo de import dedicado, gerar um arquivo de saída.
- **Enviar mensagens para o Inbox reportando problemas e sugestões de melhoria** que encontrar no sistema — mesmo canal (`POST /api/v1/demands`) já usado por agentes Hermes e pelo próprio usuário. É a forma correta de registrar um achado sem agir sozinho sobre ele: o usuário lê e decide o destino (task, projeto, base de conhecimento, planejamento).

**O assistente NUNCA pode:**
- Criar, editar ou excluir diretamente uma entidade do sistema (produto, versão, projeto, pipeline, item de planejamento, task, artefato, agente, usuário, permissão, configuração) fora de um fluxo de importação/exportação explícito.
- Alterar configurações do sistema, permissões de usuário, ou qualquer estado operacional (deploy, restart de serviço, etc.).
- Executar uma ação mutável só porque o usuário pediu no chat, se essa ação não for import/export — nesse caso, o assistente deve explicar o que precisa ser feito e apontar o usuário para a tela/botão correto, não fazer por ele.

Essa é uma fronteira de governança, não uma sugestão — qualquer implementação futura do assistente deve restringir as ferramentas/endpoints disponíveis a ele de acordo com essa política, não confiar só em uma instrução de prompt.

## Como o sistema está organizado (sidebar)

### General
| Tela | Rota | Para que serve |
|---|---|---|
| Dashboard | `/` | Visão operacional do ambiente local: versões de CLIs instaladas e uso de recursos do host. Não mostra dados de domínio do ForgeHub. |
| Workspace | `/workspace` | Chat com os agentes Hermes + terminal real (PTY) no host, lado a lado. |
| Notifications | `/notifications` | Feed persistente de alertas — execuções de cron (sucesso/erro) e alertas de sistema (ex.: chegada de mensagem no Inbox). Mesmo sino que aparece no rodapé do sidebar. |
| Inbox | `/demands` | Canal de comunicação — qualquer agente ou o próprio usuário envia uma nota (ideia, procedimento, correção, achado). O usuário lê e converte em Task, Doc, Artefato, Base de Conhecimento, item de planejamento de projeto, doc vinculado a projeto, ou "task avulsa". Aceita anexos e pode encaminhar uma mensagem para o Telegram do usuário. |
| Docs | `/docs` | Área de criação: árvore de markdown editável (e uploads), cruzada com produtos/projetos/tasks via vínculos de documento (doc_links). |

### Planning
| Tela | Rota | Para que serve |
|---|---|---|
| Products | `/product` | Cadastro de produtos e suas versões. |
| Projects | `/projects` | Projetos ligados a uma versão de produto; cada um tem diretório de trabalho real no host. |
| Pipelines | `/pipeline` | Estágios de pipeline por projeto, com artefatos obrigatórios e portões de aprovação. |
| Templates | `/pipeline-templates` | Modelos reutilizáveis de pipeline. |
| Planning | `/backlog` | Itens de planejamento (feature/bug/hotfix/melhoria/dívida técnica/refactor/segurança/pesquisa/documentação) — o ponto de entrada genérico pro planejamento de uma versão. |
| Execution | `/tasks` | Tasks desdobradas de um item de planejamento (ou de uma change request), com execuções por agente. |
| Artifacts | `/artifact` | Entregáveis versionados (docs, código gerado, etc.) — sempre com um arquivo real por trás. |
| Governance | `/governance` | Aprovações e trilha de auditoria. |
| Policies | `/governance/policies` | Políticas de governança configuráveis. |

### Agents & AI
| Tela | Rota | Para que serve |
|---|---|---|
| Agents | `/agents` | Catálogo de agentes Hermes (Athos, Atlas, etc.) — metadados, missão, camada, se usa Telegram. |
| Agent Tools | `/tools` | Registro de ferramentas/scripts que os agentes têm disponíveis no host. |
| Chat Commands | `/prompt-commands` | Comandos de prompt reutilizáveis pro chat (nome/descrição/prompt). |
| Skills | `/skills` | Leitura/edição de SKILL.md dos agentes. |
| Crons | `/crons` | Jobs agendados por perfil de agente (`hermes cron`), com logs de execução. |
| Foundation | `/foundation` | Metadados da Fundação Hermes: SOUL.md, sub-agentes, regras de governança. |
| ForgeRouter | `/forgerouter` | Configuração de roteamento de LLM por projeto (Claude/Codex/Antigravity). |

### Integrations
| Tela | Rota | Para que serve |
|---|---|---|
| Kanboard | `/kanboard` | Sincronização com o board Kanboard real (projeto id 8). |
| Knowledge Base | `/obsidian` | Navegador/editor do vault Obsidian (só markdown, espelha o app desktop). |

### Operations
| Tela | Rota | Para que serve |
|---|---|---|
| System Control | `/system-control` | Status git deste repositório (branch, commit, arquivos modificados) e backup compactado de `/root/.hermes`. Somente leitura + uma ação de backup. |
| Hindsight | `/hindsight` | Status do daemon de memória contínua dos agentes (Hindsight): saúde, config de LLM, inventário de schema, logs. Ações admin: restart do container, limpar log. |
| Auditor | `/auditor` | Checklist de verificações do ecossistema (`audit_checks`), rodado via cron no host. |
| Deploy Control | `/deploy` | Controle de grupos de deploy e sincronização. |
| Servers | `/servers` | Inventário de servidores remotos (SSH), com checagem de status e instalação de chave pública. |
| Database | `/database/*` | Schema, diagrama ER e console de query (somente leitura) do Postgres. |

### Administration
| Tela | Rota | Para que serve |
|---|---|---|
| Users | `/users` | Cadastro de usuários. |
| Access Profiles | `/profiles` | Perfis de permissão (view/query/write/delete por módulo). |

## Documentação técnica por tela

`docs/screens/*.md` tem o detalhe técnico (rotas exatas com número de linha, hooks, endpoints, regras de negócio, estados de erro/loading) das telas já documentadas: `dashboard`, `workspace`, `products`, `projects`, `pipelines`, `backlog`, `tasks`, `artifacts`, `governance`, `agents`, `forgerouter`, `foundation`, `crons`, `kanboard`, `knowledge_base`.

**Ainda sem documentação técnica própria** (usar este manual + o código-fonte até serem escritos): Inbox (demands), Docs, Notifications, Templates (pipeline-templates), Policies, Agent Tools, Chat Commands, Skills, System Control, Hindsight, Auditor, Deploy Control, Servers, Database, Users, Access Profiles.

## Regras de negócio centrais

Ver `docs/BUSINESS_RULES.md` (Produto, Pipeline, Planejamento, Execução, Skill, Rastreabilidade, Governança) e `docs/DATA_MODEL.md` para o modelo de dados completo. `docs/PRD.md`/`docs/SPEC.md` são a fonte da visão de produto original; `CLAUDE.md` (raiz do repo) é a referência de como o sistema está de fato implementado hoje — em caso de conflito entre os dois, `CLAUDE.md` reflete o estado real do código.
