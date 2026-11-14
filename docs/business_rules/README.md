# Regras de negócio do ForgeHub

Este catálogo reúne as regras que agentes devem seguir ao analisar, implementar,
revisar ou operar o ForgeHub. Ele descreve o comportamento confirmado pelo código
e pelos testes; não substitui esses artefatos nem concede autorização para executar
uma ação.

**Base analisada:** branch `main`, commit `43a6a7f`, em 14/11/2026. Mudanças em
branches ou worktrees ainda não integrados não são apresentadas como comportamento
vigente.

## Como interpretar

- **IMPLEMENTADA** — há código ou migration que aplica a regra. Os testes citados
  mostram a cobertura conhecida; eles não ampliam a autorização definida pela regra.
- **PARCIAL** — parte do comportamento existe, mas falta enforcement, fluxo de uso,
  cobertura ou integração descrita na própria regra.
- **POLÍTICA** — decisão de negócio documentada, sem enforcement técnico completo.
- **GAP** — conflito ou ausência confirmada entre a regra esperada e o comportamento
  atual. Não presuma o resultado desejado: descreva a evidência e solicite decisão
  quando ela não estiver registrada.
- **HISTÓRICA** — informação mantida para explicar uma transição; não orienta a
  operação atual quando foi substituída por decisão posterior.

As referências a arquivos, funções, migrations e testes apontam a fonte que deve
ser lida antes de mudar a regra. Quando um documento antigo divergir do código e
dos testes atuais, registre a divergência em **GAP** e siga a hierarquia em
[`docs/README.md`](../README.md#hierarquia-de-autoridade). Não copie uma regra
para o código sem identificar seus atores, precondições, efeitos, exceções,
auditoria e testes.

## Índice por domínio

| Guia | Conteúdo |
|---|---|
| [01 — Identidade, acesso e governança](01-identidade-acesso-governanca.md) | Usuários, sessões, perfis, permissões, credenciais de agentes, delegações, aprovações e trilha de auditoria. |
| [02 — Agentes, Messages e canais](02-agentes-messages-canais.md) | Identidade/runtime, skills, Tasks, Incubações, dispatch, execução, falha, recuperação e comunicação. |
| [03 — Produtos, projetos e entrega](03-produtos-projetos-entrega.md) | Produtos/versões, planejamento, mudanças, pipelines, tarefas, evidências, artefatos, release e deploy. |
| [04 — Missões e orquestração](04-missoes-orquestracao.md) | Missões, ciclos, critérios, planos, execução, revisões, autonomia, dependências e limites de coordenação. |
| [05 — Acesso remoto e manutenção](05-acesso-remoto-manutencao.md) | Máquinas, autorização de agentes, scripts, comandos, arquivos, ForgeVault, pausa e histórico. |
| [06 — Operações e Auditor](06-operacoes-auditor.md) | Rotinas 24x7, ocorrências, auditorias, frescor de evidência, incidentes e remediação. |
| [07 — Dados, integrações e atendimento](07-dados-integracoes-atendimento.md) | Banco, documentos, canais, clientes, contatos, automações e integrações operacionais. |

## Fontes existentes relacionadas

- [`reference/BUSINESS_RULES.md`](../reference/BUSINESS_RULES.md) — catálogo anterior,
  centrado na arquitetura inicial de Products/Pipelines/Tasks; usar junto com os
  guias novos, pois não cobre todos os domínios atuais.
- [`reference/DATA_MODEL.md`](../reference/DATA_MODEL.md) — entidades e relações do
  modelo; confirmar o estado atual no código e nas migrations.
- [`reference/TECHNOLOGY.md`](../reference/TECHNOLOGY.md) — tecnologias e estrutura.
- [`docs/README.md`](../README.md) — hierarquia documental e regras para interpretar
  código atual, arquitetura-alvo, propostas e documentos históricos.
- [`architecture/MISSION_MESSAGES_OPERATING_FLOW.md`](../architecture/MISSION_MESSAGES_OPERATING_FLOW.md)
  — fluxo integrado de Missões, Messages e Operação 24x7; contém trechos de alvo e
  implementação, então confira a classificação de estado em cada guia.

## Manutenção do catálogo

Ao alterar comportamento de negócio:

1. Localize o ID da regra e confirme sua fonte implementada, migration e testes.
2. Atualize a regra e seus links na mesma mudança que altera o comportamento.
3. Acrescente ou ajuste testes para cada precondição, recusa, transição e efeito
   persistido afetado.
4. Mantenha histórico de decisões substituídas; marque a antiga como HISTÓRICA e
   ligue-a à regra que a substituiu.
5. Se implementação, testes e decisão de negócio não concordarem, registre GAP e
   não declare a regra concluída até resolver a divergência.

Este catálogo não substitui a confirmação operacional de que uma migration,
integração ou release foi instalada. Código preparado, mudança integrada e estado
em produção são fatos distintos.
