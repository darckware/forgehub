# Ajuste para celular — plano tela por tela

> Status: checklist vivo. **Quem ajustar uma tela marca a caixa na mesma mudança** (mesma regra do
> `FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`: nunca atualizar em lote depois, de memória).

## Origem

2026-09-26, Marcelo, depois dos ajustes do Workspace/chat/Dashboard: "As telas ficaram boas no
ajuste que você fez. Precisa implementar para as outras telas os ajustes para uso no celular.
Faça um planejamento tela por tela do que está faltando ajustar."

**Como o levantamento foi feito:** cada rota aberta num Chromium em 390×844 (tamanho de iPhone,
toque emulado), com toda a API interceptada no navegador (listas vazias — nada tocou o backend
real). Para cada tela: quantos elementos passam da borda direita fora de uma área com rolagem
própria (transbordo intencional não conta) + screenshot revisado à mão, porque "não transborda"
não significa "está bom" (uma coluna fixa pode espremer o conteúdo sem sair da tela).

**Limites do levantamento** — ver também a Onda 5:
- Dados vazios: tabelas e listas cheias podem ter problemas que o estado vazio esconde.
- 7 telas quebraram com a resposta vazia do mock (esperavam objeto, receberam lista) — não é bug
  de produção, mas o layout delas não pôde ser avaliado: Configurações, Controle do Sistema,
  Hindsight, VPN, Nexo Agents, Diagrama do banco, Crons.
- Telas de detalhe (`/:id`) e diálogos não foram abertos — exigem dados reais.

## Já ajustado (2026-09-26)

- [x] Layout geral (`AppLayout.tsx`) — altura `100dvh` (a barra do navegador não esconde mais o rodapé)
- [x] Workspace — toolbar quebra linha, botão ≡ divide a linha com Conversas/Canais
- [x] Chat (Conversas) — composer em duas linhas, mensagens quebram URLs/caminhos, Histórico e Artefatos como sobreposição, copiar/editar visíveis em toque
- [x] Canais — lista como sobreposição, sessão individual do agente em tela cheia
- [x] Terminal — barra de digitação nativa + teclas especiais (corrige duplicação do teclado Android)
- [x] Dashboard — grid em coluna única, cabeçalhos dos cards sem corte

## Padrões encontrados (a causa se repete — corrigir na raiz primeiro)

| # | Padrão | Onde aparece | Correção |
|---|---|---|---|
| P1 | **Cabeçalho da página**: título + descrição + botões numa linha `justify-between`. Os botões saem pela direita ou a descrição vira uma coluna estreita de 8 linhas. Não existe componente compartilhado: são ~65 cabeçalhos escritos à mão, só 4 empilham no celular. | Produtos, Agentes, Tarefas, Planejamento, Deploy, Notificações, Servers, Pipelines, Artefatos, Políticas, Crons, Perfis, Usuários, Ferramentas, Skills | Criar `components/PageHeader.tsx` (título, descrição, ações; empilha abaixo de `sm`, ações quebram linha) e migrar as telas |
| P2 | **Tela dividida (lista + detalhe) com coluna fixa**: o conteúdo principal fica com ~50px ou some. | Mensagens, Documentos, Documentação (Foundation), Base de Conhecimento (Obsidian), Banco › Schema | Mesmo padrão do Canais: no celular a lista ocupa a tela; escolher um item abre o detalhe em tela cheia com botão "voltar" |
| P3 | **Tabela sem rolagem própria**: colunas cortadas à direita, sem como ver. | Servers, Irregularities, Chat Commands (e provavelmente outras com dados) | Envolver em `overflow-x-auto`; nas tabelas mais usadas, virar lista de cartões abaixo de `md` |
| P4 | **Barra de abas/filtros larga**: rótulos quebrando em 3–4 linhas ou saindo da tela. | Cockpit, Central de Projetos, Central de Sistemas, Deploy (abas só-ícone espremidas), Governança (chips) | Abas com `overflow-x-auto whitespace-nowrap` e rótulo curto no celular |
| P5 | **Toolbar de ícones sem quebra de linha** | Mensagens (30d/15d/…), Notificações | `flex-wrap` como na toolbar do Workspace |

