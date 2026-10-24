# Inteligência operacional própria ("nossa AGI")


## O que é realista

Nenhuma integração de sistemas produz uma AGI geral, e o plano não promete isso. O que dá para
construir com Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk e Darckware é uma **organização de
agentes autônoma e que melhora sozinha**:
- recebe objetivos;
- planeja e executa com evidência;
- mantém sistemas e máquinas;
- aprende com o resultado;
- melhora o próprio software, dentro de limites que o Marcelo controla.

O plano até a seção 6 cobre o **corpo** desse sistema: executar, registrar, vigiar e coordenar. A
análise abaixo mostra o que ainda falta para que ele **aprenda, se avalie e se corrija** de forma
mensurável e segura.

## O que já existe e o que falta

| Capacidade | Já existe | Falta | Fase |
|---|---|---|---|
| Agir no mundo | Messages, Acesso Remoto (Tailscale/RustDesk), Deploy, MCP, tools | — | — |
| Planejar | Service Factory, Missão (proposta), cartas | Hierarquia de objetivos acima das missões | G.1 |
| Perceber | Telemetria, Auditor, notificações, Messages, canais, Darckware (site, chat, leads, portal) | Um fluxo único de eventos que dispare iniciativa | G.2 |
| Lembrar | Hindsight, KB, Foundation, `MEMORY.md` | Controle das camadas com precedência, proveniência e isolamento | **Fase C** |
| Conhecer o próprio ambiente | Blueprints, máquinas, deploy, checks, scripts — em telas separadas | Um mapa único do ecossistema (o que existe, depende de quê, quem é dono) | G.4 |
| Verificar o próprio trabalho | `STATUS: DONE`, evidência `git:`/`file:`/`db:`, revisão do Porthus | Verificação independente do resultado por tipo de tarefa (não só "existe") | G.5 |
| **Medir a própria capacidade** | Evolução mede operação (falhas, prazos) | **Avaliações de capacidade (evals)**: tarefas-padrão por agente e domínio, repetidas, com nota. Sem isso não há como saber se uma mudança de modelo, skill ou prompt melhorou ou piorou | G.6 |
| **Aprender com o resultado** | Hindsight retém conversa; curator de skills; Evolução registra mudanças | **Lições estruturadas**: cada falha ou retrabalho gera uma lição com causa e evidência, que vira proposta de skill, carta ou rotina, avaliada pelos evals antes de valer | G.7 |
| **Melhorar o próprio software** | Retrospectiva propõe; A2 vai ao Marcelo | O laço completo: proposta → Missão → projeto → implementação pelos externos → evals → deploy → medição, de ponta a ponta | G.8 |
| Escolher o modelo certo | ForgeRouter (roteamento, fallback) | Seleção guiada pelos evals por tipo de tarefa — **no projeto ForgeRouter**, não no ForgeHub | G.9 (fora) |
| Segurança da autonomia | A0/A1/A2, delegações, redação de segredos, "dados não são instruções" | **Parada global** (pausar toda autonomia, ou a de um agente, num toque), orçamento de autonomia, testes de injeção de prompt vindos de WhatsApp/e-mail/web, registro de toda ação autônoma reversível | G.10 |
| Decisões do Marcelo | Aprovações, dúvidas, A2, incubação, aceite de missão — em telas diferentes | **Uma fila única de decisões**, com resumo e recomendação, também no Telegram | G.11 |
| Continuidade | Backup externo funcionando (38 execuções `ok`), gateway único | Recuperação testada do estado dos agentes (perfis, memória, banco) | G.12 |

## Fase G — Capacidade de aprender (depois de M.1)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| G.1 | **Objetivos** (trimestrais, com métrica) acima das missões: toda missão serve a um objetivo; o briefing mostra o avanço | Aramis + Dartan | M.1 | Missão sem objetivo só como exceção explícita |
| G.2 | **Fluxo de eventos**: normalizar o que já chega (checks, alertas, Messages, tickets, telemetria, execuções remotas) num registro único que a triagem e as regras de iniciativa consomem | Aramis | A.5 | Toda iniciativa automática cita o evento que a disparou |
| G.3 | Coberto pela **Fase C** (controle de contexto) | — | — | — |
| G.4 | **Mapa do ecossistema**: sistemas, máquinas (Tailscale), serviços, deploys, checks, donos e dependências num grafo consultável por MCP | Aramis + Dartan | B.1 | Um agente responde "o que depende do X e quem é o dono" pelo MCP |
| G.5 | **Verificador por tipo de tarefa**: código (testes + revisão), manutenção (estado da máquina depois), documentação (artefato revisado); agente diferente do executor | Porthus + Aramis | I.5, D.2 | Tarefa só fica `done` com verificação do tipo |
| G.6 | **Evals de capacidade**: conjunto de tarefas-padrão por agente e domínio (seguras e repetíveis, em ambiente de teste), rodadas por rotina semanal e a cada mudança de modelo, skill ou prompt; nota histórica no Agent Activity | Porthus (desenho) + Aramis | A.4 | Toda mudança A1/A2 de agente mostra a nota antes e depois |
| G.7 | **Lições**: falha, `PARTIAL`, reprocesso ou rejeição de revisão → lição (causa, evidência, recomendação) → proposta de skill/carta/rotina → avaliada por G.6 → aplicada pelo nível de autonomia | Aramis + Athos | G.6 | Lição repetida não gera proposta duplicada; nenhuma skill muda sem eval |
| G.8 | **Laço de autoaperfeiçoamento do software**: proposta A2 aprovada vira Missão automaticamente, com projeto, tarefas para os externos, evals e medição pós-deploy | Aramis | G.6, M.1 | Uma melhoria percorre o laço inteiro com registro em cada etapa |
| G.9 | Seleção de modelo guiada por evals | projeto **ForgeRouter** | G.6 | Fora deste plano; o ForgeHub só fornece as notas |
| G.10 | **Segurança da autonomia**: parada global e por agente; orçamento de ações autônomas; suíte de injeção de prompt (WhatsApp, e-mail, web, documento); toda ação autônoma com desfazer ou registro de irreversível | Porthus + Aegis | A.1 | Parada testada; suíte verde antes de subir qualquer nível M |
| G.11 | **Fila única de decisões** do Marcelo (aprovações, A2, dúvidas, aceite de missão, incubação madura), na tela e no Telegram | Aramis + Dartan | O.2 | Nenhuma decisão pendente fora da fila |
| G.12 | **Recuperação testada** do estado dos agentes (perfis Hermes, memória, banco do ForgeHub) a partir do backup externo | Hephaestus (rotina) + Aramis | backup externo (já funcionando) | Teste de restauração trimestral registrado |

## Níveis de autonomia revistos

Os níveis M0–M3 da Missão passam a exigir os itens da Fase G:

| Nível | Exige |
|---|---|
| M1 (coordenador propõe o plano) | G.10 (parada global) e G.11 (fila de decisões) |
| M2 (tarefas de baixo risco sem aprovação item a item) | G.5 (verificador) e G.6 (evals) com nota estável por 30 dias |
| M3 (o sistema propõe missões) | G.1, G.2, G.7 e G.8 funcionando; suíte de segurança G.10 verde |

## Ordem

```
... M.1 ──► G.10 ──► G.11 ──► G.5 ──► G.6 ──► G.7 ──► G.8
             G.1, G.2, G.3, G.4, G.12 em paralelo, conforme as dependências da tabela
```

---
[← Índice](README.md)
