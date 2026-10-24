# Lacunas e decisões

## Lacunas encontradas na revisão do plano (24/10)

| # | Lacuna | Onde foi tratada |
|---|---|---|
| 1 | A validação pelo agente dependia de ferramentas MCP que só viriam depois (ciclo) | V dividida em V-a (tela/API) e V-b (MCP); a V-b gera a lista da P.1 |
| 2 | Não havia regra de quando usar tarefa do Service Factory e quando usar Task do Messages | Regra em 1.1 |
| 3 | Sem git por tarefa, sem PR, sem CI, sem trava de repositório | Q.1–Q.3 |
| 4 | Sem ambiente de homologação; `dev.sh` e produção dividem o banco | Q.4 |
| 5 | Deploy sem gate formal nem rollback testado | Q.5 |
| 6 | Segredos de cada projeto fora do contrato do projeto | Q.6 |
| 7 | Custo e orçamento por projeto/missão | Q.7 |
| 8 | "Incidente" estava no objetivo mas sem fluxo | I.13 |
| 9 | O Service Factory começaria vazio: faltava importar projetos, documentos e pendências atuais | B.4 |
| 10 | Produtos reais ausentes da lista (Duplica, SAEDAS, FileNest, OsintKey, Marketing, Hermes) | B.1 |
| 11 | Anotar exigia a tela; o Marcelo também supervisiona pelo Telegram | P.9 |
| 12 | Skills, `CLAUDE.md` e Foundation não acompanhavam cada fase | Regra transversal antes da ordem |
| 13 | Numeração (faltava a seção 7) e diagrama de ordem com dependências invertidas | Corrigidos |

**Riscos que continuam abertos e precisam de acompanhamento:**
- **Tamanho do plano.** São mais de 100 tarefas. Sem disciplina de uma tarefa pequena por vez, com
  `STATUS: DONE` e evidência, ele repete o que aconteceu com a Missão. O próprio plano vira o primeiro
  projeto do Service Factory e é acompanhado por ele.
- ~~Backup externo sem snapshot~~ — corrigido: o backup externo roda com sucesso (38 execuções `ok`). Falta o teste de restauração (G.12).
- **Só 3 de 18 rotinas ligadas:** a Operação 24x7 só vigia de fato quando as rotinas da O.3 forem ligadas.
- **Dependência do ForgeRouter** para a seleção de modelo (G.9), que está fora deste plano.

## Decisões (padrões adotados; ver 0.2)

As recomendações abaixo valem como padrão revisável. Só as três de 0.2 bloqueiam o início.

1. Aposentar Execution Waves/Work Packages e o restante da Orquestração (R.1), que estão sem uso e
   duplicam o Messages como executor.
2. Fase V: pelo princípio 1.1, a validação natural é **um agente operando o Service Factory pelo
   MCP** com o roteiro acima, com você acompanhando, anotando e revisando o relatório; o Claude Code
   corrige os defeitos. Alternativa: você na tela.
3. Produtos internos da Fase B (lista proposta) e "Sustentação" permanente por produto.
4. Serviço a cliente: projeto por ticket/demanda (como o `:create-project` já faz, recomendado) ou um
   projeto por cliente com uma fase por ticket.
5. Horas: lançar no Darckware na conclusão da tarefa (recomendado) ou só manualmente.
6. A.1/A.2 e M.0 podem começar já, em paralelo à validação: autoriza?
7. As decisões da spec da Missão (coordenador, quem cria, dono da documentação).
8. Fase C: aprovar que C.0 (linha de base) e C.1 (política na Foundation, pelo Athos) comecem já, e
   que C.2 (isolamento do `knowledge_cycle.py`) seja feito pelo Porthus em modo observação primeiro.
9. Fase P: anotações em todos os níveis do Service Factory, herdadas no despacho das tarefas, e o MCP
   completo para os agentes operarem o módulo sem a tela.
10. Fase E (Darckware): projeto aprovado pelo cliente no portal vira projeto no Service Factory
   automaticamente (E.1), e o funil (E.4) pode começar já.
11. Fase Q: git por tarefa com PR, CI por repositório, ambiente de homologação separado e gate de
    produção com rollback (Q.1–Q.5).
12. **Service Factory (seção 1.3, Fase S):** confirmar o nome, as 9 linhas de serviço iniciais e a
    generalização (Produto = o que é atendido; Versão = o ciclo), mantendo rotas e tabelas.
13. **Papéis e validação (seção 1.6):** orquestrador, planejador, executores, verificadores e
    documentador nomeados na missão; aprovação da baseline do plano autoriza as tarefas dela;
    documentos-chave (brief, escopo, plano, resultado) aprovados por você.
14. **Pipeline (seção 1.5):** a Missão como garantia de conclusão — só ela declara um serviço
    concluído, com critérios de aceite comprovados um a um, saúde monitorada e aceite explícito.
15. **M0:** registrar já a primeira missão como projeto (o próprio plano integrado), com as
    ferramentas MCP mínimas e a convenção de missão, logo após a validação pela tela/API.
16. B.4: importar o estado atual dos produtos (pastas, documentos, pendências) antes de começar.
17. Fase G: aprovar a ideia dos **evals de capacidade** (G.6) e da **parada global** (G.10) como
   pré-requisitos para subir qualquer nível de autonomia.

---
[← Índice](README.md)
