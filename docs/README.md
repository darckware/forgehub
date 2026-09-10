# ForgeHub — Mapa e Governança da Documentação

## Estrutura da pasta `docs/`

```
docs/
├── README.md                      ← este arquivo (índice)
├── architecture/                  ← arquitetura e contrato operacional
│   ├── ENGINEERING_LOOP.md
│   ├── IMPLEMENTATION_READINESS.md
│   ├── AGENT_CLI_DEVELOPMENT_PROTOCOL.md
│   ├── PLANNING_IMPLEMENTATION_BOUNDARY.md
│   └── PLANNING_DELIVERY_ARCHITECTURE.md
├── agents/                        ← organização e ecossistema de agentes
│   ├── AGENT_ORGANIZATION_CHART.md
│   ├── AGENT_ECOSYSTEM_ASSESSMENT.md
│   └── FOUNDATION_AGENT_ORGANIZATION.md
├── baseline/                      ← documentos históricos de origem
│   └── CONTEXT_BRIEF.md
├── guides/                        ← direção/visão de produto (dev-facing)
│   ├── PROJECT_DELIVERY_GUIDE.md
│   └── MESSAGES_TELEGRAM_OPERATIONS.md
├── reference/                     ← especificação técnica do estado atual
│   ├── DATA_MODEL.md
│   ├── BUSINESS_RULES.md
│   ├── TECHNOLOGY.md
│   └── DB_README.md
├── specs/                         ← visão original de produto (baseline)
│   ├── PRD.md
│   └── SPEC.md
├── specs-ready/                   ← (vazio — renomeado para baseline/)
├── stack/                         ← (vazio — reservado para arquivos de stack)
├── modules/                       ← specs de módulos implementáveis
│   ├── README.md
│   ├── 01_CONCEPTION_AND_SYSTEM_SCOPE.md
│   ├── 02_PIPELINE_AND_PLANNING.md
│   ├── 03_EXECUTION_AND_ORCHESTRATION.md
│   ├── 04_GOVERNANCE_AND_EVIDENCE.md
│   ├── 05_RELEASE_OPERATIONS_MAINTENANCE.md
│   ├── 06_COCKPIT_AND_INTEGRATIONS.md
│   ├── 07_ATHOS_CONTROL_ROOM.md
│   ├── 08_GOVERNED_PLANNING_APPROVAL.md
│   └── 09_STAGE_COMPLETION_AND_RECOVERY.md
├── screens/                       ← inventário de telas (parcial)
│   └── *.md
├── templates/                     ← templates canônicos
│   ├── MODULE_SPEC_TEMPLATE.md
│   └── DAILY_ENGINEERING_REVIEW.md
└── assets/
    └── forgehub-logo.svg
```

