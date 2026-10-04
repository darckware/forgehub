> Plano compartilhado ForgeHub ↔ Darckware. Cópia gêmea: `/root/project/darckware/docs/superpowers/plans/2026-10-04-client-demands-forgehub.md`. Aprovado por Marcelo em 2026-10-04.

# Plano — Demandas de clientes, contratos e e-mails aprovados (ForgeHub + Darckware)

## Contexto

O gargalo: as demandas de desenvolvimento e serviço dos clientes não têm lugar único. O CRM da
Darckware está **vazio** (0 clientes, 0 tickets, 0 demandas, 0 leads) — as demandas vivem na
cabeça do Marcelo, no Telegram e no e-mail — e toda resposta ao cliente depende de aprovação
individual no Telegram (`SOUL.md` da Lara; spec `2026-09-28-lara-omnichannel-crm-design.md`,
decisão 2 "em aberto", estado seguro = não enviar nada).

Objetivo: **Darckware guarda, ForgeHub opera.**
- Darckware = CRM e fonte da verdade: cliente, contato, lead, contrato, ticket/demanda e
  **todo e-mail** (fila, envio, histórico). Abertura de ticket continua lá (portal/Lara).
- ForgeHub = console: lança demandas e contratos (gravando na Darckware), executa pela Software
  Factory, dá baixa, e é **o lugar onde o Marcelo aprova** os e-mails. Aprovado no ForgeHub, a
  Lara envia sem passar pelo Telegram (Telegram vira só aviso).

### Decisões tomadas (2026-10-04)
| Tema | Decisão |
|---|---|
| Onde mora a demanda | Darckware (Ticket + ClientDemand); ForgeHub não copia |
| Controle de e-mails | Darckware (fila `outbound_emails`); ForgeHub só aprova via API |
| Remetente | **Tudo pela Lara** (`comercial@`, assinatura Lara) — matriz por área deixa de valer para saída |
| Contrato / conversão | Lançados **no ForgeHub**, gravados na Darckware |
| Conversão de lead | **Lara propõe, Marcelo aprova** |
| Aprovação | Do **texto final** (versão + hash); editar invalida a aprovação |
| Informe ao cliente | **Mensal**, no `billing_cycle_day` do contrato |
| Nexo | Não será usado (acesso via Tailscale/RustDesk) — fora deste plano |

### Lacunas encontradas na Darckware
- Lead → cliente não existe: `Lead` não liga a `ClientAccount`; `commercial_status=ganho` não dispara nada.
- `ClientContract` só cobre franquia de horas, um por cliente (upsert admin), sem tipo/status/datas/valor de projeto; não exposto na API de agentes.
- E-mail: envio direto (`_send_email_core`, `mcp/server.py`; `send_client_email_endpoint`, `internal_agent.py:2521`) grava `InteractionLedger`, mas sem estados, sem aprovação, sem vínculo com ticket/contrato.
- `TicketStatus` não tem `aguardando_cliente`; `TicketTimeEntry.admin_user_id` obrigatório (agente não aponta horas).
- API interna (`require_agent_token`) usa **um único token, o mesmo da Lara** → se a aprovação usar esse token, a Lara poderia se autoaprovar.
- Schema por `create_all` + SQL manual em `backend/scripts/migrations/*.sql` (sem Alembic): coluna nova em tabela existente exige script SQL.

---

## Workstream Darckware (`/root/project/darckware/backend`)