## Onda 0 — fundação (resolve a maior parte de uma vez)

- [x] `PageHeader` compartilhado (P1) + teste
- [x] Padrão de lista/detalhe para celular (P2) — `hooks/useIsPhone.ts` (`usePhoneListDetail`); Mensagens e Documentos derivam direto da seleção que já tinham (lista some com `max-md:hidden` quando há item aberto, barra "voltar" com `md:hidden`)
- [x] Verificar `components/ui/table.tsx`: já tinha wrapper `overflow-x-auto` (P3). As tabelas cortadas no levantamento usam `<table>` cru (18 no código) — corrigir tela a tela
- [x] Barra de abas rolável (P4) — no próprio primitivo `components/ui/tabs.tsx` (`max-md:` apenas), cobre as 13 telas que o usam

## Onda 1 — uso diário (prioridade)

| ✓ | Tela | Rota | Problema observado | Padrão |
|---|---|---|---|---|
| [x] | Mensagens | `/demands` | Árvore Entrada/Saída/… e painel de leitura lado a lado: leitura espremida ("Selecione uma mensagem" em 1 palavra por linha); busca/filtro cortados à direita | P2, P5 |
| [x] | Notificações | `/notifications` | "Marcar todas como lidas / Manter últimos / Limpar tudo" saem 420px além da tela | P5 |
| [x] | Documentos | `/docs` | Árvore e editor em colunas fixas; 24 elementos cortados; conteúdo praticamente invisível | P2 |
| [x] | Tarefas | `/tasks` | Botão "Nova tarefa" cortado; descrição em coluna estreita; título da tarefa gigante | P1 |
| [x] | Planejamento | `/backlog` | Filtro de projeto e botões saem 780px além da tela | P1 |
| [x] | Cockpit | `/cockpit` | Filtros cortados; abas com rótulo em 3–4 linhas | P4 |
| [x] | Agentes | `/agents` | Filtro e "Sincronizar" saem 550px além da tela | P1 |

## Onda 2 — Software Factory

| ✓ | Tela | Rota | Problema observado | Padrão |
|---|---|---|---|---|
| [x] | Produtos | `/product` | "Novo produto" cortado | P1 |
| [x] | Central de Projetos | `/projects` | Abas com rótulo em 2 linhas (aceitável; revisar com dados) | P4 |
| [x] | Pipelines | `/pipeline` | Descrição em coluna estreita ao lado do botão | P1 |
| [x] | Modelos de Pipeline | `/pipeline-templates` | OK no teste — revalidar com dados | — |
| [x] | Concepção | `/conception` | OK no teste — revalidar com dados | — |
| [x] | Mapa do Sistema | `/system-map` | OK no teste — revalidar com dados (diagrama) | — |
| [x] | Escopo do Projeto | `/project-scope` | OK no teste — revalidar com dados | — |
| [x] | Telas & Regras | `/screen-inspector`, `/screen-rules` | OK no teste — revalidar com dados | — |
| [x] | Banco & ERD | `/concept-erd` | OK no teste — revalidar com dados (diagrama) | — |
| [x] | Governança | `/governance` | Chips de filtro OK; revalidar lista com dados | P4 |
| [x] | Políticas | `/governance/policies` | Descrição em coluna estreita ao lado do botão | P1 |
| [x] | Fechamento de Versão | `/version-closure` | OK no teste — revalidar com dados | — |
| [x] | Artefatos | `/artifact` | Descrição em coluna estreita (11 linhas) ao lado do botão | P1 |
| [x] | Deploy | `/deploy` | "Nova instalação" cortado; abas só-ícone espremidas, rótulos sobrepostos | P1, P4 |

