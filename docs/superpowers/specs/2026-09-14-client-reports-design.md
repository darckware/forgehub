# Relatórios revisados de acompanhamento

Complemento executável da seção 7 de `docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md`
e do plano de finalização confirmado pelo usuário em 14/09.

## Escopo e decisões

O ForgeHub gera e persiste documentos HTML autocontidos a partir de Client, Workstation e
Irregularity. O HTML é um snapshot imutável: mudanças posteriores nas irregularidades não alteram
um documento já gerado. O administrador pode revisar ou retirar a revisão, com auditoria. Não há
envio automático. As seções são resumo, estações, ocorrências, alterações observáveis, riscos,
pendências e horas/saldo. Para atendimentos e horas não representados no domínio, declarar
"Dados de atendimentos e horas não disponíveis nesta fonte"; nunca interpretar ausência como zero.

Não adicionar biblioteca PDF: HTML pode ser baixado e impresso. Usar escape de todos os campos
dinâmicos, sem scripts, recursos externos ou HTML fornecido por usuários. CSS estático pode melhorar
impressão. Downloads usam Content-Disposition attachment, nosniff e cache privado sem armazenamento.

## Persistência

`ClientReport` segue UUID/TimestampMixin no schema company. Campos: client_id (FK RESTRICT para
preservar documentos), kind (`monthly`/`on_demand`), period_start e period_end (Date, intervalo
inclusivo na interface), irregularity_id opcional (SET NULL), snapshot JSONB, html_content Text,
generated_at, generated_by_user_id opcional, reviewed_at e reviewed_by_user_id opcionais.
`period_end >= period_start`; mensal exige primeiro e último dia do mesmo mês, garantido pela
rotina de geração. Índice parcial UNIQUE(client_id, period_start) WHERE kind = 'monthly' garante
idempotência inclusive sob concorrência. Snapshots não são atualizáveis por API.

Snapshot inclui identificação de exibição do cliente, estações e irregularidades cujo intervalo
de atividade sobrepõe o período: detected_at < começo do dia seguinte a period_end e
(resolved_at é NULL ou resolved_at >= começo de period_start), sempre restrito ao cliente.
Datas são normalizadas em UTC. Relatório por ocorrência exige irregularity_id do próprio cliente
e filtra essa ocorrência. Inventário é explicitamente "estado observado na geração", pois não há
histórico completo para reconstruir inventário passado.

## Geração e revisão internas

Todas as novas rotas internas requerem administrador ativo, inclusive leitura/download.

- GET /api/v1/clients/{client_id}/reports: metadados, mais recentes primeiro.
- POST /api/v1/clients/{client_id}/reports: `{period_start, period_end, irregularity_id?}` gera
  on_demand. Intervalo inválido retorna 422; cliente/ocorrência alheia ou ausente retorna 404.
- GET /api/v1/client-reports/{report_id}: metadados e snapshot para revisão.
- GET /api/v1/client-reports/{report_id}/download: HTML persistido como anexo.
- PATCH /api/v1/client-reports/{report_id}/review: `{reviewed: boolean}`. Repetir o mesmo estado
  é idempotente. Aprovação guarda usuário/data; retirada limpa ambos e revoga acesso externo.
- POST /api/v1/clients/{client_id}/reports/monthly: `{month: "YYYY-MM"}` gera/retorna a única
  versão mensal. Apenas meses encerrados (UTC); mês atual/futuro retorna 422.

Auditoria registra geração/revisão/retirada com IDs e período, sem documento inteiro ou credenciais.
Um poll loop horário gera o mês UTC anterior para cada cliente, limitando-se a clientes existentes
antes do final daquele mês. Não inventar relatórios históricos anteriores ao início da implantação;
o botão mensal permite backfill explícito. Cada cliente tem transação independente; falha de um
não impede os outros. A unicidade no banco resolve múltiplos workers.

## API server-to-server de leitura

`ClientReadCredential`: UUID/TimestampMixin, client_id CASCADE, token_hash SHA-256 único,
expires_at opcional, revoked_at opcional, created_by_user_id. Prefixo `clr_` e 32 bytes aleatórios.
POST /api/v1/clients/{client_id}/read-credentials retorna segredo somente na criação;
GET lista metadados sem hash; DELETE /api/v1/clients/{client_id}/read-credentials/{id} revoga.
Todas essas operações exigem admin e geram auditoria sem segredo. Expiração passada é rejeitada.

Rotas externas dedicadas, autenticadas apenas pela dependência da credencial de cliente:

- GET /api/v1/client-access/clients/{client_id}/reports: somente revisados.
- GET /api/v1/client-access/clients/{client_id}/reports/{report_id}/download: somente revisado,
  cliente da URL, documento e credencial precisam coincidir; qualquer recurso alheio retorna 404.
- GET /api/v1/client-access/clients/{client_id}/irregularities: projeção limitada a id,
  workstation_id, hostname, rule_key, severity, detail, status, detected_at, resolved_at.

JWT de usuário/agente não substitui essa credencial; `clr_` não autentica nenhuma rota interna.
A exceção no middleware global abrange somente esses paths e GET, deixando a dependência obrigatória
aplicar 401/404; nenhum prefixo genérico de cliente fica público. Token inválido/revogado/expirado
retorna 401. Listagens paginam com limit 1..100 (padrão 50) e offset >= 0. Eventos, notas internas
do cliente, contatos, hashes e tokens de estações nunca entram na API externa.

## Interface interna

Adicionar seção de relatórios na página existente do cliente. Exibir período, tipo, geração e
estado de revisão; formulário por intervalo e ação mensal por mês encerrado. Link por ocorrência
na tela de irregularidades pode abrir a página do cliente com ocorrência pré-selecionada.
Gerar, baixar, revisar e retirar revisão precisam de estados de carregamento/erro e prevenir
submissão dupla. Reutilizar componentes, idioma e permissões existentes; pt-BR/en/es.
Download autenticado via cliente API e Blob, sem token na URL. Revisão requer ler o documento
antes de confirmar; confirmar retirada informa que o acesso externo será removido.

## Integração Darckware (tarefa seguinte)

O consumidor vive no backend Darckware e deriva ClientAccount.id da sessão autenticada. Nunca aceita
cliente escolhido pelo navegador. A configuração server-side associa explicitamente esse UUID ao
client_id ForgeHub e à credencial clr_; nenhum match por nome/email. O navegador só chama Darckware.
O vínculo canônico e a migração do cadastro são tratados na tarefa de identidade, sem FK entre bancos.

## Verificação

Banco dedicado, fixtures únicas e limpeza de dependências. Cobrir: snapshot estável após mudanças;
HTML com texto hostil escapado; ausência de horas explícita; limite de datas e UTC; ocorrência de
outro cliente 404; geração mensal repetida e concorrente única; apenas admin nas rotas internas;
tokens emitidos uma vez, expiração e revogação; 404 cruzado com credencial válida; rascunho
invisível; retirada de revisão imediatamente inacessível; credencial externa recusada em rotas
internas; poll de dois clientes com uma falha isolada. Nenhum teste envia mensagens externas.