### D1. Modelo de dados (`app/db/models.py` + `scripts/migrations/2026100X_client_ops.sql`)
- **`outbound_emails`** (nova): `status` (`rascunho → aguardando_aprovacao → aprovado → enviando → enviado | falhou | envio_incerto`, + `rejeitado`, `cancelado`), `kind` (`pendencia`, `solucao`, `servico_realizado`, `informe_mensal`, `boas_vindas`, `resposta_inbound`, `outro`), `to_email`, `cc`, `subject`, `body_text`, `version`, `body_hash`, `sender_alias` (default `comercial`), vínculos `client_account_id`/`lead_id`/`demand_id`/`ticket_id`/`contract_id`, `source_system` (`forgehub`/`lara`/`darckware`), `source_ref`, `created_by`, `approved_by`, `approved_at`, `approved_hash`, `sent_at`, `smtp_message_id`, `error`.
- **`client_conversion_proposals`** (nova): `lead_id`, `proposed_by`, `payload` (empresa, contato, tipo de contrato sugerido), `status` (`proposta`/`aprovada`/`rejeitada`), `decided_by/at`, `client_account_id` resultante.
- **`leads`**: `client_account_id` (FK nullable), `converted_at`.
- **`client_contracts`**: `contract_type` (`suporte_horas`/`desenvolvimento`), `status` (`ativo`/`suspenso`/`encerrado`), `start_date`, `end_date`, `total_value`, `scope_summary`, `document_url`; campos de franquia passam a nullable para `desenvolvimento`. Permitir N contratos por cliente; `core/contract_calc.py` passa a usar o contrato `suporte_horas` ativo.
- **`ticket_status`**: `ALTER TYPE ... ADD VALUE 'aguardando_cliente'` (enum nativo).
- **`ticket_time_entries`**: `admin_user_id` nullable + `recorded_by` (string) — para apontamento por agente/ForgeHub (Onda 4).

### D2. API interna (`app/api/routes/internal_agent.py`, novos módulos se crescer)
- **Credencial separada de aprovação**: `DARCKWARE_APPROVER_TOKEN` (novo em `core/config.py` + `core/agent_auth.py: require_approver_token`), entregue **só ao ForgeHub**, nunca ao MCP da Lara. Aprovar/rejeitar e-mail, aprovar conversão e lançar contrato exigem esse token.
- **Tickets** (hoje só `/tickets/status`): `GET /tickets` (filtros cliente/tipo/status), `GET /tickets/{id}`, `POST /tickets`, `PATCH /tickets/{id}` (status, resolução), `POST /tickets/{id}/comments`, `POST /tickets/{id}/time-entries`. Reaproveitar a lógica de `admin_tickets.py`/`admin_contracts.py` (extrair para `core/`/serviço, sem duplicar).
- **Demandas**: as rotas `/demands*` já existem — só expor o que faltar (filtro por cliente).
- **Clientes**: `GET /clients/{id}/summary` (contatos autorizados, contratos, abertos, saldo de horas).
- **Contratos**: `GET/POST/PATCH /clients/{id}/contracts` (approver token para escrita).
- **Conversão**: `POST /leads/{id}/conversion-proposals` (Lara); `GET /conversion-proposals`; `POST /conversion-proposals/{id}:approve` (approver) — **numa transação**: cria `ClientAccount` + `ClientContact` primário autorizado, liga `lead.client_account_id`, cria contrato, cria rascunho `boas_vindas` (convite ao portal); `:reject`.
- **E-mails**: `POST /emails` (rascunho/aguardando), `GET /emails?status=&client=`, `GET /emails/{id}` (+ `preview_html`), `PATCH /emails/{id}` (edita → `version+1`, zera aprovação), `:approve {version, body_hash}` / `:reject {reason}` (approver), `:cancel`.
- **Guarda de destinatário**: `to_email` precisa ser `ClientContact.is_authorized` do cliente, solicitante da demanda/ticket, ou e-mail do lead (só `boas_vindas`/comercial). Senão 422.

### D3. Envio (`app/services/outbound_sender.py`, loop no `lifespan` como o `email_watcher`)
- Envia só `aprovado` cujo `body_hash == approved_hash`, sempre `sender_alias=comercial` (Lara), via `core/email.py: send_email` + layout de `core/verification.py` (spec omnichannel).
- Grava `InteractionLedger` + `ClientDemandEvent`/`TicketComment` (reusar o bloco de `send_client_email_endpoint`); timeout após o comando → `envio_incerto`, sem retry automático.
- `send_email`/`send_client_email` do MCP e o endpoint direto passam a **criar item `aguardando_aprovacao`** em vez de enviar (exceto códigos de verificação e autorização de contato, que continuam diretos).

### D4. Lara (perfil Hermes + docs)
- MCP `mcp/server.py`: `propose_client_conversion`, `draft_client_email`; resposta a e-mail de entrada (triagem) entra na mesma fila como `resposta_inbound`.
- `SOUL.md` da Lara (`/root/.hermes/profiles/lara/`, via skill `hermes-ecosystem-repair`): aprovação passa a ser a ação no ForgeHub (item + versão); Telegram só avisa; nunca reescreve texto aprovado.
- Docs: `docs/MATRIZ_AGENTES_E_EMAILS.md` (saída toda pela Lara), spec omnichannel (decisões 2 e 3 resolvidas), `docs/MANUAL_OPERACIONAL_LARA_MCP.md`, `docs/CONTROLE_DE_DESENVOLVIMENTO.md` §3–6, nova spec/plano em `docs/superpowers/`.