## Onda 3 — Operações, agentes e configuração

| ✓ | Tela | Rota | Problema observado | Padrão |
|---|---|---|---|---|
| [x] | Servers | `/servers` | Tabela cortada (colunas PORT/DESC fora); abas de grupo cortadas; cabeçalho em coluna estreita | P1, P3, P4 |
| [x] | Irregularities | `/irregularities` | Tabela cortada à direita | P3 |
| [x] | Documentação (Foundation) | `/foundation` | Tela dividida, conteúdo espremido | P2 |
| [x] | Base de Conhecimento | `/obsidian` | Tela dividida, 26 elementos cortados | P2 |
| [x] | Banco › Schema | `/database/schema` | Lista de tabelas e detalhe lado a lado | P2 |
| [x] | Banco › Query | `/database/query` | Atalhos de tabelas cortados à direita | P4 |
| [x] | Chat Commands | `/prompt-commands` | Coluna ACTIONS parecia cortada, mas a tabela já usa o primitivo com rolagem — sem mudança | P3 |
| [x] | Usuários | `/users` | Revalidar tabela com dados | P3 |
| [x] | Perfis de Acesso | `/profiles` | Revalidar com dados | P1 |
| [x] | Clientes / Novo cliente | `/clients`, `/clients/new` | OK no teste | — |
| [x] | Atividade dos Agentes | `/agent-activity` | OK no teste — revalidar topologia com dados | — |
| [x] | MCP / Central de Sistemas | `/mcp`, `/systems-hub` | OK no teste; abas da Central com rótulo em 2 linhas | P4 |
| [x] | Ferramentas / Skills | `/tools`, `/skills` | Cabeçalho com contador espremido; revalidar com dados | P1 |
| [x] | Técnicas de Prompt | `/prompt-techniques` | OK no teste | — |
| [x] | Auditor | `/auditor` | OK no teste | — |
| [ ] | ForgeRouter | `/forgerouter` | Tela de login embutida (iframe) — só revisar se couber | — |

## Onda 4 — não avaliadas (precisam de dados reais)

Quebraram com a resposta vazia do mock. Avaliadas em 2026-09-26 com dados de exemplo no formato de cada
endpoint (textos longos de propósito). Causa principal em Hindsight/VPN/Controle do Sistema: grids sem
`grid-cols-1` (coluna implícita cresce até o conteúdo — mesmo defeito do Dashboard) + URLs/caminhos sem quebra:

- [x] Configurações (`/settings`)
- [x] Controle do Sistema (`/system-control`)
- [x] Hindsight (`/hindsight`)
- [x] VPN (`/vpn`)
- [x] Nexo Agents (`/nexo-agents`)
- [x] Crons (`/crons`)
- [x] Banco › Diagrama (`/database/diagram`)

## Onda 5 — telas de detalhe e diálogos

Não abertas no levantamento. Revisar depois das ondas 1–3, quando o `PageHeader` e o padrão de
lista/detalhe já existirem:

- [ ] Detalhes: `/product/:id`, `/projects/:id`, `/pipeline/:id`, `/backlog/:id`, `/tasks/:id`,
      `/agents/:id`, `/artifact/:id`, `/governance/:id`, `/clients/:id`
- [ ] Diálogos e formulários (`components/ui/dialog.tsx`): largura máxima, rolagem interna, botões
      no rodapé visíveis com o teclado aberto

## Critério de "pronto" por tela

- [ ] Em 390px nada passa da borda fora de uma área com rolagem própria
- [ ] Todas as ações da tela alcançáveis (nenhum botão cortado ou escondido atrás de hover)
- [ ] Campos de texto com fonte ≥ 16px no celular (o iOS dá zoom abaixo disso)
- [ ] Em 1440px a tela fica igual a antes (usar variantes `max-md:`/`md:`, nunca mudar o desktop)
- [ ] `tsc -b` e `npm test` passando
