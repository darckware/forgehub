# Diagnóstico e as três ondas


**Sim, a direção está certa.** Os pedidos formam um desenho coerente e quase todo apoiado no que já
existe:
- um caminho único e rastreável para todo trabalho;
- os agentes operam e o Marcelo supervisiona e dá contexto;
- a Missão garante a conclusão com critérios comprovados;
- o Service Factory organiza documentação, tarefas e pasta do projeto;
- a Operação 24x7 vigia e as Atividades dos Agentes mostram;
- o contexto é controlado por camadas;
- o Darckware é a porta de entrada;
- autonomia só sobe com critério.

**Mas há quatro problemas de execução, e o plano foi ajustado para eles:**

| # | Problema | Evidência | Ajuste |
|---|---|---|---|
| 1 | **O plano cresceu mais rápido do que qualquer entrega.** São cerca de 130 tarefas em 14 frentes e 17 decisões abertas, e nada foi implementado. Foi exatamente assim que a primeira tentativa da Missão parou no meio | Seções 6–9 | Organizado em **três ondas** com critério de saída (0.1). Cada onda só começa quando a anterior sai. O escopo fica congelado: pedido novo vira item do projeto do plano (M0.5), não texto neste documento |
| 2 | **A base ainda não foi provada.** O Service Factory nunca foi usado de verdade, o MCP não cobre o ciclo, e a regra `STATUS: DONE` tem um dia. A qualidade real das entregas dos agentes ainda é desconhecida: nos últimos 7 dias, só 1 de 170 despachos falhou, mas antes da regra "concluído" incluía trabalho cortado no meio | V, M0.2 | A Onda 1 prova a base com **uma missão real pequena** antes de construir camadas em cima |
| 3 | **Há riscos reais hoje que o plano deixava para depois.** O hook de conhecimento varre toda a `knowledge_base` (a Lara pode receber dado pessoal da Maia). O `dev.sh` e a produção usam o mesmo banco | `knowledge_cycle.py` (`rglob` na raiz); `dev.sh` | C.2 e Q.4 sobem para a **Onda 1** |
| 4 | **Conceitos demais para a mesma coisa.** Missão, Projeto, Linha de serviço, Objetivo e Rotina, com risco de confusão para os agentes e para o Marcelo | 1.3–1.6, G.1 | **A Missão vira uma extensão do Projeto**, não uma entidade nova: `project_type = mission` + critérios de aceite + papéis + brief. Objetivos (G.1) só na Onda 3 |

Também corrigido: o backup externo **já funciona** (38 execuções `ok`, a última em 24/10). O risco
"sem snapshot" estava desatualizado. Resta testar a restauração (G.12).

## As três ondas

**Onda 1 — Base provada e riscos fechados.** Pequena, para terminar.

| Item | Por quê agora |
|---|---|
| **C.2** isolamento do `knowledge_cycle.py` (modo observação, depois ativo) | Risco de privacidade real hoje |
| **Q.4** homologação com banco separado do da produção | Agentes e o `dev.sh` tocam dado real |
| **V-a** validação do Service Factory pela tela/API | Nada se apoia em módulo não provado |
| **M0.1–M0.4** produto "Ecossistema Foundation", MCP mínimo, convenção de missão (papéis, brief, plano aprovado) e skill | Os agentes precisam conseguir registrar e conduzir uma missão |
| **M0.5** primeira missão real, pequena, conduzida pelos agentes | Prova o caminho inteiro de ponta a ponta |
| **A.1/A.2** todos os agentes e todas as rotinas nas Atividades dos Agentes | O Marcelo precisa ver o que acontece |

**Saída da Onda 1:**
- uma missão real abriu, planejou, executou, comprovou e fechou só com os agentes pelo MCP, com o
  Marcelo acompanhando, anotando e aprovando;
- C.2 está ativo com teste de vazamento verde;
- nenhum ambiente de teste aponta para o banco da produção.

**Onda 2 — Ligar o que existe.**
- S.1, S.2, S.4, S.5 (linhas de serviço; o renomear S.3 vai junto);
- R (racionalização);
- B (cadastro e importação);
- P (anotações, contexto herdado, linha do tempo);
- I (manutenção remota, horas, Auditor → tarefa, incidente);
- Q.1–Q.3 e Q.5 (git, CI, gate de produção);
- D núcleo: D.1, D.2, D.7, D.8, D.10;
- O.1–O.3;
- E.1 e E.4.

Saída da Onda 2: um serviço de cada linha percorreu o fluxo com evidência e documento, e o
Marcelo supervisionou pela linha do tempo.

**Onda 3 — Garantir e aprender.**
- Missão completa M.1a–M.1l e M.2–M.4 (sobre a extensão do Projeto);
- D restante (manual, identidade visual, auditoria de documentação);
- C restante;
- E restante;
- G (evals, lições, verificador, parada global, fila de decisões, laço de autoaperfeiçoamento, objetivos).

Regra das ondas: nada da Onda 2 começa antes de a Onda 1 sair. A exceção é o documento dos sete
sistemas (M.0), que só depende de leitura.

## Decisões: padrões adotados

Das 17 decisões da seção 9, as que têm recomendação passam a valer **como padrão revisável**. O
Marcelo só precisa responder estas três para começar:

1. **Começar a Onda 1** como está em 0.1.
2. **Primeira missão:** pequena e real, para provar o caminho. Sugestão: o controle de contexto C.0+C.1
   (linha de base da memória dos agentes e política na Foundation), que tem orquestrador (Athos),
   executores (Mnemosyne, Themis), documentador (Scriba) e critérios verificáveis. O plano integrado
   inteiro como missão fica para depois, quando o caminho estiver provado.
3. **Quem implementa a Onda 1:** o Claude Code (esta sessão) faz C.2, Q.4, V-a e o MCP mínimo, com
   revisão de outro agente, porque a capacidade de os agentes conduzirem o trabalho é justamente o que
   a Onda 1 prova.

---
[← Índice](README.md)
