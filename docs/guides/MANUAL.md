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

Em **Messages**, o sidebar da tela (distinto do sidebar principal do ForgeHub) divide as mensagens em três grupos — **Incoming** (endereçadas a um agente), **Outgoing** (enviadas por um agente, ou compostas com Tipo=Task), **Notes** (arquivadas, com subpastas criáveis) — cada um com uma linha "System" (sem agente) e uma linha por agente registrado. Uma mensagem aberta em Incoming mostra o botão **Send to Outgoing**: abre um seletor de agente-destino + campo de instruções e despacha o conteúdo recebido + a instrução para esse agente executar de verdade (todo agente registrado é disparável desde 2026-07-25 — inclusive os oito profiles clássicos do Hermes e o Vector, não só Porthos/Aramis/Dartan). O status do disparo (fila/rodando/concluído/falhou) aparece na própria mensagem, e uma resposta volta automaticamente pro remetente quando "Retorno" foi marcado. Cada um dos três grupos tem um ícone de limpeza (lixeira, aparece no hover da linha raiz) que apaga permanentemente todas as mensagens daquele grupo, com confirmação; a barra superior da tela também tem "Keep last 30 days"/"Keep last 15 days"/"Clear all" para limpeza geral por idade. O botão "Notify via Telegram" foi removido da tela (2026-07-25) — encaminhar para o Telegram do usuário deixou de ser uma ação disponível na reading pane.

O botão **Login** usa a credencial de desenvolvimento configurada no backend. A senha atravessa somente a chamada interna backend → host bridge e não é retornada à interface nem persistida pelo módulo; cookies/localStorage ficam no perfil operacional protegido `/root/.forgehub/browser/athos`.

### Software Factory

Renomeada de "Planning" para "Software Factory" em 2026-07-26 — é a seção única do ciclo de desenvolvimento, organizada pela granularidade real do domínio: **Product** é durável (Concepção e Mapa do Sistema ficam no nível de produto, herdados por todo Project); cada evolução do produto vira um **Project**, que percorre as cinco fases; a cadeia completa é **Product → Project → Planejamento (grupos) → Task**. Arquitetura, classificação de projetos e operação detalhadas: [Planning e Delivery](PLANNING_DELIVERY_ARCHITECTURE.md). Funções por agente, orquestração e canais multiagente: [Canais, Funções e Orquestração](../architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md). Protocolo para Codex, Claude CLI e Agy: [Agentes CLI](AGENT_CLI_DEVELOPMENT_PROTOCOL.md). No código atual, Agy ainda aparece pelo identificador legado `antigravity`.

| Tela | Rota | Para que serve |
|---|---|---|
| Multi-Project Cockpit | `/cockpit` | Visão geral em árvore Produto → Projeto: ponto de entrada para cadastrar produto/projeto e navegar até cada detalhe. Não é uma fase, é o hub das outras seis. |
| Conception | `/conception` | Registra a ideia do Product, mantém revisões conceituais e submete a revisão exata para aprovação governada. |
| Screens & Business Rules | `/screen-inspector` | Telas do sistema, seus elementos/relações e regras de negócio — sucessora do antigo "System Map" no nível de produto. |
| Concept DB Diagram | `/concept-erd` | Diagrama ER derivado da modelagem de banco feita durante a Concepção. |
| Project Center | `/projects` | Projetos ligados a uma versão de produto; cada um tem diretório de trabalho real no host. A partir do detalhe de um Project (`/projects/:id`) chega-se a Escopo, Pipeline/Estágios, Planejamento (`/backlog`), Tasks (`/tasks`) e Artefatos (`/artifact`) daquele projeto — essas telas continuam existindo (ver rotas em `App.tsx`) mas não têm mais entrada própria no sidebar nem no Ctrl+K desde a reorganização de 2026-07-26; chegue a elas navegando a partir do Project ou do Cockpit. |
| Grupo de Trabalho (Canais) | `/workspace?view=channels` | Sala em tempo real onde você e os agentes conversam com contexto compartilhado — ver seção dedicada abaixo. Tecnicamente é a aba "Canais" do Workspace; o link do sidebar já abre direto nela. |
| Governance | `/governance` | Approval Inbox governado, decisões, trilha de auditoria e delegação limitada do Athos (e de qualquer outro agente-orquestrador). Políticas (`/governance/policies`) e Delegações de Autoridade ficam dentro dessa tela. |
| Version Closure | `/version-closure` | Fechamento de uma versão de produto: bloqueia se algum Project ainda tiver Task fora de `done/deployed/cancelled`, nunca força conclusão para desbloquear a si mesmo. |

