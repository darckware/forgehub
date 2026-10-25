# Plano integrado do ecossistema — Service Factory, Missão, Operação 24x7 e Atividades dos Agentes

**Data:** 2026-10-24
**Status:** proposta para aprovação do Marcelo — organizada em três ondas (seção 0)
**Pedidos do Marcelo (24/10):**
- "integrar a missão com operação 24x7 e software factory, para gerenciar as tarefas e registro das implementações e da documentação"
- "o projeto criado não precisa ter um cliente associado, podendo ser um projeto interno"
- "eu ainda preciso validar o software factory, que ainda não foi testado. Esse módulo foi criado para o gerenciamento da implementação dos sistemas. O software factory também pode ser utilizado para manutenção de sistema e execução de serviços de manutenção, pois a VPN Tailscale possui o acesso a todas as estações de trabalho e servidores"
- "preciso adicionar no planejamento da implementação em um conjunto completo, interligando todos os componentes criados"
- "a tela de atividades dos agentes precisa acompanhar todas as rotinas e monitorar todos os agentes"
- "o Darckware precisa ser adicionado, ele é minha ponte com a internet para captação de cliente no nosso ecossistema"
- "a ideia do Software Factory é que o agente use o módulo e eu monitore as atividades e adicione anotações e documentações adicionais para ajudar no contexto"
- "o objetivo do Software Factory é o gerenciamento da documentação, manual do sistema, controle das tarefas, distribuição das demandas entre os agentes, para a pasta do projeto ficar organizada e bem descritiva, que eu possa administrar e auditar o desenvolvimento e ajudar no contexto do projeto: definição do escopo do sistema, banco de dados, deploy, metodologia e spec adotadas para implementação"
- "adicione design system, logomarca, etc"
- "queria evoluir software factory para service factory para englobar todos os serviços"
- "como quero implementar uma missão para o grupo de agentes, eles precisam registrar isso como um projeto no Service Factory para poderem gerenciar as atividades e a documentação dos projetos em execução e a distribuição das tarefas"
- "precisa criar um pipeline para missão, service factory, operação 24x7 e atividades dos agentes. A missão é a garantia que o serviço foi concluído, ele faz o controle e monitoramento da execução"
- "na missão pode nomear os agentes, orquestrador, os executores; o contexto da missão; a validação da documentação e do plano"
- "preciso criar uma área de teste; os agentes cadastrados no ForgeVault podem fazer login direto nos sistemas e serviços, para garantir a segurança e o acesso"
- "uma área em que o agente possa testar o sistema no navegador ... um navegador próprio para testes e execução de tarefas na internet, como captação de dados e gerenciamento de redes sociais"
- "queria adicionar o controle do contexto: memória dos agentes, Hindsight (memória estendida), base de conhecimento e a documentação da Foundation"

**Documentos ligados:** [missao-especificacao.md](missao-especificacao.md) (frente Missão),
`docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md` (Operação 24x7),
`docs/superpowers/plans/2026-10-02-roadmap-geral.md` (roadmap anterior),
`docs/architecture/REMOTE_MAINTENANCE_PLAN.md` (manutenção remota).

## Como ler

| Documento | Conteúdo |
|---|---|
| [01 — Diagnóstico e as três ondas](01-diagnostico-e-ondas.md) | O caminho está certo? Problemas de execução, as três ondas e as três decisões que bloqueiam o início |
| [02 — Visão e princípios](02-visao-e-principios.md) | Objetivo, o caminho único de todo trabalho, "o agente opera, o Marcelo supervisiona", para que serve o Service Factory |
| [03 — Service Factory](03-service-factory.md) | De Software Factory a Service Factory: linhas de serviço, **abertura de um novo projeto (sistema ou serviço)** e a Fase S |
| [04 — Missão](04-missao-pipeline-e-papeis.md) | **O essencial: quando começar, como validar a entrega, críticas com correção sugerida, dossiê de validação, quando concluir**; missão como projeto, o pipeline Missão → Service Factory → Operação 24x7 → Atividades, papéis, brief, validação do plano e da documentação |
| [05 — Componentes e interligações](05-componentes-e-interligacoes.md) | Os sete sistemas, o inventário de todos os módulos com decisão, tipos de trabalho e o mapa de ligações |
| [06 — Atividades dos Agentes](06-atividades-dos-agentes.md) | Acompanhar todas as rotinas e monitorar todos os agentes |
| [07 — Fases de implementação](07-fases-de-implementacao.md) | **O planejamento único:** todas as fases e tarefas (0 revisão, V, P, R, B, I, D, Q, T, F, N, A, O, E, C, M) com dono, dependência e aceite, e a ordem |
| [08 — Inteligência operacional](08-inteligencia-operacional.md) | O que é realista, o que falta para aprender e se corrigir, níveis de autonomia |
| [09 — Lacunas e decisões](09-lacunas-e-decisoes.md) | Lacunas encontradas nas revisões, riscos abertos e as decisões com os padrões adotados |
| [10 — Área de teste e identidade](10-area-de-teste-e-identidade.md) | Ambiente de teste isolado da produção e o ForgeVault como identidade única dos agentes em todos os sistemas (Fases T e F) |
| [11 — Navegador dos agentes](11-navegador-dos-agentes.md) | Sessões de navegador isoladas por agente e tarefa, modo teste (área de teste) e modo internet (coleta de dados, redes sociais), credenciais pelo ForgeVault, publicação com aprovação (Fase N) |
| [Modelos](modelos/) | [Termo de abertura](modelos/TERMO-DE-ABERTURA.md) (todo projeto novo), [Crítica de entrega](modelos/CRITICA-DE-ENTREGA.md) e [Dossiê de validação](modelos/DOSSIE-DE-VALIDACAO.md) (Missão) |
| [Consolidado da revisão](revisao/CONSOLIDADO.md) | Os 11 pareceres agrupados por tema, com análise e proposta para cada item, e as 8 decisões pendentes |
| [Roteiro de revisão crítica](revisao/ROTEIRO-DE-REVISAO.md) | Quem revisa cada camada, as perguntas, o formato do parecer e o processo, antes da implementação |
| [Especificação da Missão](missao-especificacao.md) | Detalhe técnico da Missão (modelo, fluxo, autonomia, arquitetura dos sete sistemas) |

**Referências por número de seção** (vindas do documento único original):

| Seção citada | Onde está |
|---|---|
| 0, 0.1, 0.2 | [01](01-diagnostico-e-ondas.md) |
| 1, 1.1, 1.2 | [02](02-visao-e-principios.md) |
| 1.3 e Fase S | [03](03-service-factory.md) |
| 1.4, M0, 1.5, 1.6 | [04](04-missao-pipeline-e-papeis.md) |
| 2, 2.1, 3, 4 | [05](05-componentes-e-interligacoes.md) |
| 5 | [06](06-atividades-dos-agentes.md) |
| 6 (todas as fases) | [07](07-fases-de-implementacao.md) |
| 7 e Fase G | [08](08-inteligencia-operacional.md) |
| 8, 9 | [09](09-lacunas-e-decisoes.md) |
| Fases T, F e N (desenho) | [10](10-area-de-teste-e-identidade.md), [11](11-navegador-dos-agentes.md); tarefas em [07](07-fases-de-implementacao.md) |

**Regra deste conjunto:** o escopo está congelado. Pedido novo vira item do projeto do plano no
Service Factory (quando a M0 o registrar), não texto novo nestes documentos. Atualizações de estado
(o que foi entregue) entram em [01](01-diagnostico-e-ondas.md) no mesmo commit da entrega.
