# ForgeHub — Loop de Engenharia Governado

## 1. Objetivo

Este documento define como o ForgeHub conduz uma LLM ou agente por todo o ciclo de engenharia sem depender da memória da conversa, da personalidade do modelo ou de decisões implícitas. O ForgeHub é o control plane; a LLM interpreta e produz trabalho dentro de um contrato autorizado.

O runtime de implementação suportado nesta arquitetura é fechado inicialmente em três CLIs: Claude (`claude`), Codex (`codex`) e Agy (`agy`). `antigravity` é alias legado de Agy durante a migração. Adicionar outro runtime exige adapter versionado e aprovação de governança. Trocar a CLI/modelo não pode mudar a fonte de verdade, pular gate ou perder histórico.

O loop é independente do tipo de entrega. Pode governar um sistema completo ou um único componente; o que muda é o ProjectScope e o template resolvido. Categorias não aplicáveis devem ser marcadas explicitamente como `not_applicable`, nunca simplesmente omitidas e depois inferidas pela LLM.

> **Nota de implementação (2026-08-17):** o gate de evidência (§8, `TaskExecution: completed -> verified`) e o loop produtor-revisor com `changes_requested` (§9) descritos abaixo já têm uma implementação real no caminho canônico de dispatch (`task.py`/Messages, não o Execution Wave/Work Package deste documento) — ver `PLANNING_DELIVERY_ARCHITECTURE.md` §6.6 para o que foi construído, os arquivos exatos e a lacuna de reconciliação ainda pendente entre os dois pipelines de revisão.

## 2. Princípio central

```text
A LLM propõe e executa.
ForgeHub valida, autoriza, persiste e calcula o próximo estado.
Um revisor independente ou humano decide quando a Policy exigir.
```

Nenhum prompt é a máquina de estados. Estados, transições, dependências, leases, revisões, Policies, evidências e aprovações pertencem aos dados persistidos e às regras de domínio.

## 2.1 Gestão humana ou por agente

O mesmo processo pode ser conduzido pelo operador ou por um agente. Ambos usam os mesmos comandos de domínio; muda a autoridade concedida, não a integridade das regras.

| Modo | Agente | Operador humano |
|---|---|---|
| manual | analisa e sugere | escolhe e autoriza cada ação |
| assistido | prepara artifacts, impactos e plano | aprova dispatches e transições |
| autonomia supervisionada | executa/revisa/replaneja dentro do Stage, orçamento e Policies | decide gates críticos, mudanças de escopo e exceções |
| autonomia delegada | percorre ações elegíveis de múltiplos Stages dentro de um mandato limitado | acompanha Cockpit, recebe escalations e pode intervir |

O modo é configurado por Project e pode ser restringido por Stage, ação, risco, ambiente, custo ou Policy. Não é uma permissão irrestrita atribuída à personalidade do agente.

Toda ação registra:

```yaml
actor_type: human | agent | system
actor_id: <uuid>
authority_source: user_role | project_membership | delegation | policy
delegation_id: <uuid|null>
command: <domain command>
reason: <structured reason>
input_revision: <revision/hash>
```

O Cockpit sempre exibe `current_controller`, `next_decision_owner` e `autonomy_boundary`.

Por padrão, `current_controller=Athos` quando existe delegação ativa. Athos usa os comandos do ForgeHub como coordinator; Agents especialistas recebem Assignments e Claude/Codex/Agy executam seus Work Packages. Na ausência, expiração ou revogação da delegação, o controle retorna ao usuário e novos dispatches automáticos param.

### Delegação

Uma delegação contém escopo e expiração:

- Product/Project/Stage/ScopeItems abrangidos;
- comandos permitidos;
- paths, runtimes e ferramentas;
- orçamento, concorrência e número de iterações;
- risco máximo e ambientes permitidos;
- approvals que continuam humanos;
- data de expiração e condições de revogação.

O agente pode administrar prioridades, dispatch e rework somente dentro desse mandato. Delegação nunca concede autoaprovação quando separation of duties exigir outro ator.

