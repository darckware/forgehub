# Relatórios de acompanhamento

## Fluxo do operador

Os relatórios reúnem dados registrados no ForgeHub. O documento HTML é preservado na geração;
alterações posteriores nas estações ou ocorrências não reescrevem relatórios anteriores.
O inventário representa o estado observado na geração. Não há cálculo de atendimentos, horas
consumidas ou saldo de contrato nesta fonte.

Na página do cliente, um administrador pode gerar um relatório por intervalo ou solicitar o
relatório de um mês encerrado. Datas de início e fim são inclusivas e interpretadas em UTC.
Uma ocorrência selecionada precisa pertencer ao mesmo cliente.

1. Gere o documento pelo intervalo desejado ou por mês encerrado.
2. Leia o documento antes de confirmar a revisão.
3. Baixe o HTML para arquivamento ou impressão pelo navegador.
4. Confirme a revisão para permitir leitura pela API externa vinculada àquele cliente.
5. Retire a revisão para impedir novas consultas externas ao documento.

Retirar a revisão ou revogar uma credencial não recolhe cópias já baixadas.
Não há envio automático de mensagens ou documentos.

## Contratos HTTP

Rotas internas exigem usuário administrador ativo e autenticação normal do ForgeHub.

| Operação | Método e rota | Corpo |
| --- | --- | --- |
| Listar | `GET /api/v1/clients/{client_id}/reports` | — |
| Gerar por intervalo | `POST /api/v1/clients/{client_id}/reports` | `period_start`, `period_end`, `irregularity_id` opcional |
| Gerar mensal | `POST /api/v1/clients/{client_id}/reports/monthly` | `month` no formato `YYYY-MM` |
| Consultar snapshot | `GET /api/v1/client-reports/{report_id}` | — |
| Baixar HTML | `GET /api/v1/client-reports/{report_id}/download` | — |
| Revisar ou retirar revisão | `PATCH /api/v1/client-reports/{report_id}/review` | `reviewed`: booleano |

O mensal retorna o mesmo documento para o mesmo cliente e mês, inclusive com solicitações
concorrentes. Gerações sob demanda são documentos separados. O processamento horário considera
apenas o mês UTC anterior e clientes criados antes do término daquele mês. Meses mais antigos
dependem de solicitação explícita; uma falha em um cliente não impede os demais.

## Credenciais de leitura

O administrador gerencia as credenciais em
`/api/v1/clients/{client_id}/read-credentials`: `POST` emite, `GET` lista metadados,
`DELETE /{credential_id}` revoga. A emissão admite `expires_at` opcional, no futuro.
O segredo `clr_` aparece somente na resposta de emissão; apenas seu hash é persistido.
Guarde-o no gerenciador de segredos do consumidor. Não coloque tokens em URLs, logs, capturas,
documentação ou variáveis de build do frontend.

O consumidor envia `Authorization: Bearer <credencial>` para:

- `GET /api/v1/client-access/clients/{client_id}/reports`
- `GET /api/v1/client-access/clients/{client_id}/reports/{report_id}/download`
- `GET /api/v1/client-access/clients/{client_id}/irregularities`

Listagens aceitam `limit` de 1 a 100 (padrão 50) e `offset` a partir de zero.
Relatórios sem revisão e recursos de outro cliente retornam `404`. Credencial inválida,
revogada ou expirada retorna `401`. JWTs de usuários/agentes não substituem a credencial externa;
esta credencial também não autoriza as rotas internas.

## Integração com Darckware

O consumidor Darckware ainda é uma entrega separada. Seu backend deve obter `ClientAccount.id`
da sessão autenticada e resolver uma associação explícita entre esse UUID, o UUID do cliente
ForgeHub e sua credencial de leitura. O navegador nunca escolhe essa associação nem recebe o token.
Não associar por nome/email nem acessar diretamente o banco do outro sistema.

Configuração necessária no consumidor: URL HTTPS do ForgeHub, associação de IDs e segredo por
cliente, timeout de requisições e tratamento de indisponibilidade sem mostrar dados de outra conta.
Esses itens descrevem requisitos; não são nomes de variáveis já implementadas no Darckware.

## Verificação e implantação

Execute testes apenas com o PostgreSQL dedicado indicado em `/tmp/forgehub-pending-test-env`.
Esse arquivo contém configuração privada e não deve ser impresso ou versionado.

Antes de implantação, confira a revisão Git e o head Alembic no ambiente-alvo, execute as
migrations pelo processo autorizado e verifique as rotas com dados de teste identificáveis.
Uma suíte local aprovada não comprova implantação nem integração com Darckware.

Evidências desta entrega são registradas em `docs/PENDENCIAS.md` após a verificação.
