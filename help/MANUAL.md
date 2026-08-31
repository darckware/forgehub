# ForgeHub — Manual do Sistema

## Índice

- [Propósito deste manual](#propósito-deste-manual)
- [O que é o ForgeHub](#o-que-é-o-forgehub)
- [Política do Assistente](#política-do-assistente--leia-isto-antes-de-operar-qualquer-coisa)
- [Como o sistema está organizado (sidebar)](#como-o-sistema-está-organizado-sidebar)
  - [General](#general) — Dashboard, Workspace, Notifications, Messages, Docs
  - [Software Factory](#software-factory) — Multi-Project Cockpit, Conception, Screens & Business Rules, Concept DB Diagram, Project Center, Grupo de Trabalho (Canais), Governance, Version Closure
  - [Agents & AI](#agents--ai) — Agents, Agent Tools, Chat Commands, Skills, Crons, Foundation, ForgeRouter
  - [Integrations](#integrations) — Knowledge Base
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
- **Enviar mensagens para Messages reportando problemas e sugestões de melhoria** que encontrar no sistema — mesmo canal (`POST /api/v1/demands`) já usado por agentes Hermes e pelo próprio usuário. É a forma correta de registrar um achado sem agir sozinho sobre ele: o usuário lê e decide o destino (task, projeto, base de conhecimento, planejamento).

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
| Messages | `/demands` | Canal de comunicação agente-a-agente e humano-a-agente (internamente ainda a tabela/rota `demands`, "Inbox" no código) — qualquer agente ou o próprio usuário envia uma nota (ideia, procedimento, correção, achado) ou uma mensagem endereçada a outro agente. Aceita anexos, agendamento de envio e disparo real do agente destinatário. |
| Docs | `/docs` | Área de criação: árvore de markdown editável (e uploads), cruzada com produtos/projetos/tasks via vínculos de documento (doc_links). |

No **Workspace**, o ícone de globo abre ou oculta o navegador interno sem encerrar a sessão. A imagem exibida vem da mesma sessão Chromium/CDP usada pelas ferramentas `browser_*` do Athos: navegação, cliques, preenchimento e screenshots do agente aparecem na tela. O painel lateral mantém prompt, passos e retorno final visíveis; a coluna estreita explica os comandos. O operador também pode clicar na imagem, digitar no campo focado e salvar a URL atual como aplicação.

Em **Messages**, comunicação e execução compartilham um envelope rastreável, mas não substituem chat: Conversation/Channels são para diálogo contínuo; Messages é para handoff, incubação, despacho e resultado auditável. **Incoming** contém cartas de retorno entregues ao solicitante; **Outgoing** contém trabalho ainda não iniciado; **Incubation**, **Running**, **Completed** e **Failed** representam estados exclusivos do trabalho; **Archived** organiza o histórico. Uma Task endereçada aciona o worker de execução imediatamente depois de ser salva; a verificação periódica de 30 segundos existe apenas para recuperação. Uma mensagem em Incoming pode ser encaminhada a um agente com instruções. Quando "Retorno" foi solicitado, o resultado gera uma carta ligada por `reply_to_id`; ela não é contada novamente como uma segunda execução concluída. Resultados originados em Channels voltam ao transcript do canal. O retorno externo pelo Telegram é opt-in: só ocorre quando o próprio assunto ou corpo da mensagem pede explicitamente resposta pelo Telegram; metadados `channel`/`channel_ref` sozinhos não autorizam o envio. Quando solicitado, usa o chat e o bot do agente corretos.

O botão **Login** usa a credencial de desenvolvimento configurada no backend. A senha atravessa somente a chamada interna backend → host bridge e não é retornada à interface nem persistida pelo módulo; cookies/localStorage ficam no perfil operacional protegido `/root/.forgehub/browser/athos`.

### Software Factory

A Software Factory é o motor unificado do ciclo de desenvolvimento de software (AI-SDLC) do ForgeHub. Toda a esteira é governada e dividida em 7 módulos claros, garantindo rastreabilidade desde a concepção do produto até a entrega final em produção:

1. **Concepção & Contexto (`/conceptions`)**: Registra a abertura da demanda vinculada a um **Produto** existente (ou novo), classificando o tipo de abertura como **🚀 Nova Implementação** (novas features / módulos) ou **🔧 Manutenção** (sustentação / correção / melhorias). Define a stack tecnológica (Frontend, Backend, Database) e gera 1 ou N Projetos associados.
2. **Telas & Regras (`/screen-inspector`)**: Mapeamento completo de telas, rotas, protótipos de interface e regras de negócio de cada projeto.
3. **Banco de Dados & ERD (`/concept-erd`)**: Modelagem do Diagrama Entidade-Relacionamento, schemas, tabelas, campos, chaves e relacionamentos.
4. **Central de Projetos & Backlog (`/projects`)**: Estrutura hierárquica **1 Projeto → N Itens de Planejamento → N Tarefas**. Visualização Master-Detail interativa com filtros de status (*Abertos, Em Execução, Finalizados, Com Bloqueio / Erro*).
5. **Gate de Governança (`/governance`)**: Gate de validação formal de planejamento. Itens não validados permanecem em **Backlog** (`new`); em revisão ficam **Em Análise** (`triaged`); ao clicar em **Liberar p/ Execução** (`in_progress`), o operador **seleciona o Agente Executor** responsável pelas tarefas.
6. **Cockpit de Execução (`/cockpit`)**: Painel de visualização e acompanhamento em tempo real das ondas de execução e progresso dos agentes.
7. **Fechamento de Versão & Produção (`/version-closure`)**: Checklist de auditoria 100% de tarefas. O botão de publicação é bloqueado se houver pendências. Ao publicar a versão, o projeto é marcado como `completed` e os itens de planejamento como `done`, tornando o projeto **permanentemente bloqueado contra alterações**.

| Tela | Rota | Para que serve |
|---|---|---|
| Multi-Project Cockpit | `/cockpit` | Painel de monitoramento visual das fases e acompanhamento da execução em tempo real. |
| Conception | `/conceptions` | Abertura do projeto associado ao Produto, seleção de Nova Implementação vs Manutenção e definição da Stack. |
| Screens & Business Rules | `/screen-inspector` | Inventário de telas, rotas e regras de negócio do projeto. |
| Concept DB Diagram | `/concept-erd` | Diagrama ER e schemas de dados do projeto. |
| Project Center | `/projects` | Central de projetos relacionando N planejamentos e N tarefas por projeto. |
| Grupo de Trabalho (Canais) | `/workspace?view=channels` | Sala de colaboração em tempo real entre humano e múltiplos agentes com contexto compartilhado. |
| Governance | `/governance` | Gate de liberação de planejamento para execução com atribuição de Agente Executor e auditoria. |
| Version Closure | `/version-closure` | Fechamento do projeto com checagem 100% concluída, geração de versão e bloqueio permanente. |

---

### Servidor MCP Unificado (`forgehub`)

O ForgeHub disponibiliza o servidor MCP oficial **`forgehub`** via protocolo JSON-RPC 2.0 (stdio), permitindo que agentes de IA autônomos (Claude Code, Hermes, Antigravity, OpenClaw, Codex) interajam diretamente com o ciclo de desenvolvimento e colaborem entre si:

- **Script de Execução**: `backend/app/mcp/factory_server.py`
- **Registro Global**: Tabela `company.mcp_catalog_servers` (`forgehub`) com `apply_to_all_agents: true`.
- **Ferramentas de AI-SDLC**:
  - `list_projects`, `get_project_context`: Contexto do produto, versão, stack e working directory.
  - `list_project_screens`, `get_project_erd`: Leitura de telas, regras de negócio e diagramas de banco de dados.
  - `list_planning_items`, `list_project_tasks`: Leitura do backlog e tarefas de execução.
  - `update_task_status`: Atualização do status de tarefas pelo agente em tempo real.
  - `report_governance_blocker`: Sinalização de bloqueios técnicos/negociais para a Governança.
  - `get_product_evolution_history`: Histórico de versões e releases anteriores.
- **Ferramentas de Comunicação Inter-Agentes**:
  - `send_agent_message`, `list_agent_messages`, `check_agent_inbox`, `propose_channel_task`, `list_my_incubation`, `receive_incubation`, `list_agent_skills`.

### Controle de conclusão e retomada

Nos detalhes de **Pipeline** (`/pipeline/:id`, acessível a partir do detalhe de um Project em **Project Center**), o cartão **Project progress** informa macrofluxo, última confirmação e primeira ação segura. Cada Stage apresenta:

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
| Técnicas de Prompt | `/prompt-techniques` | Catálogo pesquisável de estratégias classificadas para texto, software, agentes, pesquisa, conteúdo, design, automação, imagem e vídeo, com notas de uso e esforço. |
| Skills | `/skills` | Leitura/edição de SKILL.md dos agentes. |
| Crons | `/crons` | Jobs agendados por perfil de agente (`hermes cron`), com logs de execução. |
| Foundation | `/foundation` | Metadados da Fundação Hermes: SOUL.md, sub-agentes, regras de governança. |
| ForgeRouter | `/forgerouter` | Configuração de roteamento de LLM por projeto (Claude/Codex/Agy; alias legado `antigravity`). |

### Integrations
| Tela | Rota | Para que serve |
|---|---|---|
| Knowledge Base | `/obsidian` | Navegador/editor do vault Obsidian (só markdown, espelha o app desktop). |

### Operations
| Tela | Rota | Para que serve |
|---|---|---|
| System Control | `/system-control` | Status git deste repositório (branch, commit, arquivos modificados) e backup compactado de `/root/.hermes`. Somente leitura + uma ação de backup. |
| Hindsight | `/hindsight` | Status do daemon de memória contínua dos agentes (Hindsight): saúde, config de LLM, inventário de schema, logs. Ações admin: restart do container, limpar log. |
| Auditor | `/auditor` | 38 controles do ecossistema, incluindo auditoria individual dos oito profiles. Permite filtrar por profile, ver contexto/evidência/histórico e, quando houver correção determinística, aplicá-la com confirmação administrativa e reverificação automática. |
| Deploy Control | `/deploy` | Controle de grupos de deploy e sincronização. |
|| Servers | `/servers` | Inventário de servidores remotos (SSH), com checagem de status, instalação de chave pública e **cofre de chaves**: uma cópia criptografada da chave privada guardada na linha do servidor, para que perder o arquivo no host não signifique perder o acesso. Guardar, restaurar e remover a cópia são ações administrativas e sempre explícitas — nada é feito automaticamente. **Registro canônico:** `docs/SERVERS_SSH_REGISTRY.md` (13 servidores, 1 serviço, verificado 2026-08-14). |
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

Na tela **Tasks** (`/tasks`, acessível a partir do detalhe de um Project em **Project Center**):

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

`docs/screens/*.md` tem o detalhe técnico (rotas exatas com número de linha, hooks, endpoints, regras de negócio, estados de erro/loading) das telas já documentadas: `dashboard`, `workspace`, `products`, `projects`, `pipelines`, `backlog`, `tasks`, `artifacts`, `governance`, `agents`, `forgerouter`, `foundation`, `crons`, `knowledge_base`, `servers`.

**Ainda sem documentação técnica própria** (usar este manual + o código-fonte até serem escritos): Docs, Notifications, Templates (pipeline-templates), Policies, Grupo de Trabalho (channels), Agent Tools, Chat Commands, Skills, System Control, Hindsight, Auditor, Deploy Control, Database, Users, Access Profiles. Messages possui o runbook técnico `docs/guides/MESSAGES_TELEGRAM_OPERATIONS.md`.

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

Para cadastrar a key, abra o Agent e use o cartão **ForgeRouter API key**. A chave é aceita para gravação, criptografada e nunca exibida novamente. Desde 2026-07-25 a key deixou de ser obrigatória para disparar um agente: sem ela, o disparo (via Messages, veja acima) roda com a autenticação nativa já configurada naquele CLI no host (assinatura do Claude Code, `auth.json` do Codex, token OAuth do Antigravity) em vez de bloquear a execução — a key continua sendo a forma de rotear especificamente via ForgeRouter quando isso é desejado. Athos e os outros sete profiles clássicos do Hermes, além do Vector, nunca precisaram dessa key: já têm credencial própria configurada no profile/`openclaw.json`. Em Settings, o catálogo **ForgeRouter virtual models** apresenta `auto`, `simple`, `standard`, `complex`, `reasoning`, `vision`, `audio` e `code`; `auto` é o padrão principal recomendado.

Comercial e Redes Sociais são áreas de crescimento previstas. Devem começar como demandas e setores sob coordenação de Athos, com aprovação humana para ações externas. Uma nova liderança Tier A só deve ser criada quando volume, risco e conflito de prioridades demonstrarem necessidade permanente.

O organograma completo, avaliação de necessidade, sobreposições e plano de crescimento estão em [Organograma de Agentes](AGENT_ORGANIZATION_CHART.md) e [Avaliação do Ecossistema](AGENT_ECOSYSTEM_ASSESSMENT.md).

Ver `docs/reference/BUSINESS_RULES.md` (Produto, Pipeline, Planejamento, Execução, Skill, Rastreabilidade, Governança) e `docs/reference/DATA_MODEL.md` para o modelo de dados completo. `docs/specs/PRD.md`/`docs/specs/SPEC.md` são a fonte da visão de produto original; `CLAUDE.md` (raiz do repo) é a referência de como o sistema está de fato implementado hoje — em caso de conflito entre os dois, `CLAUDE.md` reflete o estado real do código.