### Intervenção e retomada humana

O operador pode, a qualquer momento:

1. pausar novos dispatches;
2. deixar execuções seguras terminarem ou solicitar cancelamento;
3. assumir a próxima decisão;
4. alterar prioridade antes da baseline ou abrir Change Request depois dela;
5. revogar/reduzir delegação;
6. aprovar, rejeitar ou solicitar revisão;
7. devolver o controle ao agente com nova revisão do mandato.

Intervenção preserva eventos e resultados já produzidos. Uma execução iniciada com contexto antigo não pode continuar silenciosamente depois de mudança relevante; ela é reconciliada, cancelada ou marcada stale.

## 3. Loops aninhados

O processo possui quatro loops, todos limitados e auditáveis:

```text
Product Lifecycle Loop
  Concepção -> Construção/Entrega -> Operação/Manutenção/Evolução

Project Pipeline Loop
  Stage ready -> active -> verification -> approval -> completed

Scope Coverage Loop
  identified -> specified -> designed -> planned -> implemented
             -> verified -> released -> delivered -> operationally_verified

Task Engineering Loop
  prepare -> authorize -> execute -> verify -> review -> accept/rework
```

O loop interno nunca pode avançar o externo diretamente. Concluir uma Task não conclui automaticamente um Stage; concluir um Stage não cria Release; produzir Release não prova Deployment.

Planejamento e execução também são separados: criar uma Task com status `planned` não a torna consumível por executor. `ReleaseExecutionWave` seleciona Tasks elegíveis após baseline e move-as para `ready`; somente então scheduling/dispatch pode ocorrer.

## 4. Fontes de verdade

| Informação | Fonte autoritativa |
|---|---|
| identidade e versão do produto | Product/ProductVersion |
| mapa do sistema | System Blueprint e versões dos elementos |
| delta desta entrega | ProjectScope + PlanBaseline/Change Request |
| ordem da produção | ProjectPipeline e dependências de Stage |
| trabalho autorizado | Planning Item + ProjectTask + Assignment |
| tentativa real | TaskExecution |
| saída e evidência | ArtifactVersion + evidence refs/hashes |
| regras aplicáveis | PolicyDefinition/Binding/Evaluation |
| decisão | ApprovalDecision/Review |
| conteúdo entregue | Release manifest |
| resultado operacional | Delivery/Deployment + checks |
| histórico | AuditEvent append-only |

ForgeFlow, GitHub, CLIs e memória semântica são integrações ou projeções. Nenhuma delas pode substituir os registros acima no modo gerenciado.

## 5. Work Package imutável

Toda execução começa com um pacote versionado. Campos mínimos:

```yaml
contract_version: forge-engineering-work-package/v1
work_package_id: <uuid>
issued_at: <timestamp>
expires_at: <timestamp>
revision: <integer>
idempotency_key: <string>

product: {id, name}
product_version: {id, version}
project: {id, name, working_directory_path}
baseline: {id, revision, content_hash}
pipeline: {id, stage_id, stage_name}

scope_items:
  - {id, system_element_id, stable_key, change_type, expected_state}
source:
  planning_item_id: <uuid|null>
  change_request_id: <uuid|null>
task:
  id: <uuid>
  title: <string>
  description: <string>
  acceptance_criteria: []
  definition_of_done: []
  dependencies: []

assignment:
  id: <uuid>
  membership_id: <uuid>
  responsible_identity: {agent_id, sub_agent_id}
runtime:
  type: codex | claude | agy
  profile_id: <uuid>
  routing_group: <string>

context:
  artifact_versions: [{id, hash, uri}]
  decisions: [{id, revision}]
  policies: [{id, version, evaluation_input_hash}]
constraints:
  allowed_paths: []
  denied_paths: []
  allowed_tools: []
  max_cost: <number|null>
  timeout_seconds: <integer>
verification:
  commands: []
  expected_outputs: []
  evidence_destination: <uri>
return_contract: forge-engineering-result/v1
```

