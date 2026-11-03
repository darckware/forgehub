# Roteiro de revisão crítica do plano integrado

**Data:** 2026-10-24
**Objetivo:** antes de qualquer implementação, cada agente analisa o plano pela sua especialidade,
critica e propõe melhorias (Marcelo: "precisamos analisar todas as camadas do planejamento na
documentação antes da implementação").

**Regra:** a revisão é **somente leitura**. Nenhum revisor altera os documentos. Cada um devolve o
parecer no resultado da tarefa. O Claude Code consolida os pareceres em `CONSOLIDADO.md`, com análise
de cada proposta (aceitar, ajustar ou rejeitar, sempre com motivo), e o Marcelo decide.

## Quem revisa o quê

| Revisor | Runtime | Camada que analisa | Documentos principais | Perguntas que precisa responder |
|---|---|---|---|---|
| **Porthus** | Claude Code | Arquitetura e coerência entre camadas | Todos; foco em 01, 02, 04, 05, 07, 10 e `missao-especificacao.md` | As camadas se contradizem? A Missão como extensão do Projeto é o modelo certo? O que falta no modelo de dados? Algo está sendo reconstruído sem necessidade? |
| **Aramis** | Codex | Viabilidade técnica do backend | 07 (todas as fases), 10 (F.2 no ForgeVault em .NET, F.4), 04, 03, 05 | Cada tarefa é implementável como está escrita? Que migrations, rotas e ferramentas MCP faltam? Que dependência técnica não foi listada? Qual o esforço relativo das tarefas da Onda 1? |
| **Dartan** | agy | Telas, experiência e testes no navegador | 06, 04, 03, 11; em 07 as fases A, P, D (D.12, D.13) e S.4 | O painel da missão, o Cockpit por linha, as Atividades dos Agentes e as anotações funcionam no celular? A identidade visual e a homologação de design estão completas? |
| **Athos** | Hermes | Governança, processo e Foundation | 01, 02, 04, 08, 09 | Os papéis, gates e níveis de autonomia são governáveis? Algo contraria a Foundation ou a política comum? O orquestrador consegue de fato conduzir uma missão? |
| **Atlas** | Hermes | Planejamento | 01, 07 | As ondas e dependências fazem sentido? As tarefas estão do tamanho certo? Os critérios de saída das ondas são verificáveis? Qual é o caminho crítico? |
| **Daedalus** | Hermes | Qualidade da especificação para os executores | 07 (especialmente Q, I, M0), 04 | Um agente externo consegue executar cada tarefa só com o que está escrito? O fluxo git/PR/CI da Fase Q está completo? |
| **Hephaestus** | Hermes | Infraestrutura e operação | 10 (Fase T), 07 (Q.5, I.10–I.13), 08 (G.12) | A área de teste (bancos, aplicações, máquinas de teste, reset), o gate de deploy com rollback, incidentes e restauração são viáveis neste VPS? O que falta? |
| **Aegis** | Hermes | Segurança e identidade | 10 (Fases T e F), 11 (política de rede, injeção de prompt por páginas, credenciais no navegador), 07 (I.2, I.5, Q.6, E.8), 08 (G.10), 05 | O ForgeVault como provedor de identidade (troca de token, chaves, ambientes, revogação, falha do ForgeVault) é seguro? Manutenção remota, segredos por projeto, parada global, injeção de prompt e exposição do Darckware estão bem cobertos? |
| **Themis** | Hermes | LGPD e conformidade | 07 (fases C e E), 04 (contexto da missão), 11 (coleta de dados e redes sociais) | A classificação dos dados, o isolamento Maia/Lara, os dados de leads e clientes e a retenção atendem à LGPD? |
| **Mnemosyne** | Hermes | Memória e contexto | 07 (fase C), 04 (brief e contexto), 08 | As camadas de contexto, a precedência e a promoção para Hindsight/KB/Foundation estão corretas? O brief da missão conversa com a memória dos agentes? |
| **Scriba** | Hermes | Documentação | Todos (clareza), 07 (fase D), 04 (validação da documentação) | O conjunto é claro para quem nunca o viu? A pasta padrão do projeto e a validação de documentos seguem o padrão 18? O que está ambíguo? |
| **Kairos** | Hermes | Captação, mercado e redes sociais | 03, 07 (fase E), 11 (N.7, N.8) | O funil do Darckware e a linha de Marketing e captação geram o que é preciso para crescer? Que indicador falta? |

**Ficam de fora, por desenho:** Lara (atende clientes; documento interno de planejamento não deve
entrar no contexto dela) e Maia (assistente pessoal).

**Pergunta comum a todos:** as três regras essenciais da Missão (quando começar, como validar a
entrega, quando marcar como concluída; `04-missao-pipeline-e-papeis.md`, primeira seção) são
suficientes e verificáveis do ponto de vista da sua especialidade? O que falta?

## Formato do parecer (igual para todos)

```
## Parecer de <agente> — <camada>

### O que está bom e deve ser mantido
- ...

### Problemas e melhorias
| # | Severidade | Documento e seção | Problema | Evidência | Proposta |
|---|---|---|---|---|---|
| 1 | bloqueia / importante / melhoria | 07, Q.4 | ... | arquivo, rota, dado ou regra que comprova | ... |

### Respostas às perguntas do roteiro
1. ...

### Sobre as três regras da Missão (começar, validar, concluir)
- ...

STATUS: DONE
```

Severidade:
- **bloqueia:** não dá para implementar como está, ou há risco sério;
- **importante:** precisa mudar antes da onda em que o item está;
- **melhoria:** vale fazer, mas não impede.

Toda crítica precisa de **evidência** (arquivo, rota, tabela, documento da Foundation ou regra). Opinião
sem evidência entra como pergunta, não como problema.

## Como roda

Esta revisão é a **Fase 0** do planejamento ([07](../07-fases-de-implementacao.md)), tarefas 0.1 a 0.15.


1. **Rodada 1 (paralela):** uma tarefa no Messages para cada revisor, `working_path`
   `/root/project/forgehub`, com este roteiro, a camada dele e o formato. Respeita o teto de
   concorrência e um despacho por agente.
2. **Consolidação:** o Claude Code junta os pareceres em `CONSOLIDADO.md`, agrupando os problemas
   repetidos. Cada proposta recebe análise (aceitar, ajustar ou rejeitar) com motivo.
3. **Rodada 2 (cruzada):** Porthus e Athos revisam o consolidado. A pergunta é se alguma decisão
   cria contradição entre camadas.
4. **Decisão do Marcelo** sobre o que entra. Os documentos são atualizados num único commit, com
   referência ao item do consolidado.
5. **Só então começa a Onda 1.**

**Critério de pronto da revisão:**
- todos os pareceres recebidos com `STATUS: DONE`;
- nenhum item "bloqueia" sem decisão;
- os documentos atualizados.
