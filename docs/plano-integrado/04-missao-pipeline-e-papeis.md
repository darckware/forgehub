# Missão: pipeline, papéis, contexto e validação

## O essencial da Missão: começar, validar, concluir

Marcelo, 24/10: "O importante na Missão é saber quando começar, validar o que foi entregue e marcar
como concluída a missão." E: "na Missão preciso adicionar as críticas, caso a entrega não condiga com
as expectativas, sugerindo as devidas correções", e o documento para "validar o projeto na
finalização da missão". Tudo o mais neste documento serve a estas regras.

### Estados

`rascunho` → `pronta` → `ativa` → `em verificação` → `aguardando aceite` → `concluída`
(ou `cancelada` com motivo, de qualquer estado; uma crítica ou `reaberta` volta para `ativa`)

### 1. Quando começar (definição de "pronta")

A missão só passa de `rascunho` para `pronta` quando **todos** os itens abaixo estão cumpridos. O
sistema verifica e mostra o que falta:

| # | Condição | Como se verifica |
|---|---|---|
| 1 | Brief aprovado (objetivo, escopo e fora de escopo, restrições, riscos) | Artefato `BRIEF.md` em `approved`, aprovado pelo Marcelo |
| 2 | Critérios de aceite **verificáveis**: cada um diz o que prova, como se prova e quem verifica | Nenhum critério sem método de verificação e sem verificador |
| 3 | Papéis nomeados e checados (orquestrador, executores, verificadores, documentador) | Regras da seção "Papéis" sem violação |
| 4 | Plano validado: todo critério coberto por tarefa, dependências sem ciclo, prazo cabe, documento com dono, entrega com verificador | Checagem automática verde |
| 5 | Pré-requisitos de execução prontos: acessos, delegações, ambiente de homologação, máquinas autorizadas (manutenção) | Lista de pré-requisitos do plano toda marcada |
| 6 | Prazo e orçamento definidos | Campos preenchidos |

**A largada** é a aprovação da baseline do plano pelo Marcelo (ou por delegação explícita). Ela leva
a missão a `ativa` e despacha automaticamente as tarefas sem dependência. Antes disso, nenhuma tarefa
da missão é despachada.

### 2. Como validar o que foi entregue

A validação acontece em dois níveis, e nenhum deles é feito por quem executou.

**Por tarefa (entrega):**
1. O executor termina com `STATUS: DONE` e evidência.
2. A evidência é verificada automaticamente: commit e CI, execução remota com todas as máquinas `ok`,
   arquivo, registro no banco.
3. Um verificador independente confere, conforme o tipo: revisão de código, estado da máquina depois
   do serviço, documento revisado.
4. O documento do estágio está registrado.

Faltou qualquer passo? A tarefa volta ao executor com o motivo. Não há "quase pronto".

**Por critério de aceite:**
- o verificador do critério marca `comprovado` citando a evidência, depois que todas as tarefas
  ligadas a ele estão validadas;
- ou marca `reprovado` com motivo, e o orquestrador replaneja (nova tarefa, ou change request se o
  escopo muda).

Quando todos os critérios estão `comprovados`, a missão passa a `em verificação` final.

### 3. Quando marcar como concluída

A missão só fica `concluída` quando:

| # | Condição |
|---|---|
| 1 | Todos os critérios de aceite estão `comprovados`, cada um com a evidência citada |
| 2 | Todos os documentos obrigatórios estão aprovados |
| 3 | Nenhuma tarefa aberta (canceladas só com justificativa aprovada) |
| 4 | Consolidação feita pelo orquestrador: resultado e documento final, revisados pelo documentador |
| 5 | Aceite do cliente no portal, quando a missão é de cliente |
| 6 | Nenhuma crítica aberta que bloqueie o aceite (seção 4) |
| 7 | **Dossiê de validação** gerado e completo (seção 5) |
| 8 | **Aceite do Marcelo** (ou de quem ele delegou para aquela missão), dado sobre o dossiê |

**Quem marca:** só o Marcelo, ou um delegado nomeado na abertura. O sistema recusa o aceite enquanto
qualquer item acima estiver pendente, e mostra qual.