---

## Workstream ForgeHub (`/root/project/forgehub`)

### F1. Cliente HTTP (`backend/app/core/darckware_client.py`)
- `httpx.AsyncClient` para `settings.DARCKWARE_API_URL` (default `http://darckware-backend:8020/api/internal/agent`; ambos no `foundation_network`), `DARCKWARE_AGENT_TOKEN` (leitura/escrita operacional) e `DARCKWARE_APPROVER_TOKEN` (aprovação) em `core/config.py`. Falha → 502 com mensagem clara; nada é cacheado como verdade.

### F2. Domínio proxy `client_ops` (como `foundation.py`/`system_control.py`: sem tabela própria)
- `api/routes/client_ops.py` (`/api/v1/client-ops/...`) + `api/schemas/client_ops.py`: clientes, tickets/demandas (visão unificada com `kind=ticket|demand`, `tipo=desenvolvimento|servico`), contratos, conversões, e-mails.
- Todas `get_current_admin`; toda mutação grava `AuditEvent(entity_type="darckware_<obj>", entity_id=<uuid darckware>, actor=usuário)`.
- Ações compostas: **aguardando cliente** (status + rascunho `pendencia`), **dar baixa** (resolução + horas + rascunho `solucao`/`servico_realizado`), **reabrir**.
- Loop de aviso `_client_ops_poll_loop` (2 min, tarefa própria em `main.py`, padrão dos loops existentes): `Notification` deduplicada por `event_key` para ticket/demanda nova, e-mail aguardando aprovação, proposta de conversão.

### F3. Vínculo com a Software Factory (Onda 3)
- Alembic (schema `company`, encadeado **depois** das migrations pendentes do Codex): `products.darckware_client_id` + `darckware_client_name` (snapshot); `projects.darckware_client_id`, `darckware_origin_type` (`ticket`/`demand`), `darckware_origin_id`. Sem FK (bancos diferentes) — padrão `(entity_type, entity_id)` já usado em `governance.Approval`.
- Projeto herda o cliente do produto quando não informado. Planejamento/Task herdam pela cadeia Projeto → PlanningItem → Task (sem coluna nova).
- Ação "Criar projeto a partir da demanda" reutiliza a lógica de `POST /products`/`POST /projects` (regra 6.1.3).
- `factory.py` cockpit: campo cliente na árvore + filtro.

### F4. Telas (frontend, nova seção **"Clientes"** em `navSections.ts`)
- **Demandas** (`pages/client-demands/`): lista unificada por cliente/tipo/status/prioridade, nova demanda (grava na Darckware), ações aguardando cliente / dar baixa / reabrir / criar projeto.
- **Aprovação de e-mails** (`pages/client-emails/`): fila `aguardando_aprovacao`, preview HTML, editar (nova versão), aprovar/rejeitar, aprovar selecionados.
- **Clientes** (`pages/clients/` + `[id].tsx`): abas Demandas, Contratos, Projetos, E-mails, Informes; **conversões propostas** pela Lara com formulário de contrato.
- Padrões obrigatórios: ViewModel hooks (§21, `hooks/use<Thing>ViewModel.ts`), `ConfirmDialog`, RHF+Zod, `PageHeader`, mobile 390px, i18n pt-BR/en/es; atualizar `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`.

### F5. Informe mensal (Onda 4)
- Darckware: `GET /clients/{id}/monthly-report?cycle=` (tickets/demandas abertos e fechados, horas x franquia via `contract_calc`).
- ForgeHub: cron por agente (padrão da memória: dono Athos, script no perfil, `hermes cron`, registrado no ForgeHub) chama `POST /api/v1/client-ops/reports:generate` → junta andamento dos projetos (fases do cockpit) → cria rascunho `informe_mensal` na fila → aprovação.

---

## Ondas (ordem de entrega)

