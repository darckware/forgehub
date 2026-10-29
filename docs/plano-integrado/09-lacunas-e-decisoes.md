# Lacunas e decisões

## Lacunas encontradas na revisão do plano (24/10)

| # | Lacuna | Onde foi tratada |
|---|---|---|
| 1 | A validação pelo agente dependia de ferramentas MCP que só viriam depois (ciclo) | V dividida em V-a (tela/API) e V-b (MCP); a V-b gera a lista da P.1 |
| 2 | Não havia regra de quando usar tarefa do Service Factory e quando usar Task do Messages | Regra em 1.1 |
| 3 | Sem git por tarefa, sem PR, sem CI, sem trava de repositório | Q.1–Q.3 |
| 4 | Sem ambiente de homologação; `dev.sh` e produção dividem o banco | T.1/T.2 (substituem Q.4) |
| 5 | Deploy sem gate formal nem rollback testado | Q.5 |
| 6 | Segredos de cada projeto fora do contrato do projeto | Q.6 |
| 7 | Custo e orçamento por projeto/missão | Q.7 |
| 8 | "Incidente" estava no objetivo mas sem fluxo | I.13 |
| 9 | O Service Factory começaria vazio: faltava importar projetos, documentos e pendências atuais | B.4 |
| 10 | Produtos reais ausentes da lista (Duplica, SAEDAS, FileNest, OsintKey, Marketing, Hermes) | B.1 |
| 11 | Anotar exigia a tela; o Marcelo também supervisiona pelo Telegram | P.9 |
| 12 | Skills, `CLAUDE.md` e Foundation não acompanhavam cada fase | Regra transversal antes da ordem |
| 13 | Numeração (faltava a seção 7) e diagrama de ordem com dependências invertidas | Corrigidos |

**Achado em 24/10:** dois agentes de teste ("Global Owner 95d695fb", "Scoped Owner 95d695fb") estão ativos no banco de produção, sobra do teste `test_responsibility_area.py`, que falhou de forma intermitente na suíte e não limpou o que criou. Limpar os registros e corrigir a limpeza do teste.

**Riscos que continuam abertos e precisam de acompanhamento:**
- **Tamanho do plano.** São mais de 100 tarefas. Sem disciplina de uma tarefa pequena por vez, com
  `STATUS: DONE` e evidência, ele repete o que aconteceu com a Missão. O próprio plano vira o primeiro
  projeto do Service Factory e é acompanhado por ele.
- **Recuperação ainda não comprovada por alvo:** há snapshots históricos, mas faltam cobertura/recência por destino crítico e restauração de amostra (G.12). Falha do sistema não é anulada por sucesso de outro projeto.
- **Só 3 de 18 rotinas ligadas:** a Operação 24x7 só vigia de fato quando as rotinas da O.3 forem ligadas.
- **Dependência do ForgeRouter** para a seleção de modelo (G.9), que está fora deste plano.

## Decisões e limites de autorização — consolidação 27/10

**Novas (área de teste e identidade, [10](10-area-de-teste-e-identidade.md)):**
- Área de teste na Onda 1, com banco separado e integrações simuladas.
- ForgeVault como provedor de identidade dos agentes (token curto, assinado com chave assimétrica, por sistema e ambiente). A alternativa de só guardar os tokens atuais no ForgeVault fica apenas como transição.
- Por padrão, os agentes só recebem acesso ao ambiente de teste; a produção exige concessão por papel ou por missão.


Marcelo aprovou nesta conversa incorporar as correções e fechar a primeira onda. Este registro não
atribui a ele decisões operacionais que não foram apresentadas individualmente. Para tornar o plano
concreto, o redator adotou abaixo as recomendações existentes como **premissas revisáveis de planejamento**.
Permissões de produção, gasto, publicação, Foundation e dados pessoais continuam com os gates próprios.
Nenhuma identidade, produto, credencial, VM ou task foi criada por este registro.

**Decisão do Marcelo (0.15, 28/10/2026):** D-1 a D-8 foram apresentadas uma a uma e aprovadas como
na tabela abaixo. A D-1 mudou: o Codex (Aramis) está sem cota, então **Porthus implementa e Dartan
revisa**. A D-4 foi aprovada como "decidir depois": a Onda 1 é só Linux, e a máquina Windows é escolhida
antes da T.4b. Essas aprovações valem para o desenho. Não liberam gasto, publicação, credencial nem
despacho, que continuam com os gates próprios de cada tarefa.

| Decisão | O que foi decidido | Limite / confirmação na execução |
|---|---|---|
| D-1 | **Decidido em 28/10:** Porthus implementa; Dartan revisa código/telas/testes (Aramis/Codex sem cota) | Revalidar a cota do agy antes de cada atribuição; sem cota do Dartan, a revisão espera, nunca vira autorrevisão. Porthus e Claude Code são a mesma identidade |
| D-2 | **Aprovado em 28/10:** C.0+C.1 é a primeira missão; plano integrado é projeto comum no Ecossistema Foundation | Abertura após M0.4/M0.R e contenção C.2.R; prazo, orçamento, papéis e baseline exata antes do despacho |
| D-3 | **Aprovado em 28/10:** Projeto coordenador vinculado aos projetos executores; gates de 04 | M0.0/M.1 especificam migrations; não aplicar código parcial antigo |
| D-4 | **Aprovado em 28/10:** Linux na Onda 1; Windows T.4b na Onda 2 | **Pendente de alvo/capacidade/custo:** nenhum host Windows escolhido, nenhuma VM/compra autorizada |
| D-5 | **Aprovado em 28/10:** Negócio/brief em pt-BR; spec técnica/ADR/API/código em inglês conforme padrão 18 | Foundation continua em inglês conforme sua política própria; esta consolidação preserva pt-BR do plano |
| D-6 | **Aprovado em 28/10:** Referências de responsáveis propostas abaixo | Titularidade/delegação no banco só após validação do registro e confirmação do cadastro/baseline |
| D-7 | **Aprovado em 28/10:** Manter a regra da Lara sem contato por rotina | Nenhum envio/prospecção autorizado por esta aprovação |
| D-8 | **Aprovado em 28/10:** Kairos como reviewer em missão comercial | Usar vocabulário de papéis existente; sem criar função nova |

