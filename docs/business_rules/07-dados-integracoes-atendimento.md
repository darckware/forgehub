# 07 — Dados, integrações e atendimento

Base: `main` em `43a6a7f`. Esta área reúne regras de domínios operacionais distintos;
respeite a origem de verdade indicada e nunca presuma que uma tela de leitura define
as capacidades da API completa.

## Clientes e atendimento

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| DATA-001 | IMPLEMENTADA | Darckware é origem de verdade dos cadastros de clientes, contratos/tickets, demandas e emails de cliente; ForgeHub opera a integração sob permissão administrativa e audita mutações. Não reintroduza a cópia legada Nexo como fonte atual. | `backend/app/api/routes/client_ops.py`; migration `a9c4e7f2b1d6_drop_nexo_client_monitoring.py`; `backend/app/tests/test_client_ops.py` |
| DATA-002 | IMPLEMENTADA | Ticket/demanda são apresentados como work items com mapeamento explícito de status. Email para cliente é rascunho enfileirado para aprovação; ForgeHub não envia email diretamente. Enfileire antes da transição e cancele rascunho se a transição falhar. | `backend/app/api/routes/client_ops.py`; `backend/app/tests/test_client_ops.py:260,295` |
| DATA-003 | IMPLEMENTADA | Linha de serviço é catálogo administrado; tipo de projeto pode mapear para linha. Linha que tem projetos associados não pode ser desativada. | `backend/app/api/routes/service_line.py`; `backend/app/tests/test_service_line.py` |

## Dados pessoais e captura

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| DATA-004 | IMPLEMENTADA | Registros pessoais são acessados pelo principal pessoal e pelos estados permitidos do modelo; não os trate como registros compartilhados do projeto. | `backend/app/api/routes/personal.py`; `backend/app/db/models/personal.py` |
| DATA-005 | IMPLEMENTADA | Contato valida categoria/aniversário, normaliza telefone e impede duplicação. Exclusão é restrita à pessoa autorizada. Mensagem recebida pode alimentar contexto; saída e notas não entram como mensagens recebidas. | `backend/app/api/routes/personal_contacts.py`; `backend/app/tests/test_personal_contacts.py`; `test_personal_contacts_features.py` |
| DATA-006 | IMPLEMENTADA | Sugestão de captura só aceita ou descarta enquanto pendente. Aceite converte em demanda, tarefa ou nota e registra auditoria; captura em grupo usa fluxo próprio e mantém proveniência. | `backend/app/api/routes/personal_contacts.py`; `backend/app/tests/test_personal_groups.py`; `test_personal_contacts.py` |

## Documentos, banco e automação

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| DATA-007 | IMPLEMENTADA | API Foundation resolve caminhos dentro da raiz documental. Rotas de edição operam Markdown e podem criar documento/pastas permitidos; ativos binários usam fluxo próprio de upload/download/rename. Não confunda raiz documental com diretório de perfil de agente. | `backend/app/api/routes/foundation_docs.py`; `docs/screens/foundation.md`; sem teste dedicado localizado para gravação de documentos |
| DATA-008 | IMPLEMENTADA | Script de Foundation só é registrado se o arquivo existe no diretório `scripts/` do perfil e está referenciado em Markdown. Registro não deve apontar fora da raiz permitida. | `backend/app/api/routes/foundation_script.py`; `backend/app/tests/test_foundation_script.py` |
| DATA-009 | GAP | Endpoint de consulta do navegador de banco restringe verbos SQL a `SELECT`, `WITH` ou `EXPLAIN` e limita linhas; o router completo também oferece endpoints DDL para criar/remover tabelas, funções e índices. Não declare todo o módulo como read-only. | `backend/app/api/routes/database.py:90,462,588,742`; `docs/reference/DB_README.md` |
| DATA-010 | IMPLEMENTADA | Automação web e macro apontam a exatamente um Product ou StandaloneApp e guardam alvo, trigger, modo e resultado de teste. Macro apenas prepara o composer: envio exige ação explícita do usuário; não execute automaticamente. | `backend/app/db/models/web_automation.py`; `backend/app/api/routes/workspace_browser.py`; `backend/app/tests/test_workspace_browser.py` |
| DATA-011 | IMPLEMENTADA | Navegador autenticado compartilhado exige principal humano. Caminho de navegador de tarefa de agente é isolado, condicionado a feature switch e limites de host; não reaproveite sessão humana. | `backend/app/api/routes/workspace_browser.py`; `backend/app/tests/test_workspace_browser.py`; `backend/app/tests/test_task_browser.py` |

## Integrações e deploy

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| DATA-012 | IMPLEMENTADA | Entrada de servidor MCP exige exatamente um transporte (comando ou URL). Atribuir grava config no alvo; excluir item do catálogo não desinstala config existente. Excluir atribuição tenta remover a instalação remota. | `backend/app/api/routes/mcp_catalog.py`; `backend/app/tests/test_mcp_catalog.py` |
| DATA-013 | HISTÓRICA | Kanboard não é integração atual; migration removeu campos e registro de ferramentas. Não recrie dependência com base em texto histórico ou documento de tecnologia. | migration `1e22d064a986_remove_kanboard_integration.py`; `docs/reference/TECHNOLOGY.md` |
| DATA-014 | IMPLEMENTADA | Deploy mantém catálogo de instalações/grupos e sincroniza containers observados via bridge Docker. Excluir instalação suprime sua sincronização posterior; recriação explícita remove a supressão. Isso não equivale a publicar release completo de produto. | `backend/app/api/routes/deploy.py`; `backend/app/tests/test_deploy.py`; guia 03 DEL-016 |
| DATA-015 | GAP | Documento de tela Foundation afirma que gravação exige arquivo Markdown existente, mas PUT pode criar documento e pastas autorizadas. Corrija a documentação de tela antes de usá-la como requisito. Há outras páginas de tela de produto com descrição de endpoint obsoleta. | `backend/app/api/routes/foundation_docs.py:97`; `docs/screens/foundation.md`; `docs/screens/products.md` |

## Regras para agentes

- Identifique o sistema que é fonte de verdade antes de alterar dados; respeite
  escopo do principal, consentimento, validação, auditoria e política de envio.
- Leia a rota de mutação, seu modelo e testes; não deduza capacidade de escrita a
  partir de um endpoint de consulta nem deduza ausência de capacidade a partir da UI.
- Não reative integração histórica nem comportamento descrito como arquitetura-alvo
  sem confirmar decisão e código corrente.
- Ao mudar integração, documente comportamento quando o serviço está indisponível,
  idempotência, compensação, retry, auditoria e reconciliação de estado remoto.

## Referências

- [Modelo de dados](../reference/DATA_MODEL.md)
- [Topologia de bancos](../reference/DB_README.md)
- [Atendimento do cliente](../runbooks/CLIENT_REPORTS.md)
- [Organização de documentos Foundation](../screens/foundation.md)
- [Factory e entrega](../screens/products.md)