**Ao concluir, automaticamente:**
- a autoridade do orquestrador sobre o projeto é revogada;
- o canal da missão é arquivado;
- as lições são registradas (o que funcionou, o que falhou);
- as métricas vão para a Evolução;
- o brief e os documentos ficam somente leitura.

Reabrir exige motivo e volta a missão a `ativa`, com histórico.

### 4. Críticas: quando a entrega não atende ao esperado

Uma crítica registra que **o que foi entregue não corresponde ao esperado** e diz **como corrigir**.
Ela é o caminho formal de "não aceito, e por quê", e nunca se perde: fica no dossiê da missão.

**Quem pode criticar:**
- o Marcelo, em qualquer momento;
- os verificadores, ao conferir uma entrega ou um critério;
- os revisores, ao revisar um documento;
- o cliente, pelo "pedir ajuste" do portal (E.3), que entra como crítica de origem cliente.

O executor nunca critica a própria entrega para encerrá-la.

**O que toda crítica contém** (modelo em [modelos/CRITICA-DE-ENTREGA.md](modelos/CRITICA-DE-ENTREGA.md)):

| Campo | Conteúdo |
|---|---|
| Sobre o quê | Tarefa, entrega, documento ou critério de aceite criticado |
| Esperado | O que deveria ter sido entregue, citando o critério de aceite, o brief, o contrato do projeto ou a anotação que define a expectativa |
| Entregue | O que de fato veio, com a evidência (commit, tela, arquivo, execução) |
| Diferença | O que falta, o que está errado ou o que contraria o esperado |
| Severidade | **bloqueia o aceite** (a missão não conclui com ela aberta) · **corrigir antes de concluir** · **melhoria futura** (vira item de uma próxima missão, não bloqueia) |
| Correção sugerida | O que fazer para atender, de forma que um agente execute sem adivinhar |
| Responsável sugerido | Normalmente o executor original; outro agente quando a causa é de outra área |
| Como verificar a correção | O teste ou a evidência que vai provar que foi corrigido |

**O que acontece quando a crítica é registrada:**
1. O critério de aceite ligado volta de `comprovado` para `reprovado`, e a missão volta para `ativa`
   se já estava em verificação.
2. O orquestrador transforma a correção sugerida em **tarefa de correção**, ligada à crítica, à tarefa
   original e ao critério. Ela é despachada com a crítica no contexto.
3. A correção passa pelo mesmo caminho de qualquer entrega: `STATUS: DONE`, evidência e verificador
   independente.
4. **Quem criticou fecha a crítica** (ou o Marcelo): aceita a correção ou a reabre com novo comentário.
   O executor não fecha crítica.
5. Se a crítica pede algo **fora do escopo** combinado, ela vira **change request** (mudança de
   escopo, com aprovação), e não tarefa de correção.

**Estados da crítica:** `aberta` → `em correção` → `correção entregue` → `aceita` (fechada) ou
`reaberta`; também `convertida em mudança de escopo` ou `adiada para próxima missão` (só para melhoria futura).

**Aprendizado:** críticas repetidas do mesmo tipo (mesmo agente, mesma área, mesma causa) viram lição
(G.7) e proposta de melhoria de skill, carta ou rotina.

### 5. Dossiê de validação: o documento para validar o projeto na finalização

Quando todos os critérios estão comprovados, a missão passa a `aguardando aceite` e o sistema gera o
**dossiê de validação** (`docs/missions/<slug>/DOSSIE-DE-VALIDACAO.md`, registrado como Artefato).
É sobre ele que o Marcelo valida e dá o aceite. Modelo em
[modelos/DOSSIE-DE-VALIDACAO.md](modelos/DOSSIE-DE-VALIDACAO.md).

O dossiê reúne, num lugar só:
1. **Identificação:** missão, objetivo, período, orquestrador, papéis, linha de serviço, cliente (se houver).
2. **Critérios de aceite × evidência:** cada critério, as tarefas que o cumpriram, a evidência que o
   prova, quem verificou e quando.
3. **Entregas:** tarefas concluídas, com executor, verificador e evidência.
4. **Documentos:** cada documento obrigatório, a versão aprovada e quem aprovou.
5. **Críticas e correções:** todas, abertas e fechadas, com o esperado, o entregue, a correção e o
   resultado. Nenhuma crítica que bloqueie pode estar aberta.