**Decisões do Marcelo em 29/10/2026:**
- **Tela mínima de execuções da missão na M0** (tarefas, executor, estado, provas, revisor, aceite), antecipada da M.1 da Onda 3: a condução da Onda 1 por mensagens e monitores improvisados mostrou que sem ela o orquestrador não consegue gerenciar as execuções. Entra na especificação M0.SPEC.
- **O orquestrador decide e agenda pela Operação 24x7** (04 §7), e podem existir várias missões cadastradas e ativas (04 §6). Entra na M0.SPEC.
- **M0.SPEC passa do Daedalus para o Porthus**, com revisão do Dartan e do Aegis: agentes Hermes não editam repositório, e a especificação exige leitura exata do código. O Daedalus é consultado, sem editar.

Responsáveis de produto (K6, aprovados em D-6): Ecossistema Foundation → Athos; ForgeHub → Daedalus;
ForgeRouter → Atlas; ForgeVault → Aegis; Darckware → Kairos; Serviços de Manutenção → Hephaestus.
Outros produtos recebem dono no inventário B.1, sem atribuição inventada. Não confundir dono do
produto com executor de código ou aprovação de produção.

## Histórico dos 17 temas (não é autorização imediata)

Os 17 temas originais abaixo continuam referências de escopo; prevalecem 04/07/08/10/12 e as decisões
acima quando os textos históricos se repetirem. A revisão cruzada desta edição é o gate 0.14;
sua conclusão não aprova políticas/credenciais/deploy que cada tarefa ainda precisará apresentar.

1. Aposentar Execution Waves/Work Packages e o restante da Orquestração (R.1), que estão sem uso e
   duplicam o Messages como executor.
2. Fase V: pelo princípio 1.1, a validação natural é **um agente operando o Service Factory pelo
   MCP** com o roteiro acima, com você acompanhando, anotando e revisando o relatório; o Claude Code
   corrige os defeitos. Alternativa: você na tela.
3. Produtos internos da Fase B (lista proposta) e "Sustentação" permanente por produto.
4. Serviço a cliente: projeto por ticket/demanda (como o `:create-project` já faz, recomendado) ou um
   projeto por cliente com uma fase por ticket.
5. Horas: lançar no Darckware na conclusão da tarefa (recomendado) ou só manualmente.
6. A.1/A.2 seguem T.2+T.3; M.0 documental pode avançar conforme 07, sem iniciar execução mutante antes do isolamento.
7. As decisões da spec da Missão (coordenador, quem cria, dono da documentação) são substituídas pelo contrato do 04; não reabrir a lista histórica.
8. Fase C: a indicação antiga de começar C.0/C.1 imediatamente está **superada**: ambas são executadas após a abertura M0.5; antes disso apenas preparação de leitura, e
   que C.2 (isolamento do `knowledge_cycle.py`) segue dividido: C.2a/C.2.R contêm o hook antes da missão; C.2b/C.2b.R completam a política depois de C.1; Porthus escreve, Dartan revisa (com o Aegis como segundo revisor na C.2a) e Athos publica pelo processo canônico.
9. Fase P: anotações em todos os níveis do Service Factory, herdadas no despacho das tarefas, e o MCP
   completo para os agentes operarem o módulo sem a tela.
10. Fase E (Darckware): projeto aprovado pelo cliente no portal vira projeto no Service Factory
   automaticamente (E.1), e o funil (E.4) pode começar já.
11. Fase Q: git por tarefa com PR, CI por repositório, ambiente de homologação separado e gate de
    produção com rollback (Q.0–Q.5).
12. **Service Factory (seção 1.3, Fase S):** confirmar o nome, as 9 linhas de serviço iniciais e a
    generalização (Produto = o que é atendido; Versão = o ciclo), mantendo rotas e tabelas.
13. **Papéis e validação (seção 1.6):** orquestrador, planejador, executores, verificadores e
    documentador nomeados na missão; aprovação da baseline do plano autoriza as tarefas dela;
    documentos-chave (brief, escopo, plano, resultado) aprovados por você.
14. **Pipeline (seção 1.5):** a Missão como garantia de conclusão — em trabalho de missão, só o aceite da missão declara o conjunto
    concluído, com critérios de aceite comprovados um a um, saúde monitorada e aceite explícito.
15. **M0:** abrir a primeira missão real C.0+C.1 após ferramentas, guards e convenção verificados; o plano integrado é projeto comum separado, não a primeira missão. Registro real em produção; ensaios mutantes depois de T.2+T.3.
16. B.4: importar o estado atual dos produtos (pastas, documentos, pendências) antes de começar.
17. Fase G: aprovar a ideia dos **evals de capacidade** (G.6) e da **parada global** (G.10) como
   pré-requisitos para subir qualquer nível de autonomia.

---
[← Índice](README.md)
