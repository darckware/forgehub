# Visão e princípios


Todo trabalho do ecossistema passa por um único caminho rastreável, seja ele implementação, manutenção
de sistema, serviço em estação ou servidor de cliente, documentação, incidente ou missão:

```
Darckware (site, chat da Lara, portal) ─┐
Entrada ──► Service Factory ──► Messages ──► Agente ──► Evidência ──► Documento ──► Aceite
(pedido,     (Produto/Versão/     (único       (Hermes ou  (git/file/db/  (DocLink)     (Marcelo ou
 ticket,      Projeto/Fase/        executor)    externo)    execução                   delegação)
 check,       Tarefa)                                       remota)
 missão)
                     ▲                                                          │
                     └──── Operação 24x7 vigia, cobra e escala ◄────────────────┘
                           Agent Activity mostra tudo em tempo real
```

## Princípio de uso: o agente opera, o Marcelo supervisiona e dá contexto

O Service Factory é **operado pelos agentes** pelo MCP `forgehub`: eles criam o planejamento, as
tarefas e as dependências, despacham, registram evidência e documentos e fecham as fases. O Marcelo
não precisa operar o módulo. Ele:
- **monitora** o que os agentes fizeram (linha do tempo, Cockpit, Agent Activity);
- **decide** o que é dele (fila única de decisões);
- **acrescenta contexto**: anotações e documentos em qualquer nível (produto, versão, projeto, fase,
  tarefa, missão), que passam a acompanhar automaticamente toda tarefa abaixo daquele nível.

Consequências para o plano:
- toda ação da tela tem uma ferramenta MCP equivalente;
- toda ação de agente é auditada com o nome do agente;
- a anotação do Marcelo é a camada de maior precedência do contexto (Fase C, camada 1);
- **regra de uso:** trabalho com entrega (código, documento, manutenção, serviço) é tarefa do Software
  Factory; o Messages é o executor e o canal de conversa entre agentes, não o lugar de registrar
  trabalho. Uma Task solta no Messages só para pergunta, aviso ou algo que não deixa entrega.

## Para que serve o Service Factory

É o centro de gestão do desenvolvimento. O que ele gerencia, onde isso já existe e o que falta:

| O Marcelo precisa | Já existe | Falta | Tarefas |
|---|---|---|---|
| **Documentação** do projeto organizada e com estado (rascunho, em revisão, aprovado) | Concepção gera `PRD.md`, `SPEC-TECNOLOGIA.md`, `SCREEN-TEMPLATES.md`, `DESIGN-SYSTEM.md` (padrão 18 da Foundation) e copia para `docs/` do projeto; Artefatos; `DocLink`; Pipelines | Conjunto completo de documentos por projeto, estado de cada um, documento obrigatório por estágio | D.1–D.5, D.7, D.11 |
| **Manual do sistema** (uso e operação) | Telas e regras de negócio no Escopo | Manual gerado e atualizado a cada versão | D.9 |
| **Controle das tarefas** | Planejamento, tarefas, dependências, status, evidência, Cockpit | Linha do tempo e supervisão | P.5, P.6 |
| **Distribuição das demandas entre os agentes** | Atribuição, membros do projeto por tipo de solução, despacho pelo Messages | Sugestão de agente por skill/carta, MCP completo | I.11, P.1 |
| **Pasta do projeto organizada e descritiva** | Navegador de arquivos do projeto; cópia dos documentos da Concepção para `docs/` | Estrutura padrão (padrão 19), índice, guia para agentes, verificação de divergência entre a pasta e o Service Factory | D.7, D.10, D.11 |
| **Administrar e auditar** o desenvolvimento | Governança, `AuditEvent`, aprovações, fechamento de versão | Completude da documentação por projeto, auditoria de quem mudou o quê | D.11, P.5 |
| **Identidade visual:** design system, logomarca, cores, tipografia, ícones, templates de tela, protótipos | Concepção gera `DESIGN-SYSTEM.md` e `SCREEN-TEMPLATES.md`; MCP salva protótipo HTML de tela; padrão 02 da Foundation (UI e design system); o Darckware tem homologação de design própria | Logomarca e ativos guardados no projeto, tokens de design aplicáveis no código, homologação antes de implementar tela | D.12, D.13 |
| **Contexto do projeto para os agentes:** escopo, banco, deploy, metodologia, specs | Escopo e telas; modelo de banco derivado (ERD); Deploy; padrões 01–19 da stack | Um **contrato do projeto** que declara metodologia, specs e padrões adotados, banco, ambientes de deploy, e vai junto em todo despacho | D.8, P.4 |

---
[← Índice](README.md)
