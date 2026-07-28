# ForgeHub — Protocolo de Desenvolvimento para Agentes CLI

## 1. Finalidade

Este protocolo define como Codex, Claude CLI e Agy devem receber, executar e devolver trabalho controlado pelo ForgeHub. Ele complementa `AGENTS.md` e as regras próprias de cada repositório; não substitui instruções locais. Agy usa o identificador alvo `agy`; até a migration do runtime atual, o adapter normaliza o valor legado `antigravity`.

O objetivo é impedir execução sem contexto, alteração de conteúdo aprovado, conclusão sem evidência e perda de rastreabilidade.

Este documento orienta a execução no modelo atual e durante a migração. A máquina operacional-alvo, incluindo Work Package, preflight, leases, recovery, cockpit diário e loops aninhados, está definida em `ENGINEERING_LOOP.md`. Em caso de divergência sobre o alvo, prevalecem `PLANNING_DELIVERY_ARCHITECTURE.md` e `ENGINEERING_LOOP.md`; o código continua sendo a fonte do comportamento disponível hoje.

## 2. Pacote mínimo de execução

Nenhum agente deve iniciar codificação sem um pacote contendo:

```yaml
product:
  id: <uuid>
  name: <nome>
product_version:
  id: <uuid>
  version: <semver>
project:
  id: <uuid>
  name: <nome>
  working_directory_path: <caminho absoluto>
  solution_types: []
  delivery_strategy: <tipo de entrega>
  target_platforms: []
  risk_class: <classe>
pipeline:
  id: <uuid>
  stage_id: <uuid>
  stage_name: <nome>
source:
  planning_item_id: <uuid opcional>
  change_request_id: <uuid opcional>
task:
  id: <uuid>
  title: <título>
  description: <escopo>
  acceptance_criteria: []
  definition_of_done: []
  functional_modules: []
  technical_tracks: []
assignment:
  id: <uuid>
  project_membership_id: <uuid>
  responsible_agent_id: <uuid>
  responsible_sub_agent_id: <uuid opcional>
  assignment_role: <executor|reviewer|coordinator>
runtime:
  type: <codex|claude|agy|human|system>
  profile_ref: <referência sem segredo>
  routing_group: <auto|simple|standard|complex|reasoning|vision|audio|code>
constraints:
  allowed_paths: []
  locked_paths: []
  artifact_versions_to_read: []
  policies: []
verification:
  commands: []
  evidence_destination: <URI/path/PR>
```

No modelo atual, alguns campos ainda não existem diretamente. O orquestrador deve fornecê-los no contexto da task e registrar a associação manualmente até as mudanças P0 de `PLANNING_DELIVERY_ARCHITECTURE.md` serem implementadas.

O Agent/SubAgent identifica o responsável cadastrado; `runtime.type` identifica a ferramenta efetivamente utilizada. Esses valores não são intercambiáveis.

## 2.1 Hierarquia do ecossistema

O ecossistema funciona como uma empresa. Possui oito Agents principais Tier A: Athos como único Orquestrador e sete responsáveis principais pelo desenvolvimento de sistemas (Daedalus, Atlas, Mnemosyne, Scriba, Themis, Hephaestus e Aegis). Athos interpreta o objetivo, organiza o planejamento, classifica a carga para o ForgeRouter, seleciona membros/perfis e acompanha os loops. Agents Tier B formam os grupos especialistas de AI Runtime, Architecture, Engineering, Governance, Integration Governance, Operations, Quality e Security. SubAgents são workers de escopo restrito pertencentes a um Agent e não entram na contagem dos oito principais. Delegar uma Task não transfere identidade nem credencial: cada processo usa a API key ForgeRouter do Agent responsável pela execução.

Athos também é o operador padrão do ForgeHub. Com delegação ativa, ele pode criar/revisar planejamento, montar equipe e liberar Tasks elegíveis por ExecutionWave. O usuário conserva autoridade final, e Athos deve escalar toda decisão fora do mandato ou reservada por Policy.

## 3. Sequência obrigatória

### 3.1 Antes da mudança

1. Ler `AGENTS.md` e instruções locais.
2. Confirmar o working directory.
3. Ler a Task, seu Planning Item ou Change Request, stage e artefatos vigentes.
4. Verificar `is_locked` em artifacts e structure nodes envolvidos.
5. Confirmar que dependências estão concluídas.
6. Inspecionar o estado real do repositório e preservar alterações de terceiros.
7. Registrar/iniciar uma TaskExecution.
8. Confirmar que Assignment aponta para um Agent/SubAgent cadastrado, ativo e pertencente à equipe autorizada do Project.

### 3.2 Durante a mudança

1. Permanecer dentro dos caminhos e do escopo autorizados.
2. Não editar ArtifactVersion aprovada; criar nova revisão.
3. Não alterar escopo baselined sem Change Request.
4. Não alterar migrations já aplicadas; criar migration posterior.
5. Não misturar correções não relacionadas na mesma execução.
6. Registrar decisões relevantes em documentação/ADR quando exigido.
7. Executar verificações proporcionais ao risco.