6. **Mudanças de escopo:** change requests aprovados e o que mudaram.
7. **Prazo e custo:** previsto × realizado.
8. **Riscos e pendências remanescentes:** o que fica para depois, com dono e destino (outra missão,
   sustentação).
9. **Lições:** o que funcionou e o que não funcionou.
10. **Checklist de aceite:** os itens da seção 3, marcados, e o espaço para o aceite (ou a crítica) do
    Marcelo.

Se o Marcelo não aceitar, ele registra **críticas** no próprio dossiê, a missão volta para `ativa` e um
novo dossiê é gerado na próxima vez que chegar a `aguardando aceite`. As versões anteriores ficam
guardadas.

## Missão = projeto no Service Factory: o que os agentes conseguem hoje

Para um grupo de agentes executar uma missão, ela precisa existir como projeto no Service Factory.
O projeto é onde eles gerenciam as atividades, a documentação e a distribuição das tarefas. Análise
das ferramentas MCP de 24/10:

| O grupo precisa | Hoje pelo MCP | Lacuna |
|---|---|---|
| Registrar a missão como projeto | Só pelo caminho de software novo: `create_conception_idea` (cria produto, conceito, blueprint) → aprovação do conceito → `authorize_project_delivery`. Pesado e errado para uma missão interna | **Criar projeto interno** sob um produto/versão existente, na linha "Missões", com objetivo e critério de sucesso |
| Ter onde registrar (produto e ciclo) | Não há produto real cadastrado, só dados de teste | Produto "Ecossistema Foundation" com versão `2026.4` (B.1) |
| Definir participantes e papéis | `ProjectAgentMembership` existe (13 registros), mas no módulo de Orquestração e sem ferramenta MCP | Ferramenta para gerenciar membros. **Atenção:** a R.1 aposenta a Orquestração e precisa preservar o `ProjectAgentMembership` |
| Quebrar em fases e tarefas | `create_planning_item`, `create_project_task` | — |
| Ordenar as tarefas | Não há ferramenta de dependência | `add_task_dependency` |
| Distribuir as tarefas | `release_planning_for_execution` só grava o agente no item; não cria a atribuição da tarefa nem despacha | `assign_task` e `dispatch_task` (a rota já existe) |
| Acompanhar | `list_project_tasks`, `update_task_status` | Linha do tempo (P.5) |
| Provar a entrega | Só pela resposta do Messages | `report_task_execution` com evidência |
| Documentar o projeto | `save_concept_document` (só no conceito) | Documento ligado ao projeto/fase/tarefa (`DocLink` + artefato) e a pasta `docs/missions/<slug>/` |
| Receber o seu contexto | — | Anotações (P.2) e contexto herdado no despacho (P.4) |

## Fase M0 — Caminho rápido: a primeira missão como projeto (logo após a V-a)

Antes do módulo completo de Missão (M.1), o grupo já pode trabalhar numa missão registrada como
projeto, por convenção. A camada de Missão vem depois e se apoia nesses mesmos projetos.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| M0.1 | Produto "Ecossistema Foundation" (interno, sem cliente) com versão `2026.4` | Claude Code (via API), Marcelo confirma | V-a | Aparece no Cockpit |
| M0.2 | Ferramentas MCP mínimas para o grupo: `create_internal_project` (produto/versão, linha, objetivo, critérios de aceite, orquestrador, pasta), `manage_project_members` (com função), `submit_project_plan` (Plano do projeto para aprovação), `add_task_dependency`, `assign_task`, `dispatch_task`, `report_task_execution` (evidência), `attach_project_document` (`DocLink`) | Aramis, Porthus revisa | V-a | Um agente cria e conduz um projeto de missão inteiro pelo MCP |
| M0.3 | **Convenção de missão** até a M.1: projeto do tipo missão; o primeiro planning item é "Objetivo e critérios de aceite" (um critério por linha, cada um com a tarefa e a evidência que o comprovam); fases = planning items; orquestrador = Athos (`coordinator`); executores, verificadores, planejador e documentador como membros do projeto com a função; `BRIEF.md` e documentos em `docs/missions/<slug>/` com `00-INDICE.md`; plano no Plano do projeto, aprovado pelo Marcelo antes de despachar; toda tarefa termina com `STATUS: DONE` e evidência | Athos (Foundation) + Scriba | M0.2 | Convenção publicada na skill `forgehub` e na Foundation |
| M0.4 | **Skill "como conduzir uma missão"** na skill compartilhada `forgehub`: registrar, planejar, distribuir, acompanhar, documentar, consolidar | Athos + Claude Code | M0.3 | Os agentes seguem o mesmo roteiro |
| M0.5 | **Primeira missão real:** o próprio plano integrado, registrado como projeto de missão (fases do plano = planning items, tarefas = tarefas), com o Athos coordenando e você acompanhando e anotando | Athos | M0.4 | O avanço do plano é visto no Cockpit, não em documento solto |