**`help/` (irmã de `docs/`, na raiz do repositório) é uma pasta separada** (2026-08-16, Marcelo:
"crie um pasta de help e adicione essa documentação separada do docs" / "a pasta docs, utilizada
mais para documentação do dev, e a pasta help para suporte e ajuda") para conteúdo de suporte
consultado por humano *e* por agente durante o **uso** do produto -- diferente de `docs/`, que é
governança/especificação para quem **desenvolve** o próprio ForgeHub. Contém:

- `MANUAL.md` -- manual operacional do usuário final (movido para fora de `docs/guides/`);
- `FORGEHUB_CHANNELS_AGENT_GUIDE.md` -- guia operacional do canal de agentes, enviado literalmente
  aos agentes dentro de uma mensagem de canal real (`backend/app/api/routes/channel.py`), mesma
  categoria de suporte do manual (movido para fora de `docs/guides/`);
- `TECH_STACK_GUIDE.md` -- guia de stack tecnológico para os produtos que o ForgeHub gerencia,
  consumido pelo botão "Gerar com agente" da Concepção.

---

## Finalidade

Este arquivo define como humanos e agentes devem interpretar a documentação do ForgeHub. Ele existe para impedir que uma LLM combine uma visão futura com um endpoint atual, trate uma proposta como implementada ou escolha arbitrariamente entre documentos divergentes.

## Planejamento de memória e rotinas — 2026-09-06

- [Registro central de pendências do Nexo, Headscale e Darckware](PENDENCIAS.md).
- [Runbook de pacotes e monitoramento do Nexo Remote Agent](runbooks/NEXO_AGENT_PACKAGES.md).
- [Plano de memória, recuperação de crons e coerência do ForgeHub](superpowers/plans/2026-09-06-collective-memory-governance.md).
- [Cartilha de autoconfiguração dos agentes externos](runbooks/EXTERNAL_AGENT_ECOSYSTEM_SELF_CONFIGURATION.md).
- [Baseline P0 de memória, crons e notificações](audits/2026-09-06-memory-cron-notification-baseline.md).

Ambos são propostas para revisão, sem implementação iniciada. O desenho local/VPS está sob
responsabilidade do Claude; a integração aguarda a conclusão desse planejamento. Cada agente
externo será responsável pela adequação da própria configuração conforme a cartilha aprovada.

## Hierarquia de autoridade

Quando houver conflito, use esta ordem:

1. **Código, migrations e testes executados** — comportamento implementado hoje.
2. **`reference/DATA_MODEL.md`, `reference/BUSINESS_RULES.md` e `reference/TECHNOLOGY.md`** — descrição do estado implementado, desde que confirmada pelo código.
3. **`architecture/PLANNING_DELIVERY_ARCHITECTURE.md`** — direção canônica do produto e arquitetura-alvo.
4. **`architecture/ENGINEERING_LOOP.md`** — contrato operacional-alvo para execução determinística por agentes/LLMs.
5. **`architecture/IMPLEMENTATION_READINESS.md`** — lacunas entre estado atual e arquitetura-alvo e ordem de fechamento.
6. **`architecture/AGENT_CLI_DEVELOPMENT_PROTOCOL.md`** — conduta transitória para executar Tasks no modelo disponível.
7. **`guides/PROJECT_DELIVERY_GUIDE.md` e `../help/MANUAL.md`** — experiência de uso desejada e orientação ao operador.
8. **`specs/PRD.md`, `specs/SPEC.md` e documentos de tela históricos** — baseline original; não substituem decisões posteriores.

Regra: documento de direção pode exigir uma mudança, mas não prova que ela já existe. Documento do estado atual pode descrever uma limitação, mas não revoga a arquitetura-alvo.

## Classificação dos documentos

| Documento | Papel | Estado |
|---|---|---|
| `baseline/CONTEXT_BRIEF.md` | contexto original do ForgeHub | histórico, válido como origem |
| `specs/PRD.md` | visão e requisitos originais | desatualizado para a arquitetura-alvo |
| `specs/SPEC.md` | especificação original de software | desatualizado para a arquitetura-alvo |
| `architecture/PLANNING_DELIVERY_ARCHITECTURE.md` | concepção consolidada e arquitetura-alvo | canônico para direção |
| `architecture/ENGINEERING_LOOP.md` | máquina operacional de engenharia e anti-alucinação | canônico para o runtime-alvo |
| `architecture/IMPLEMENTATION_READINESS.md` | auditoria de completude e sequência de implementação | canônico para planejamento técnico |
| `reference/DATA_MODEL.md` | dicionário do banco atualmente implementado | estado atual |
| `reference/BUSINESS_RULES.md` | regras aplicadas atualmente e inconsistências conhecidas | estado atual |
| `reference/TECHNOLOGY.md` | stack implementada | estado atual |
| `architecture/AGENT_CLI_DEVELOPMENT_PROTOCOL.md` | pacote e conduta de execução | transição atual → alvo |
| `guides/PROJECT_DELIVERY_GUIDE.md` | jornada operacional desejada | misto; confirmar disponibilidade |
| `guides/MESSAGES_TELEGRAM_OPERATIONS.md` | operação e recuperação de Messages, Telegram e gateways | estado atual verificado |
| `../help/MANUAL.md` | navegação e operação da aplicação atual | operacional |
| `agents/AGENT_ORGANIZATION_CHART.md` | organização operacional dos agentes | arquitetura organizacional |
| `agents/AGENT_ECOSYSTEM_ASSESSMENT.md` | justificativa e acionamento dos agentes | análise de apoio |
| `agents/FOUNDATION_AGENT_ORGANIZATION.md` | projeção proposta para Hermes Foundation | integração proposta |
| `screens/*.md` | inventário de telas selecionadas | parcial e não exaustivo |
| `templates/MODULE_SPEC_TEMPLATE.md` | contrato mínimo antes da implementação de um módulo | template canônico |
| `templates/DAILY_ENGINEERING_REVIEW.md` | revisão diária humana/agente | template canônico |
| `modules/README.md` e `modules/01_...` a `09_...` | contratos implementáveis por fatia | specs-alvo; exigem aprovação antes do código |
| `architecture/PLANNING_IMPLEMENTATION_BOUNDARY.md` | fronteira autorizada da primeira onda | escopo ativo da implementação |

## Leitura obrigatória por tipo de trabalho

### Para analisar ou planejar o produto

1. este arquivo;
2. `architecture/PLANNING_DELIVERY_ARCHITECTURE.md`;
3. `architecture/ENGINEERING_LOOP.md`;
4. `architecture/IMPLEMENTATION_READINESS.md`;
5. código e documentos do domínio afetado.

### Para implementar um módulo

1. identificar o item em `architecture/IMPLEMENTATION_READINESS.md`;
2. confirmar que o Definition Gate do módulo está completo;
3. ler o recorte correspondente da arquitetura-alvo;
4. inspecionar modelos, schemas, rotas, hooks e telas atuais;
5. seguir `architecture/AGENT_CLI_DEVELOPMENT_PROTOCOL.md`;
6. não implementar campos ou estados ainda não decididos sem registrar a decisão.

### Para operar o sistema atual

1. `../help/MANUAL.md`;
2. `guides/MESSAGES_TELEGRAM_OPERATIONS.md` para comunicação ou gateways;
3. `reference/DATA_MODEL.md` e `reference/BUSINESS_RULES.md` quando houver dúvida;
4. código/rotas atuais;
5. nunca presumir que itens marcados como propostos estejam disponíveis.

## Definition Gate de documentação

Um módulo só está pronto para implementação quando possui, no mínimo:

- objetivo, atores e limites de responsabilidade;
- entidades, atributos, relações, constraints e estratégia de migração;
- estados e transições, incluindo comandos inválidos;
- regras e Policies aplicáveis;
- contratos de API, erros, idempotência e autorização;
- telas, ações, estados vazios/loading/error e acessibilidade;
- eventos e registros de auditoria;
- integrações e comportamento em falha;
- critérios de aceite e testes de contrato, domínio e interface;
- observabilidade, rollout e rollback;
- indicação explícita do que permanece fora do escopo.

Descrição conceitual sem esses itens orienta design, mas não autoriza uma LLM a inventar a implementação.

## Regras contra alucinação documental

1. Não inferir que uma entidade proposta possui tabela ou endpoint.
2. Não inventar UUID, aprovação, evidência, Policy, estado de gate ou resultado de teste.
3. Não escolher silenciosamente entre nomes/estados divergentes; registrar conflito.
4. Não usar memória de conversa como fonte exclusiva de decisão.
5. Toda decisão nova precisa de registro durável e vínculo ao escopo afetado.
6. Toda execução recebe IDs, revisões e caminhos explícitos no Work Package.
7. Ausência de contexto obrigatório produz `blocked`, não preenchimento criativo.
8. Um agente pode propor a próxima ação; somente regras persistidas e autoridade adequada podem autorizá-la.

## Controle de revisão

Cada alteração arquitetural deve atualizar, conforme aplicável:

1. arquitetura-alvo;
2. readiness e ordem de implementação;
3. modelo de dados e regras quando implementada;
4. protocolo/loop quando muda a operação;
5. manual e telas quando muda a experiência;
6. migrations, testes e código.

Não se apaga uma decisão já utilizada por baseline ou release. Ela é superseded por uma revisão posterior, preservando motivo, autor, data e elementos impactados.
