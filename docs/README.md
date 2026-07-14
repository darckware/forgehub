# ForgeHub — Mapa e Governança da Documentação

## Finalidade

Este arquivo define como humanos e agentes devem interpretar a documentação do ForgeHub. Ele existe para impedir que uma LLM combine uma visão futura com um endpoint atual, trate uma proposta como implementada ou escolha arbitrariamente entre documentos divergentes.

## Hierarquia de autoridade

Quando houver conflito, use esta ordem:

1. **Código, migrations e testes executados** — comportamento implementado hoje.
2. **`DATA_MODEL.md`, `BUSINESS_RULES.md` e `TECHNOLOGY.md`** — descrição do estado implementado, desde que confirmada pelo código.
3. **`PLANNING_DELIVERY_ARCHITECTURE.md`** — direção canônica do produto e arquitetura-alvo.
4. **`ENGINEERING_LOOP.md`** — contrato operacional-alvo para execução determinística por agentes/LLMs.
5. **`IMPLEMENTATION_READINESS.md`** — lacunas entre estado atual e arquitetura-alvo e ordem de fechamento.
6. **`AGENT_CLI_DEVELOPMENT_PROTOCOL.md`** — conduta transitória para executar Tasks no modelo disponível.
7. **`PROJECT_DELIVERY_GUIDE.md` e `MANUAL.md`** — experiência de uso desejada e orientação ao operador.
8. **`PRD.md`, `SPEC.md` e documentos de tela históricos** — baseline original; não substituem decisões posteriores.

Regra: documento de direção pode exigir uma mudança, mas não prova que ela já existe. Documento do estado atual pode descrever uma limitação, mas não revoga a arquitetura-alvo.

## Classificação dos documentos

| Documento | Papel | Estado |
|---|---|---|
| `CONTEXT_BRIEF.md` | contexto original do ForgeHub | histórico, válido como origem |
| `PRD.md` | visão e requisitos originais | desatualizado para a arquitetura-alvo |
| `SPEC.md` | especificação original de software | desatualizado para a arquitetura-alvo |
| `PLANNING_DELIVERY_ARCHITECTURE.md` | concepção consolidada e arquitetura-alvo | canônico para direção |
| `ENGINEERING_LOOP.md` | máquina operacional de engenharia e anti-alucinação | canônico para o runtime-alvo |
| `IMPLEMENTATION_READINESS.md` | auditoria de completude e sequência de implementação | canônico para planejamento técnico |
| `DATA_MODEL.md` | dicionário do banco atualmente implementado | estado atual |
| `BUSINESS_RULES.md` | regras aplicadas atualmente e inconsistências conhecidas | estado atual |
| `TECHNOLOGY.md` | stack implementada | estado atual |
| `AGENT_CLI_DEVELOPMENT_PROTOCOL.md` | pacote e conduta de execução | transição atual → alvo |
| `PROJECT_DELIVERY_GUIDE.md` | jornada operacional desejada | misto; confirmar disponibilidade |
| `MANUAL.md` | navegação e operação da aplicação atual | operacional |
| `AGENT_ORGANIZATION_CHART.md` | organização operacional dos agentes | arquitetura organizacional |
| `AGENT_ECOSYSTEM_ASSESSMENT.md` | justificativa e acionamento dos agentes | análise de apoio |
| `FOUNDATION_AGENT_ORGANIZATION.md` | projeção proposta para Hermes Foundation | integração proposta |
| `screens/*.md` | inventário de telas selecionadas | parcial e não exaustivo |
| `templates/MODULE_SPEC_TEMPLATE.md` | contrato mínimo antes da implementação de um módulo | template canônico |
| `templates/DAILY_ENGINEERING_REVIEW.md` | revisão diária humana/agente | template canônico |
| `modules/README.md` e `modules/01_...` a `07_...` | contratos implementáveis por fatia | specs-alvo; exigem aprovação antes do código |
| `PLANNING_IMPLEMENTATION_BOUNDARY.md` | fronteira autorizada da primeira onda | escopo ativo da implementação |

## Leitura obrigatória por tipo de trabalho

### Para analisar ou planejar o produto

1. este arquivo;
2. `PLANNING_DELIVERY_ARCHITECTURE.md`;
3. `ENGINEERING_LOOP.md`;
4. `IMPLEMENTATION_READINESS.md`;
5. código e documentos do domínio afetado.

### Para implementar um módulo

1. identificar o item em `IMPLEMENTATION_READINESS.md`;
2. confirmar que o Definition Gate do módulo está completo;
3. ler o recorte correspondente da arquitetura-alvo;
4. inspecionar modelos, schemas, rotas, hooks e telas atuais;
5. seguir `AGENT_CLI_DEVELOPMENT_PROTOCOL.md`;
6. não implementar campos ou estados ainda não decididos sem registrar a decisão.

### Para operar o sistema atual

1. `MANUAL.md`;
2. `DATA_MODEL.md` e `BUSINESS_RULES.md` quando houver dúvida;
3. código/rotas atuais;
4. nunca presumir que itens marcados como propostos estejam disponíveis.

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