1. **Destravar demandas e e-mails** — D1 (`outbound_emails`, `aguardando_cliente`), D2 (tickets, e-mails, approver token, guarda de destinatário), D3, D4 (Lara cria rascunhos); F1, F2, F4 Demandas + Aprovação de e-mails.
2. **Cliente e contrato** — D1 (leads, contratos, propostas), D2 (contratos, conversão); F4 Clientes + Conversões.
3. **Software Factory por cliente** — F3.
4. **Horas e informe** — D1 (`time_entries`), F5.

Restrições: ForgeHub tem implementação pendente do Codex (working tree sujo, 3 migrations não commitadas) — trabalhar em arquivos novos, encadear Alembic após as dele, sem deploy até pedido. Darckware também tem alterações não commitadas (CONTROLE, i18n) — não sobrescrever.

---

## Verificação

- **Darckware pytest** (novos `tests/test_outbound_emails.py`, `test_conversions.py`, `test_internal_agent_tickets.py`, `test_contracts_multi.py`): token da Lara **não** aprova (403); editar após aprovar invalida; sender não envia sem `approved_hash` igual; destinatário não autorizado → 422; conversão é atômica; `contract_calc` com N contratos; MCP `send_email` vira rascunho.
- **ForgeHub pytest** (`app/tests/test_client_ops.py`): `darckware_client` com `httpx.MockTransport`; AuditEvent em cada mutação; Notification deduplicada; Darckware fora → 502.
- **Vitest** dos ViewModels; `tsc -b`.
- **E2E manual** (dev.sh + darckware local): cadastrar cliente → contrato → ticket pelo ForgeHub → "aguardando cliente" → rascunho aparece → aprovar → e-mail chega numa caixa de teste do Marcelo → `InteractionLedger`/timeline do ticket na Darckware; repetir com edição pós-aprovação (não envia); telas em 390px e 1440px.


---

## Progresso

**2026-10-04 — Onda 1 implementada (sem deploy, sem commit):**
- Darckware: `outbound_emails` + `TicketStatus.aguardando_cliente` (`scripts/migrations/20261004_client_ops.sql`), `require_approver_token`, `services/outbound_email.py` (fila, guarda de destinatário, envio só com hash aprovado, sem retry), rotas `internal_client_ops.py` (`/outbound-emails*`, `/tickets*`, `/api/internal/approver/*`), `/emails/send` passou a enfileirar, MCP da Lara atualizado, vocabulário do portal/admin com o status novo. Correção: `ClientAccount.archived_at` faltava no modelo (`GET /clients` dava 500 em produção).
- ForgeHub: `core/darckware_client.py`, `api/routes/client_ops.py`, loop de avisos, telas `/client-demands` e `/client-emails` (ViewModels §21, pt-BR/en/es, 390px/1440px verificados).
- Pendente para ativar: aplicar o SQL na Darckware, gerar `DARCKWARE_APPROVER_TOKEN` e configurar `DARCKWARE_*` no `.env` do ForgeHub, deploy dos dois. D4 (SOUL.md da Lara, docs da Darckware) ainda não feito.

**2026-10-04 — Onda 2 implementada (sem deploy):**
- Darckware: `client_contracts` com N contratos (`contract_type`, `status`, datas, valor, escopo; índice único parcial = um suporte ativo), `leads.client_account_id`/`converted_at`, `client_conversion_proposals` (`scripts/migrations/20261005_client_contracts_conversion.sql`); `services/client_conversion.py` (aprovação atômica: conta + contato + contrato + vínculo + rascunho de boas-vindas), rotas `/clients/{id}/summary|contracts`, `/leads/{id}/conversion-proposals`, `/conversion-proposals*` e as de aprovação; MCP `propose_client_conversion`. Admin e portal continuam lendo só o contrato de suporte.
- ForgeHub: rotas de contratos/conversões/leads em `client_ops.py`, aviso de proposta no sino, telas `/client-accounts` e `/client-accounts/:id`.
- Para ativar: aplicar `20261005_client_contracts_conversion.sql` (depois do `20261004`) e o mesmo deploy da Onda 1.

**2026-10-04 — Onda 3 implementada (sem deploy):**
- ForgeHub: colunas de cliente em `products`/`projects` (migration `d7a3c91e5f20`, já aplicada no banco — só colunas anuláveis), herança do cliente do produto no `POST /projects`, `:create-project` a partir de chamado/demanda (idempotente, exige cliente), vínculo de produto existente ao cliente, seção Software Factory na ficha do cliente, cliente e filtro no Cockpit.
- Darckware: nenhuma mudança nesta onda.