### 3.3 Na entrega

O agente devolve um relatório estruturado:

```yaml
task_id: <uuid>
execution_id: <uuid>
assignment_id: <uuid>
responsible_agent_id: <uuid>
runtime_type: codex | claude | agy | human | system
runtime_session_ref: <id seguro da sessão, quando disponível>
status: completed | failed | blocked
summary: <resultado objetivo>
changed_files: []
artifacts_created_or_revised: []
verification:
  - command: <comando>
    result: passed | failed | not_run
    notes: <resumo>
evidence_ref: <commit, PR, log ou arquivo>
residual_risks: []
follow_up_items: []
```

`completed` significa que o executor terminou e anexou evidência. A validação independente muda a execução para `verified`; o executor não deve autoaprovar seu próprio trabalho quando a policy exigir separação de funções.

## 4. Divisão recomendada de trabalho

A escolha do agente deve ser configurável por capacidade e policy, não codificada como verdade permanente. Como ponto de partida:

| Trabalho | Executor preferencial | Revisão |
|---|---|---|
| Exploração do repositório e implementação incremental | Codex ou Claude CLI | outro agente ou humano |
| Especificação extensa e análise transversal | Claude CLI | owner/arquitetura |
| Testes, correções localizadas e automação repetitiva | Codex | CI + reviewer |
| Tarefa curta, isolada e com contrato rígido | Agy | Codex/Claude/humano |
| Migration ou segurança de alto risco | agente qualificado | humano obrigatório |
| Deploy em produção | sistema/operador autorizado | Approval explícita |

O nome da ferramenta não substitui competência, permissões, disponibilidade ou revisão.

## 5. Regras de segurança e governança

- Nunca inventar aprovação, evidência, resultado de teste ou estado de deploy.
- Nunca expor segredo em prompt, log, Artifact ou `evidence_ref`.
- Nunca executar ação destrutiva ou externa além da autorização da Task.
- Nunca desbloquear artifact/nó apenas para contornar uma regra; solicitar mudança governada.
- Nunca marcar stage, release ou deploy como concluído diretamente. Essas conclusões são calculadas pelo ForgeHub a partir das evidências e decisões.
- Se o código contradizer a documentação, registrar a divergência e usar o comportamento real até decisão do owner.
- Se os critérios de aceite forem ambíguos, pausar antes de uma mudança que altere escopo ou arquitetura.

## 6. Definition of Done para mudanças de código

Uma Task de código só está pronta para revisão quando:

- o comportamento solicitado foi implementado;
- arquivos fora do escopo não foram alterados;
- testes relevantes foram adicionados/atualizados e executados;
- lint/typecheck/build aplicáveis passaram ou a falha foi registrada;
- migration e rollback foram avaliados quando há mudança de dados;
- documentação e contratos foram atualizados;
- riscos e limitações residuais foram declarados;
- existe `evidence_ref` verificável;
- ArtifactVersions produzidas foram registradas;
- nenhum gate foi autoaprovado pelo executor.

## 7. Instrução padrão para despacho

O orquestrador pode usar o seguinte molde:

```text
Execute a Task <id> do Project <id>, stage <id>, no diretório <path>.
Leia AGENTS.md e as ArtifactVersions <ids> antes de modificar arquivos.
Escopo autorizado: <descrição e paths>.
Não altere: <locks/paths>.
Critérios de aceite: <lista>.
Verificações obrigatórias: <comandos>.
Ao final, não faça deploy nem aprove gates. Retorne o relatório estruturado
do Protocolo de Desenvolvimento para que a execução seja revisada e registrada.
```

## 8. Tratamento de falhas e reexecução

- Falha técnica termina a tentativa atual como `failed`, com logs/evidência.
- Uma correção cria nova TaskExecution com novo `attempt_number`; não apaga a anterior.
- Bloqueio externo mantém a Task `blocked` e descreve condição de desbloqueio.
- Mudança de escopo abre Change Request ou novo Planning Item; não amplia silenciosamente a Task.
- Rejeição em review gera `changes_requested` e outra execução; preserva o histórico.

## 9. Compatibilidade com o estado atual

O backend já implementa ProjectMembership, perfis ForgeRouter, classes semânticas de roteamento, policies de loop, dispatch e reviews. Permanecem transitoriamente:

- stage e módulo devem ser repetidos na descrição da Task;
- a ligação Artifact → Project/versão deve ser resolvida pelo stage/execution e conferida manualmente;
- Approval e gate precisam ser atualizados de forma coordenada;
- conclusão de Task precisa de revisão manual porque a API atual não garante execução verificada/subtasks completas;
- o cleanup do Kanboard não deve ser usado até a correção da consulta a `ProjectTask.project_id`.
- o CRUD manual legado ainda aceita Assignment/TaskExecution sem membership; o runner automatizado não aceita;
- TaskExecution criada fora do runner deve sempre informar `assignment_id`, mesmo que a coluna permaneça nullable para dados antigos;
- o relatório deve registrar separadamente Agent/SubAgent responsável e CLI utilizada.

Essas são medidas transitórias, não o desenho final.