#### Grupo de Trabalho (Canais): como usar

Um canal é uma sala persistente onde você (autenticado) e N agentes conversam com o mesmo histórico visível para todos — diferente do Workspace/Conversas (1 humano + 1 agente, sem contexto compartilhado). Cobre o mesmo papel que o board de tarefas de uma branch faz numa ferramenta como o Buzz: o canal é o ponto único onde se discute, propõe e acompanha o trabalho de um Project (ou de uma ideia sem projeto ainda).

1. **Criar um canal**: clique em "+" ao lado de CHANNELS. Dê um nome; o Project é opcional (uma sala pode ser só uma ideia livre) e pode ser anexado depois, a qualquer momento, como se fosse um MCP — nunca trava o canal num "modo". Os membros (agentes) são sempre uma escolha explícita sua, nunca herdados automaticamente do time do projeto — mesmo quando um Project é anexado, o time dele só aparece como sugestão.
2. **Função de cada especialista, já na criação**: ao marcar um agente como membro, aparece um resumo (a descrição cadastrada do agente) e um seletor de função — pré-preenchido com a função padrão do cadastro dele (`Agent.default_role`, editável na própria página do agente em "Função padrão"), mas você pode ajustar ali mesmo antes de criar a sala. Depois de criado, a função de cada membro continua editável a qualquer momento pelo seletor ao lado do nome no cabeçalho do canal.
3. **Orquestrador (opcional)**: ainda na criação (ou depois, clicando no ícone de coroa ao lado de um agente no cabeçalho), você pode designar um agente como orquestrador operacional daquele canal — por exemplo, o Athos coordenando os demais e as funções deles no projeto. Essa marcação é só informativa: ela não concede autoridade nenhuma sozinha. Você continua sendo o chefe (etiqueta "Chefe" ao lado do seu nome) e a autoridade final de qualquer decisão é sempre sua.
4. **Agentes propõem tarefas, mas ficam pendentes**: um agente-membro pode propor uma tarefa para si mesmo (dentro da própria função no canal) e ela já nasce liberada; propor uma tarefa **para outro agente** sempre cria uma Approval pendente de verdade, no mesmo mecanismo de Governance já usado no resto do sistema (Policy/Approval/trilha de auditoria) — nunca um campo booleano à parte. A tarefa fica visualmente bloqueada na aba Tasks do canal até alguém decidir.
5. **Decidir a proposta**: por padrão, só você decide — pelo botão Aprovar/Rejeitar que aparece na própria tarefa pendente do canal, ou pela tela Governance como qualquer outra Approval. Para que o agente-orquestrador decida em seu lugar (ex.: Athos aprovando propostas do time sem precisar de você em cada uma), conceda a ele, em Governance → Delegações de Autoridade, a ação `channel.member.role.assign` (para ele poder ajustar a função dos colegas no canal) e/ou `governance.approval.decide` (para ele poder decidir as propostas de tarefa) — a mesma credencial de serviço e o mesmo mandato com prazo que o resto do sistema já usa para delegar ao Athos, não um mecanismo novo exclusivo de canais.
6. **Rodar de verdade**: uma mensagem do canal vira uma execução real (dispara o CLI do agente) pelo mesmo caminho de despacho que qualquer Task do sistema usa — nunca um segundo executor. O resultado narra de volta no próprio canal como uma mensagem do sistema.

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

`docs/screens/*.md` tem o detalhe técnico (rotas exatas com número de linha, hooks, endpoints, regras de negócio, estados de erro/loading) das telas já documentadas: `dashboard`, `workspace`, `products`, `projects`, `pipelines`, `backlog`, `tasks`, `artifacts`, `governance`, `agents`, `forgerouter`, `foundation`, `crons`, `knowledge_base`.

**Ainda sem documentação técnica própria** (usar este manual + o código-fonte até serem escritos): Messages (demands), Docs, Notifications, Templates (pipeline-templates), Policies, Grupo de Trabalho (channels), Agent Tools, Chat Commands, Skills, System Control, Hindsight, Auditor, Deploy Control, Servers, Database, Users, Access Profiles.

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
