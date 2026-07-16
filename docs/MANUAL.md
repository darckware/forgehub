# ForgeHub — Manual do Sistema

## Índice

- [Propósito deste manual](#propósito-deste-manual)
- [O que é o ForgeHub](#o-que-é-o-forgehub)
- [Política do Assistente](#política-do-assistente--leia-isto-antes-de-operar-qualquer-coisa)
- [Como o sistema está organizado (sidebar)](#como-o-sistema-está-organizado-sidebar)
  - [General](#general) — Dashboard, Workspace, Notifications, Inbox, Docs
  - [Planning](#planning) — Conception, System Map, Project Scope, Products, Projects, Pipelines, Templates, Planning, Execution, Artifacts, Governance, Policies
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
- **Controlar integralmente a aplicação web na sessão compartilhada do Workspace quando o usuário enviar uma instrução explícita pelo composer do Assistente** — isso inclui navegar, clicar, rolar, focar, digitar, selecionar opções e enviar formulários necessários para cumprir o pedido. O agente selecionado deve inspecionar o estado antes de agir, limitar-se ao comando recebido e confirmar o resultado ao final; abrir a aba ou visualizar a página nunca autoriza interação automática.
- **Operar o sistema, mas exclusivamente via importação e exportação de dados** — ex.: exportar um relatório, importar uma planilha/CSV para popular registros através de um fluxo de import dedicado, gerar um arquivo de saída.
- **Enviar mensagens para o Inbox reportando problemas e sugestões de melhoria** que encontrar no sistema — mesmo canal (`POST /api/v1/demands`) já usado por agentes Hermes e pelo próprio usuário. É a forma correta de registrar um achado sem agir sozinho sobre ele: o usuário lê e decide o destino (task, projeto, base de conhecimento, planejamento).

**O assistente NUNCA pode:**
- Criar, editar ou excluir diretamente uma entidade do sistema (produto, versão, projeto, pipeline, item de planejamento, task, artefato, agente, usuário, permissão, configuração) fora de um fluxo de importação/exportação explícito **ou de uma instrução explícita do usuário no Assistente com o contexto do navegador compartilhado**.
- Alterar configurações do sistema, permissões de usuário, ou qualquer estado operacional (deploy, restart de serviço, etc.).
- Executar ação mutável por iniciativa própria ou a partir de contexto apenas visual. Fora de uma instrução explícita no Assistente com o contexto do navegador compartilhado, se a ação não for import/export, o assistente deve explicar o que precisa ser feito e apontar o usuário para a tela/botão correto.

Essa é uma fronteira de governança, não uma sugestão — qualquer implementação futura do assistente deve restringir as ferramentas/endpoints disponíveis a ele de acordo com essa política, não confiar só em uma instrução de prompt.

**Como o contexto da tela chega até você:** ao abrir o painel do Assistente (ou quando o usuário anexa o contexto da tela via "Use current X", "Assistant" no Workspace, ou os botões de enviar-ao-assistente de Tools/Skills/Crons/Auditor), a interface envia automaticamente um **turno inicial de contextualização** na mesma sessão — uma mensagem separada, anterior e independente da primeira mensagem real do usuário. **O usuário não vê esse turno** (nem a sua resposta a ele): ambos são gravados dentro de um bloco `[[forgehub:contexto-interno]] … [[/forgehub:contexto-interno]]` e removidos da transcrição. Responda a ele apenas com "ok", sem executar nada, e trate-o como contexto de fundo: não o cite literalmente nem se refira a "as instruções acima" como se o usuário as tivesse escrito.

**Idioma de resposta:** cada mensagem chega a você com uma instrução oculta de idioma no final (ex.: "responda sempre em português do Brasil"), definida no dropdown de Settings → AI chat (`CHAT_RESPONSE_LANGUAGE` no forgehub.config; catálogo de idiomas em `core/config.py`, hoje pt-BR, en, es, fr, de, it). Ela também é injetada pela interface — o usuário não a vê e não a escreveu; siga-a sem comentá-la.

## Como o sistema está organizado (sidebar)

### General
| Tela | Rota | Para que serve |
|---|---|---|
| Dashboard | `/` | Visão operacional do ambiente local: versões de CLIs instaladas e uso de recursos do host. Não mostra dados de domínio do ForgeHub. |
| Workspace | `/workspace` | Chat/retorno dos agentes, terminal real e navegador Chromium compartilhado com Athos por CDP. |
| Notifications | `/notifications` | Feed persistente de alertas — execuções de cron (sucesso/erro) e alertas de sistema (ex.: chegada de mensagem no Inbox). Mesmo sino que aparece no rodapé do sidebar. |
| Inbox | `/demands` | Canal de comunicação — qualquer agente ou o próprio usuário envia uma nota (ideia, procedimento, correção, achado). O usuário lê e converte em Task, Doc, Artefato, Base de Conhecimento, item de planejamento de projeto, doc vinculado a projeto, ou "task avulsa". Aceita anexos e pode encaminhar uma mensagem para o Telegram do usuário. |
| Docs | `/docs` | Área de criação: árvore de markdown editável (e uploads), cruzada com produtos/projetos/tasks via vínculos de documento (doc_links). |

No **Workspace**, o ícone de globo abre ou oculta o navegador interno sem encerrar a sessão. A imagem exibida vem da mesma sessão Chromium/CDP usada pelas ferramentas `browser_*` do Athos: navegação, cliques, preenchimento e screenshots do agente aparecem na tela. O painel lateral mantém prompt, passos e retorno final visíveis; a coluna estreita explica os comandos. O operador também pode clicar na imagem, digitar no campo focado e salvar a URL atual como aplicação.

O botão **Login** usa a credencial de desenvolvimento configurada no backend. A senha atravessa somente a chamada interna backend → host bridge e não é retornada à interface nem persistida pelo módulo; cookies/localStorage ficam no perfil operacional protegido `/root/.forgehub/browser/athos`.

### Planning

Arquitetura, classificação de projetos e operação detalhadas: [Planning e Delivery](PLANNING_DELIVERY_ARCHITECTURE.md). Protocolo para Codex, Claude CLI e Agy: [Agentes CLI](AGENT_CLI_DEVELOPMENT_PROTOCOL.md). No código atual, Agy ainda aparece pelo identificador legado `antigravity`.
| Tela | Rota | Para que serve |
|---|---|---|
| Conception | `/conception` | Registra a ideia, mantém revisões conceituais e submete a revisão exata para aprovação governada. |
| System Map | `/system-map` | Mantém o grafo versionado do sistema, seus elementos/relações e o hash usado na aprovação. |
| Project Scope | `/project-scope` | Define o delta de elementos e critérios de aceite de cada Project. |
| Products | `/product` | Cadastro de produtos e suas versões. |
| Projects | `/projects` | Projetos ligados a uma versão de produto; cada um tem diretório de trabalho real no host. |
| Pipelines | `/pipeline` | Estágios de pipeline por projeto, com artefatos obrigatórios e portões de aprovação. |
| Templates | `/pipeline-templates` | Modelos reutilizáveis de pipeline. |
| Planning | `/backlog` | Itens de planejamento (feature/bug/hotfix/melhoria/dívida técnica/refactor/segurança/pesquisa/documentação) — o ponto de entrada genérico pro planejamento de uma versão. |
| Execution | `/tasks` | Tasks desdobradas de um item de planejamento (ou de uma change request), com execuções por agente. |
| Artifacts | `/artifact` | Entregáveis versionados (docs, código gerado, etc.) — sempre com um arquivo real por trás. |
| Governance | `/governance` | Approval Inbox governado, decisões, trilha de auditoria e delegação limitada do Athos. |
| Policies | `/governance/policies` | Políticas de governança configuráveis. |

### Controle de conclusão e retomada

Nos detalhes de **Pipeline**, o cartão **Project progress** informa macrofluxo, última confirmação e primeira ação segura. Cada Stage apresenta:

- requisitos confirmados e pendentes;
- último checkpoint, ator e horário;
- ponto e motivo da interrupção;
- instrução de retomada;
- avaliação determinística de conclusão;
- ação governada para concluir quando o assessment estiver `ready`.

Use **Evaluate** depois de alterar artifacts, gates, dependências ou checkpoints. A conclusão não pode mais ser feita selecionando livremente `completed`: o command exige o assessment da revisão atual. Se qualquer requisito mudar, o assessment anterior aparece como `stale` e deve ser recalculado.

Execuções registram automaticamente checkpoints de início e término. Runtime/agente autorizado pode acrescentar checkpoints intermediários e usar os commands de bloqueio, pausa, reconciliação e retomada. Em uma interrupção:

1. consulte **Stopped at** e o último checkpoint confirmado;
2. não presuma falha apenas por heartbeat ausente;
3. reconcilie o processo ou efeito externo;
4. resolva o blocker ou obtenha a autoridade indicada;
5. retome a partir de **Resume from**;
6. preserve a tentativa anterior e suas evidências.

Em **Access Profiles**, as ações são `planning.progress.view`, `planning.progress.manage` e `planning.stage.complete`. O Athos precisa recebê-las explicitamente na delegação; revogação bloqueia a command seguinte.

### Agents & AI
| Tela | Rota | Para que serve |
|---|---|---|
| Agents | `/agents` | Organograma empresarial dos agentes Hermes: Athos, departamentos Tier A, setores Tier B, subagentes, funções, skills aprovadas e status da key ForgeRouter individual. |
| Agent Tools | `/tools` | Registro de ferramentas/scripts que os agentes têm disponíveis no host. |
| Chat Commands | `/prompt-commands` | Comandos de prompt reutilizáveis pro chat (nome/descrição/prompt). |
| Skills | `/skills` | Leitura/edição de SKILL.md dos agentes. |
| Crons | `/crons` | Jobs agendados por perfil de agente (`hermes cron`), com logs de execução. |
| Foundation | `/foundation` | Metadados da Fundação Hermes: SOUL.md, sub-agentes, regras de governança. |
| ForgeRouter | `/forgerouter` | Configuração de roteamento de LLM por projeto (Claude/Codex/Agy; alias legado `antigravity`). |

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

## Aprovação governada da concepção

1. Em **Access Profiles**, conceda explicitamente as ações sensíveis necessárias. A ausência de uma ação significa bloqueio; administradores possuem bypass explícito.
2. Em **Conception**, crie/revise a ideia e submeta a revisão. O ForgeHub registra a revisão e o hash exatos, executa a policy estruturada e cria uma Approval Request.
3. Um segundo usuário autorizado abre **Governance** e decide no **Governed Planning Approvals**. O autor da revisão não pode aprovar a própria produção quando a policy de separação de funções estiver ativa.
4. Depois da aprovação válida, a autorização do planejamento de entrega ainda é uma ação distinta e exige `planning.delivery.authorize`.

O nome do requester e do decisor vem da credencial autenticada; valores enviados pelo frontend não substituem essa identidade. Repetir uma decisão com a mesma chave de idempotência não cria outra decisão. Se revisão ou hash mudarem, a aprovação anterior não autoriza a nova baseline.

### Delegação limitada do Athos

Na tela **Governance**, um usuário com `governance.delegation.manage` pode conceder ao Athos ações específicas, escopo e prazo, e revogar o mandato a qualquer momento. A credencial de serviço é emitida pelos endpoints governados e o token só é exibido no momento da emissão; depois deve ser instalado no runtime autorizado do Athos. Credencial e delegação são verificadas em cada command.

Delegar `governance.approval.decide` não concede automaticamente `planning.delivery.authorize`, não permite autoaprovação nem concede execução. Após `ER-RUN-01`, execução exige separadamente as actions `planning.execution.*`, uma ExecutionWave aprovada/ativa e Work Package emitido. O mandato padrão de 24 horas do Athos não inclui `planning.execution.release`.

## Execution Release e CLIs governadas

Na tela **Planning > Execution**:

1. selecione Project, baseline e Tasks já atribuídas a memberships ativas;
2. crie a wave em `draft` e execute **Preflight**;
3. um ator com `planning.execution.release` aprova a wave;
4. ative a wave para mover somente Tasks elegíveis a `ready`;
5. para cada Task, construa o Work Package com paths, critérios e DoD;
6. emita o package e despache Claude, Codex ou Agy;
7. acompanhe Execution, checkpoints e resultado; use pause/cancel/reconcile em falhas;
8. submeta a revisão independente. Exit code zero gera `completed`, não `verified`; review aprovado promove a tentativa e conclui a Task.

O dispatch direto antigo foi desativado. Reinício do bridge preserva estado seguro por run e reconcilia o PID; prompts e credenciais não são persistidos. Rework cria outra revisão do package e outra tentativa, mantendo o histórico anterior.

## Documentação técnica por tela

`docs/screens/*.md` tem o detalhe técnico (rotas exatas com número de linha, hooks, endpoints, regras de negócio, estados de erro/loading) das telas já documentadas: `dashboard`, `workspace`, `products`, `projects`, `pipelines`, `backlog`, `tasks`, `artifacts`, `governance`, `agents`, `forgerouter`, `foundation`, `crons`, `kanboard`, `knowledge_base`.

**Ainda sem documentação técnica própria** (usar este manual + o código-fonte até serem escritos): Inbox (demands), Docs, Notifications, Templates (pipeline-templates), Policies, Agent Tools, Chat Commands, Skills, System Control, Hindsight, Auditor, Deploy Control, Servers, Database, Users, Access Profiles.

## Regras de negócio centrais

## Organograma e operação dos agentes

O ecossistema atual possui oito Agents principais Tier A: Athos como Orquestrador e sete responsáveis departamentais. Athos recebe objetivos, organiza o planejamento e monta a menor equipe necessária; não executa automaticamente o trabalho de todos os departamentos.

Os departamentos atuais são Product & Planning, Engineering, Knowledge & Context, Documentation, Governance & Compliance, Platform & Operations e Security & Assurance. Agents Tier B ocupam setores especializados e entram no projeto somente quando tipo, fase, risco ou tecnologia exigirem. SubAgents são workers de escopo restrito e permanecem subordinados ao Agent responsável.

Na tela `/agents`, use o organograma para verificar:

1. responsável Tier A de cada departamento;
2. setor e função de cada especialista Tier B;
3. relação de reporte;
4. Skills versionadas e aprovadas que cobrem a função;
5. presença da API key ForgeRouter individual;
6. workers/subagentes vinculados ao responsável.

Para cadastrar a key, abra o Agent e use o cartão **ForgeRouter API key**. A chave é aceita para gravação, criptografada e nunca exibida novamente. Execuções sem key são bloqueadas. Em Settings, o catálogo **ForgeRouter virtual models** apresenta `auto`, `simple`, `standard`, `complex`, `reasoning`, `vision`, `audio` e `code`; `auto` é o padrão principal recomendado.

Comercial e Redes Sociais são áreas de crescimento previstas. Devem começar como demandas e setores sob coordenação de Athos, com aprovação humana para ações externas. Uma nova liderança Tier A só deve ser criada quando volume, risco e conflito de prioridades demonstrarem necessidade permanente.

O organograma completo, avaliação de necessidade, sobreposições e plano de crescimento estão em [Organograma de Agentes](AGENT_ORGANIZATION_CHART.md) e [Avaliação do Ecossistema](AGENT_ECOSYSTEM_ASSESSMENT.md).

Ver `docs/BUSINESS_RULES.md` (Produto, Pipeline, Planejamento, Execução, Skill, Rastreabilidade, Governança) e `docs/DATA_MODEL.md` para o modelo de dados completo. `docs/PRD.md`/`docs/SPEC.md` são a fonte da visão de produto original; `CLAUDE.md` (raiz do repo) é a referência de como o sistema está de fato implementado hoje — em caso de conflito entre os dois, `CLAUDE.md` reflete o estado real do código.