A M.1 (módulo completo) passa a acrescentar o que a convenção não cobre: campos próprios de missão,
consolidação automática, contexto por destinatário (M.2) e a tela `/missions`.

## Pipeline de ponta a ponta: Missão → Service Factory → Operação 24x7 → Atividades dos Agentes

**A Missão é a garantia de que o serviço foi concluído.** Ela define o que é "concluído", controla e
monitora a execução, e só se encerra quando cada critério está comprovado. Os outros três componentes
executam e observam. Ninguém além da Missão declara um serviço terminado.

```
 MISSÃO (garantia)          SERVICE FACTORY (gestão)       OPERAÇÃO 24x7 (vigilância)    ATIVIDADES DOS AGENTES (visão)
 ─────────────────          ────────────────────────       ──────────────────────────    ──────────────────────────────
 1 Abertura ───────────────► 2 Planejamento
   objetivo, critérios        projetos por linha,
   de aceite, prazo,          fases, tarefas,
   coordenador                dependências, docs,
        ▲                     agentes
        │                          │
        │                          ▼
        │                     3 Execução ─────────────────► vigia prazos, falhas,  ──► tempo real de cada agente,
        │                       despacho pelo Messages,       bloqueios; cobra,          rotina e execução, com a
        │                       STATUS + evidência            escala, pergunta           origem (missão/projeto/tarefa)
        │                          │                               │                          │
        │                          ▼                               ▼                          ▼
 5 Verificação ◄──────────── 4 Entrega por tarefa ◄────── sinais de saúde ◄─────────── eventos e indicadores
   cada critério × evidência   evidência verificada,
   documentação aprovada       documento registrado
        │
        ▼
 6 Aceite e encerramento ──► lições (G.7) e melhoria
   cliente (portal) e Marcelo
```

**Estágios, responsáveis e gates**

| # | Estágio | Componente | Entra | Sai | Gate para avançar |
|---|---|---|---|---|---|
| 1 | **Abertura** | Missão | Pedido do Marcelo, ticket/proposta do cliente, proposta da retrospectiva | Objetivo, **critérios de aceite** (cada um verificável), prazo, coordenador, linhas de serviço, orçamento | Marcelo aprova (ou delegação) |
| 2 | **Planejamento** | Service Factory | Missão aprovada | Projeto(s) por linha com pipeline da linha, fases, tarefas, dependências, documentos obrigatórios, agentes; **cada critério de aceite ligado às tarefas que o cumprem** | Coordenador confirma que todo critério tem tarefa; Marcelo aprova o plano (até o nível M1) |
| 3 | **Execução** | Service Factory + Messages | Tarefa pronta (dependências concluídas) | Despacho com contexto (contrato, anotações, missão); resultado com `STATUS` e evidência | `STATUS: DONE` |
| 4 | **Entrega por tarefa** | Service Factory | Resultado da execução | Evidência verificada (`git:`/CI, `host_execution`, `file:`, `db:`), documento registrado; `PARTIAL`/`BLOCKED` voltam à execução com motivo | Evidência verificada + documento do estágio |
| — | **Vigilância contínua** (estágios 3 e 4) | Operação 24x7 | Sinais de todas as tarefas da missão | Cobrança ao agente, reatribuição, pergunta ao Marcelo, escalada ao coordenador | — |
| — | **Visibilidade contínua** | Atividades dos Agentes | Eventos de execução, rotinas, telemetria | Quem está fazendo o quê, para qual missão, e há quanto tempo | — |
| 5 | **Verificação** | Missão | Tarefas entregues | Cada critério de aceite marcado como cumprido, com a evidência que prova; verificador independente (G.5) quando o tipo exige | **Todos** os critérios comprovados; nenhum documento obrigatório pendente |
| 6 | **Aceite e encerramento** | Missão | Verificação completa | Resultado consolidado, documento final, aceite do cliente no portal (se houver) e do Marcelo; lições registradas | Aceite explícito; sem aceite, a missão volta ao estágio que falhou |