O pacote é snapshot. Se baseline, Task, Policy ou ArtifactVersion mudar, a execução antiga é cancelada/rejeitada e uma nova revisão é emitida. A LLM não combina automaticamente contexto de revisões diferentes.

## 6. Preflight obrigatório

Antes do dispatch, o backend calcula e persiste o resultado de preflight:

1. IDs existem e pertencem ao mesmo Product/Version/Project.
2. baseline e stage estão vigentes.
3. scope items pertencem à baseline ou Change Request aprovada.
4. dependências estão satisfeitas.
5. Task está em estado elegível.
6. Assignment usa membership ativa e skills aprovadas.
7. runtime, paths, ferramentas, custo e concorrência estão autorizados.
8. inputs existem e seus hashes correspondem.
9. não há lock ou conflito de escrita.
10. Policies foram avaliadas e approvals prévios existem.
11. critérios, outputs e verificações não estão vazios quando obrigatórios.
12. idempotency key ainda não produziu outra execução válida.

Falha de preflight não é entregue à LLM para “resolver criativamente”. Produz bloqueio estruturado com código, entidade responsável e ação de desbloqueio.

## 7. Algoritmo do loop

```text
1. LOAD
   Ler somente snapshot autoritativo e revisões declaradas.

2. VALIDATE
   Executar preflight e conferir integridade do Work Package.

3. SELECT
   Motor calcula Tasks planejadas elegíveis e ações já liberadas; Policy/ranking escolhe ou pede decisão humana.

4. AUTHORIZE
   Liberar ExecutionWave quando necessário; depois criar Assignment/lease e, quando exigido, Approval.

5. EXECUTE
   Runtime altera somente paths permitidos e emite heartbeat/eventos.

6. VERIFY
   Executar comandos, validar outputs e registrar evidências com hash.

7. REVIEW
   Revisor independente compara resultado, critérios, diff, testes e Policies.

8. DECIDE
   approved | changes_requested | rejected | blocked | failed.

9. RECORD
   Persistir resultado, custos, evidências, decisões e AuditEvents.

10. ADVANCE
    Recalcular cobertura, readiness do Stage e próximas ações elegíveis.
```

O passo 10 nunca é “perguntar à LLM o que fazer agora” sem opções governadas. O motor oferece uma lista calculada; a LLM pode recomendar uma opção e justificar, mas a autorização segue Policy.

Entre os passos, o runtime persiste `ProgressCheckpoint` append-only. Cada checkpoint informa o último passo confirmado, evidências aceitas, passo seguinte e instrução segura de retomada. Interrupção sem checkpoint não autoriza presumir conclusão; o sistema volta ao último ponto confirmado e reconcilia efeitos externos antes de repetir uma ação.

## 8. Estados e transições

O alvo deve usar máquinas distintas:

```text
ProjectTask:
planned -> ready -> assigned -> in_progress -> in_review -> done -> deployed
                    |              |
                    +-> blocked    +-> changes_requested -> ready/in_progress
                    +-> cancelled

TaskExecution:
pending -> running -> completed -> verified
             |           |
             +-> failed  +-> rejected/changes_requested -> nova execução
             +-> blocked

PipelineStage:
pending -> ready -> in_progress -> in_review -> completed
             |          |            |
             +-> blocked+------------+-> rejected/rework -> in_progress
             +----------------------------> skipped/cancelled quando template/Policy permitir
```

Transições são comandos de domínio com precondições. PATCH genérico de `status` não deve ser o mecanismo final.

`PipelineStage.completed` exige `StageCompletionAssessment` vigente com todos os requisitos obrigatórios satisfeitos. O assessment registra revisão/hash de inputs, evidências, requisitos faltantes e motivos de bloqueio; assim, “concluído” é resultado calculado e auditável, não marcação manual.

`verifying` e `awaiting_approval` são condições calculadas dentro de `in_review`, não estados adicionais. Falha/retry pertence à TaskExecution; review com `changes_requested` devolve a Task para trabalho sem apagar a tentativa anterior.

### Execution Release