**Como a Missão monitora (o "controle da execução")**

A missão calcula continuamente a própria **saúde** a partir das tarefas dos seus projetos, e a mostra
como um semáforo:

| Sinal | Fonte | Vira alerta quando |
|---|---|---|
| Avanço por critério de aceite | tarefas ligadas a cada critério | um critério não tem tarefa, ou nenhuma tarefa dele avançou em N dias |
| Prazo | datas das tarefas × prazo da missão | caminho crítico passa do prazo |
| Bloqueios e falhas | `blocked`, `PARTIAL`, `BLOCKED`, falha no Messages | qualquer bloqueio > 24 h, ou 2 falhas na mesma tarefa |
| Evidência pendente | tarefas `reported` sem verificação | entrega sem prova > 24 h |
| Documentação | documentos obrigatórios do pipeline | estágio concluído sem documento |
| Rotinas e agentes | Operação 24x7 e Atividades dos Agentes | agente da missão degradado, rotina de vigilância perdida |
| Custo | ForgeRouter e horas (Q.7) | consumo acima do orçamento |
| Cliente | portal Darckware (E.2/E.3) | ajuste pedido ou aceite pendente |

Cada alerta vai para quem age:
- ao **coordenador**, como tarefa de triagem;
- ao **Marcelo**, pela fila de decisões (G.11), só quando a decisão é dele;
- ao **agente responsável**, como cobrança pela Operação 24x7.

A saúde da missão aparece no Cockpit, no briefing do Athos e no painel da própria missão.

**Regras do pipeline**
1. Só a Missão declara um serviço concluído. Tarefa `done` e fase concluída são etapas, não o fim.
2. Todo critério de aceite precisa de evidência verificável. Critério sem prova não fecha.
3. Todo trabalho de missão passa pelo Service Factory. Execução fora dele não conta para a missão.
4. A Operação 24x7 nunca encerra nada: ela cobra, reatribui e escala.
5. As Atividades dos Agentes nunca decidem nada: elas mostram, com a origem de cada execução.
6. Falha em qualquer estágio volta ao estágio anterior, com motivo registrado. Nada é apagado.

## Papéis, contexto e validação na missão

### Papéis (nomeados na abertura da missão)

Reaproveitam o vocabulário único de funções que já existe (`PROJECT_AGENT_ROLES`, usado por membros
de projeto, agentes e canais). Nada de lista nova.

| Papel na missão | Função existente | Quantos | Quem (padrão) | Faz | Nunca faz |
|---|---|---|---|---|---|
| **Patrocinador / aprovador** | — (pessoa) | 1 | Marcelo | Aprova abertura, plano, documentos-chave e aceite final; anota | — |
| **Orquestrador** | `coordinator` | exatamente 1 | Athos | Planeja com o planejador, distribui, acompanha a saúde, resolve bloqueios, consolida | Executar código (é agente Hermes); verificar a própria consolidação |
| **Planejador** | `planner` | 0–1 | Atlas | Monta o plano (fases, tarefas, dependências, critérios × tarefas) | Aprovar o próprio plano |
| **Executores** | `developer`, `designer`, `data_engineer`, `architect`, `release_manager`, `compliance`, `knowledge_management` | 1 ou mais | Por linha e carta: código só Aramis, Porthus, Dartan | Executam as tarefas e entregam evidência | Verificar a própria entrega |
| **Verificadores** | `reviewer`, `qa`, `security_reviewer` | 1 ou mais | Porthus (código), Aegis (segurança), outro agente da área | Comprovam entregas e critérios de aceite | Verificar o que eles mesmos executaram |
| **Documentador** | `documentation` | 1 | Scriba | Mantém o brief, os documentos obrigatórios e o resultado final | Aprovar o próprio documento |

**Regras checadas automaticamente ao nomear:**
- exatamente um orquestrador;
- código só com executor de runtime externo;
- verificador nunca é o executor da mesma tarefa;
- o papel respeita o "nunca faz" da carta do agente;
- o agente está ativo e com canal saudável;
- há limite de missões simultâneas por orquestrador e de carga por executor.

### Contexto da missão (o "brief")

Um documento único, versionado, `docs/missions/<slug>/BRIEF.md`, registrado como Artefato. Contém:
- objetivo;
- histórico e motivação;
- escopo e fora de escopo;
- critérios de aceite;
- restrições;
- decisões já tomadas;
- referências: contrato do projeto (D.8), documentos do produto, Foundation, Base de Conhecimento;
- riscos;
- glossário;
- papéis.

O brief é a base do contexto enviado em cada despacho, junto com as anotações do Marcelo (P.4) e os
itens de contexto filtrados por destinatário (M.2). Mudou o brief? Sai uma nova versão, os membros são
avisados e as próximas tarefas já recebem a versão nova.

### Validação do plano

O plano da missão usa o **Plano do projeto que já existe** (`ProjectPlan`: rascunho → aprovado →
baseline → substituído) e o **change request** para mudanças depois da baseline.

1. **Checagem automática**, antes de pedir aprovação:
   - todo critério de aceite tem tarefa;
   - toda tarefa tem papel e agente compatíveis;
   - as dependências não formam ciclo;
   - o caminho crítico cabe no prazo;
   - todo documento obrigatório tem dono;
   - toda entrega tem verificador;
   - o orçamento cabe;
   - os riscos estão listados.
2. **Revisão:** o orquestrador revisa o que o planejador montou.
3. **Aprovação:** o Marcelo aprova, e o plano vira baseline. **A aprovação do plano autoriza a execução
   das tarefas daquela baseline.** Não é preciso aprovar tarefa por tarefa, o que concilia com a regra
   dos canais "a execução real fica com o Marcelo" (`CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md` §3.3).
4. **Depois da baseline:** só por change request aprovado. Mudança de prazo, escopo ou critério reabre a validação.

### Validação da documentação

- **Ciclo por documento:** autor → revisão por outro agente → aprovação. Os estados seguem o padrão 18
  da Foundation (rascunho, em revisão, aprovado), mapeados nos estados do Artefato
  (`draft`, `submitted`, `approved`) e das versões (`draft`, `final`, `superseded`).
- **Documentos-chave aprovados pelo Marcelo:** brief, escopo/PRD, plano, resultado final. Os demais são
  aprovados pelo verificador ou pelo documentador.
- **Checagem automática:** cabeçalho com estado/dono/data, links válidos, nenhum segredo, nenhum nome
  ou id interno em documento visível ao cliente.
- **Regra:** a missão só passa da verificação (estágio 5) com todos os documentos obrigatórios aprovados.

### Lacunas encontradas

| # | Lacuna | Tarefa |
|---|---|---|
| 1 | Os papéis existem por projeto (`ProjectAgentMembership`), mas não por tarefa: não há verificador nomeado por entrega | M.1e |
| 2 | Nenhuma regra é checada ao nomear (independência, runtime de código, "nunca faz" da carta, carga) | M.1e |
| 3 | O orquestrador não recebe autoridade sobre o projeto; a delegação pode ser limitada a projeto, mas nada a concede | M.1f |
| 4 | Não há substituto quando o orquestrador fica indisponível | M.1f |
| 5 | Não existe o brief da missão nem o seu ciclo de versão e validação | M.1g |
| 6 | O Plano do projeto existe (1 registro) mas não é usado; não há checagem automática do plano | M.1h |
| 7 | A independência na revisão de documentos não é exigida; não há checagem automática de documento | M.1i |
| 8 | A missão não ganha um canal de coordenação, embora canais já aceitem projeto e membros com função | M.1j |
| 9 | O agente não tem como perguntar "qual é o meu papel e as minhas tarefas nesta missão" pelo MCP | M.1k |
| 10 | A regra dos canais "execução real só com o Marcelo" não diz como fica numa missão com plano aprovado | Resolvida acima (aprovação da baseline autoriza as tarefas dela); registrar na Foundation (M.1l) |

---
[← Índice](README.md)