Antes de `planned -> ready`, validar:

1. Task pertence à baseline vigente ou Change Request aprovada;
2. scope items e Stage estão definidos;
3. descrição, critérios de aceite, DoD, risco e prioridade estão completos;
4. dependências não possuem ciclos e permitem a liberação;
5. skills, papel executor/reviewer e runtime permitido estão definidos;
6. paths, artifacts de entrada, outputs e comandos de verificação estão definidos;
7. WIP, capacidade, orçamento e Policies permitem a onda;
8. não existe conflito de lock/ownership conhecido.

`ExecutionWave` registra `project_id`, `baseline_id`, `stage_id`, tasks, autorização/delegação, limits, status e timestamps. Estados: `draft -> approved -> active -> completed`, com `paused|cancelled`. Pausar bloqueia novos dispatches; não apaga execuções em andamento.

## 9. Producer–reviewer loop

Para cada tipo de trabalho, uma `LoopPolicy` define:

- produtor e reviewer elegíveis e distintos;
- profiles/runtimes permitidos;
- critérios e score mínimo;
- artefatos e verificações obrigatórias;
- número máximo de iterações;
- orçamento acumulado;
- condições de aprovação humana;
- comportamento em timeout/falha.

```text
producer execution
  -> deterministic verification
  -> independent review
      -> approved: registrar e recalcular readiness
      -> changes_requested: nova execução com feedback estruturado
      -> rejected/limit reached: escalar ao humano
```

O feedback de review vira input explícito da nova execução. Não se reabre a mesma tentativa nem se apaga evidência anterior.

## 10. Condições obrigatórias de parada

O agente deve parar e retornar `blocked` quando houver:

- requisito ambíguo que altere comportamento ou escopo;
- conflito entre documentos/revisões;
- referência ausente ou hash divergente;
- ação fora dos paths/ferramentas autorizados;
- necessidade de segredo não fornecido por mecanismo seguro;
- mudança de arquitetura, risco ou Policy não prevista;
- dependência incompleta;
- teste obrigatório impossível de executar;
- custo/tempo/iterações esgotados;
- tentativa de autoaprovação proibida;
- estado externo que não possa ser confirmado.

O bloqueio contém `code`, `message`, `affected_ids`, `evidence`, `safe_actions` e `required_authority`.

## 11. Ajuste humano do processo

O operador pode ajustar o processo a qualquer momento, mas nunca reescrever história:

| Momento | Mecanismo |
|---|---|
| concepção draft | nova ConceptRevision |
| antes da baseline | editar plano/escopo draft e recalcular impactos |
| após baseline | Change Request + nova revisão/baseline |
| execução ativa | pause/cancel; preservar tentativa; emitir novo Work Package |
| stage ativo | replan governado, sem apagar execuções |
| release candidate | retirar candidato ou criar nova revisão |
| após deploy | rollback/roll-forward + incidente/manutenção |
| mudança do processo padrão | nova versão de template/Policy; instâncias antigas permanecem reproduzíveis |

Overrides exigem autoridade, justificativa, duração/escopo e AuditEvent. Policy obrigatória não pode ser removida silenciosamente.

## 12. Cockpit diário

O ForgeHub deve fornecer uma visão diária calculada, não redigida apenas pela LLM:

```text
Product / Version / Project
Macrofluxo e Stage atual
Baseline e revisões vigentes
System Scope: total, coberto, lacunas e mudanças
Tasks: ready, ativas, review, bloqueadas e atrasadas
Executions: runtime, lease, heartbeat, custo e resultado
Último checkpoint confirmado, ponto de parada e instrução de retomada
Gates: satisfeitos, pendentes e motivos
Riscos, Policies e approvals aguardando decisão
Release/ambiente e saúde operacional
Decisões tomadas desde a última revisão
Próximas ações elegíveis e quem pode autorizá-las
```

Ritual recomendado:

1. conferir divergências e execuções sem heartbeat;
2. revisar bloqueios, riscos e mudanças de escopo;
3. decidir approvals/Change Requests;
4. confirmar prioridades entre ações elegíveis;
5. autorizar dispatches dentro de orçamento/capacidade;
6. registrar decisão diária e snapshot;
7. ao final, comparar previsto versus realizado e preparar handoff.

A LLM pode gerar o resumo narrativo, mas números, estados e readiness vêm de consultas persistidas.

## 13. Continuidade entre LLMs e sessões

Uma nova sessão recebe:

- snapshot do Cockpit;
- Work Package ou decisão pendente;
- revisões exatas dos artifacts;
- últimos eventos e handoff estruturado;
- limitações e ações elegíveis.

Não recebe como obrigação todo o histórico conversacional. Memória semântica serve para recuperação auxiliar; decisões efetivas precisam de IDs e revisões no ForgeHub.

Cada handoff registra:

```yaml
from_execution_id: <uuid>
to_role: <role>
completed: []
pending: []
blocked: []
decisions: []
artifacts: [{id, version, hash}]
next_eligible_actions: []
risks: []
```

## 14. Concorrência, idempotência e recuperação

- Dispatch cria lease com prazo, heartbeat e owner.
- Uma Task não possui duas assignments executoras ativas salvo estratégia explícita.
- Escrita concorrente exige locks por SystemElement/path ou merge strategy declarada.
- Todo comando externo usa idempotency key.
- Eventos de runtime entram por outbox/inbox e podem ser repetidos sem duplicar transições.
- Reinício do runner recupera execuções persistidas; estado somente em memória é insuficiente.
- Lease vencido não marca falha automaticamente sem reconciliação do processo externo.
- Resultados tardios são preservados, mas rejeitados como stale quando a revisão não é vigente.

## 15. Divisão entre ForgeHub e ForgeFlow

No modo gerenciado:

- ForgeHub possui Tasks, estado, autorização, review, gates e auditoria;
- ForgeFlow prepara o workspace, executa CLIs, mantém checkpoint/outbox local e coleta evidências;
- `.state` é cache operacional, não ledger empresarial autoritativo;
- ForgeFlow não aprova gate nem conclui Project/Stage/Release.

No modo standalone, ForgeFlow pode usar ledger local, mas o modo deve ser explícito e não pode sincronizar retroativamente decisões como se tivessem sido aprovadas pelo ForgeHub.

## 15.1 Contrato dos adapters CLI

- O backend persiste WorkPackage; o host runner entrega arquivo/stdin ao adapter.
- Cada adapter possui executable e argumentos fixos/configurados pelo código, nunca um comando shell livre vindo da Task.
- O working directory vem do Project e precisa passar por allowlist/canonicalização.
- Prompt/instruction é derivado do WorkPackage e usa template versionado.
- CLI emite stdout/stderr para log limitado e retorna `forge-engineering-result/v1` por arquivo/canal conhecido.
- Timeout envia cancelamento gracioso e depois encerra o processo; resultado parcial permanece evidência.
- PID/session/heartbeat/exit code ficam persistidos para recovery.
- Secrets entram por ambiente seguro do adapter e nunca no WorkPackage/artifact/log.
- Capabilities diferentes entre CLIs são declaradas; ausência de capability torna o runtime inelegível, não improvisado.

## 16. Critérios de aceite do loop

O loop estará pronto quando testes demonstrarem:

1. retomada por outra LLM sem conversa anterior;
2. bloqueio por contexto obrigatório ausente;
3. nenhuma transição inválida via API;
4. dispatch/retry idempotentes;
5. recovery após reinício do runner;
6. producer e reviewer independentes;
7. limite de iterações/custo aplicado;
8. mudança pós-baseline obrigando Change Request;
9. cobertura recalculada por evidência real;
10. Stage bloqueado com motivo determinístico;
11. Release manifest reproduzível;
12. Deployment verificado ou revertido com evidência;
13. ajuste humano preservando histórico;
14. Cockpit reconstruído apenas do banco/eventos;
15. mesma decisão de elegibilidade com qualquer LLM, pois a decisão estrutural pertence ao motor.
