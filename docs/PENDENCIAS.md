# Pendências — Nexo, Headscale e Darckware

> **Atualizado em:** 2026-09-13  
> **Escopo:** acompanhamento da entrega descrita em
> [`architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md`](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md).

Este documento é o registro central do estado dessa entrega. Ele não substitui a especificação nem
os planos de implementação: resume o que está concluído, o que ainda exige trabalho e o que pertence
a outro projeto ou fase. Um item só deve migrar para **Concluído** quando houver código integrado e
evidência verificável; existência em uma especificação ou plano não prova implementação.

## Concluído

### Fundação de monitoramento Nexo

- Domínio `Client`, `Workstation` e `Irregularity`, incluindo migrations no schema `company`.
- Ciclo de emissão e revogação do token do dispositivo.
- Ingestão autenticada dos relatórios do Nexo Remote Agent e avaliação das regras de irregularidade.
- Detecção de estações sem comunicação (`agent_unreachable`).
- APIs e telas internas de clientes, estações e irregularidades.

Referências:

- Plano: [`superpowers/plans/2026-09-06-nexo-client-monitoring-foundation-implementation.md`](superpowers/plans/2026-09-06-nexo-client-monitoring-foundation-implementation.md).
- Integração na branch `develop`: commit `1e19a07`.
- Migration principal: `backend/alembic/versions/e9ae96a2c664_add_client_workstation_irregularity.py`.

### Administração de rede Nexo

- Modelo auditável de concessão e revogação de comunicação entre estações do mesmo cliente.
- Renderização determinística da política Headscale com negação por padrão.
- Adapter de publicação pelo host bridge, sincronização do ciclo de vida do cliente e rollback da
  alteração de banco quando a publicação da política falha.
- APIs, hooks e telas de administração de clientes e pares de estações.

Referências:

- Plano: [`superpowers/plans/2026-09-06-nexo-network-administration-implementation.md`](superpowers/plans/2026-09-06-nexo-network-administration-implementation.md).
- Commits principais: `e1b73e1`, `8b2ac33`, `4081499`, `d248b6c`, `b879dff` e `26b5eb3`.
- Migration: `backend/alembic/versions/40e6bb284f7b_add_workstation_peer_grants.py`.

## Pendente — funcional

### Instalador e distribuição do Nexo Remote Agent

Existe especificação e plano, e a implementação está na branch `feature/nexo-installer-monitoring`
(revisão `27679d9`, worktree `.worktrees/nexo-installer-monitoring`). Ela ainda não está integrada
em `develop`, por isso a entrega permanece pendente nesta branch.

A implementação inclui builds Linux/Windows por revisão Git, artefatos verificados por SHA-256,
ZIP por estação com `agent.yaml`, rotação de token, histórico de instalação e registro seguro de
falhas. Em 2026-09-13 foram reexecutados no worktree:

- `POSTGRES_HOST=127.0.0.1 timeout 60s .venv/bin/python -m pytest app/tests/test_nexo_package_routes.py app/tests/test_nexo_package_e2e.py -q --tb=short`: **16 testes aprovados em 4,96 s**, carregando o `.env` raiz;
- `.venv/bin/ruff check app/api/routes/nexo_installation.py app/tests/test_nexo_package_routes.py app/tests/test_nexo_package_e2e.py`: **aprovado**.

O teste integrado gera e inspeciona os ZIPs das duas plataformas e confirma `online` por relatório
Linux autenticado com o token do pacote; Windows é verificado até `downloaded`. Bridge e binários
são sintéticos. Permanecem integração da branch, builds reais, instalação nas duas plataformas,
validação de permissões/retenção e deploy.

Referências: [especificação](superpowers/specs/2026-09-08-nexo-installer-monitoring-design.md) e
[plano](superpowers/plans/2026-09-08-nexo-installer-monitoring-implementation.md).

### Relatórios

Ainda não há plano de implementação nem biblioteca de geração de documento escolhida para a seção 7.
Falta:

- definir o formato e a tecnologia de geração do documento;
- gerar o relatório mensal por cliente;
- gerar relatório sob demanda por ocorrência ou intervalo;
- armazenar os relatórios e permitir revisão antes do envio;
- expor os relatórios por uma API somente leitura e restrita ao cliente correto.

Referência: [seção 7 da especificação](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md#7-report-generation).

### Integração com a área do cliente Darckware

O ForgeHub ainda precisa expor a API client-scoped prevista para irregularidades e relatórios. O
projeto Darckware precisa de uma especificação própria para:

- vincular uma conta/empresa Darckware ao `Client` correspondente no ForgeHub;
- consumir a API com credencial de serviço de escopo mínimo;
- exibir irregularidades e relatórios na área autenticada `/cliente/`;
- preservar isolamento entre clientes, inclusive retornando `404` para recursos de outro tenant.

Referência: [seção 8 da especificação](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md#8-client-facing-display-lives-in-the-darckware-sites-existing-client-area-not-here).

## Pendente — operacional

### Sincronização Git

Na verificação local de 2026-09-13, `develop` está **27 commits à frente e 1 commit atrás** da
referência local `origin/develop` (`git rev-list --left-right --count develop...origin/develop`).
Não houve fetch; esse resultado não comprova o estado atual do servidor remoto. É necessário reconciliar o commit remoto, preservar as alterações locais e somente
então publicar a revisão integrada. Não há autorização implícita neste documento para merge, rebase
ou push.

### Validação com Headscale real

Os testes automatizados isolam o host bridge e não validam uma instância Headscale real. Falta
executar, em ambiente autorizado:

- provisionamento de tag de cliente;
- publicação e leitura da política real;
- concessão, revogação e nova concessão entre duas estações registradas;
- confirmação efetiva do tráfego permitido/bloqueado;
- verificação dos registros de auditoria e do comportamento de rollback.

O próprio plano registra que o host usado na implementação não possuía um binário Headscale acessível
para esse teste.

### Migrations e deploy

As migrations `e9ae96a2c664` e `40e6bb284f7b` existem no repositório, mas esta revisão documental não
comprovou que o banco do ambiente-alvo está em `head` nem que a revisão atual está implantada. Falta:

1. reconciliar a branch com o remoto;
2. comparar `alembic current` com `alembic heads` no ambiente-alvo;
3. aplicar as migrations pendentes pelo processo autorizado;
4. construir e implantar a revisão identificada;
5. executar health checks e smoke tests autenticados das telas e APIs de clientes, irregularidades e
   administração de rede;
6. registrar revisão implantada, resultado e estratégia de rollback.

## Evidências automatizadas disponíveis

Os seguintes testes estão versionados e cobrem a entrega concluída:

- `backend/app/tests/test_client.py`
- `backend/app/tests/test_client_routes.py`
- `backend/app/tests/test_workstation_routes.py`
- `backend/app/tests/test_agent_report_ingestion.py`
- `backend/app/tests/test_workstation_staleness.py`
- `backend/app/tests/test_irregularity_routes.py`
- `backend/app/tests/test_workstation_peer_grant.py`
- `backend/app/tests/test_headscale_client.py`
- `backend/app/tests/test_peer_grant_routes.py`
- `frontend/src/pages/clients/index.test.tsx`

O commit `870e44a` registra a revisão final da fundação de monitoramento, incluindo correções de
deduplicação, atualização de irregularidades, detecção de estações que nunca reportaram, validações de
rota e limpeza dos dados criados pelos testes.

Na tentativa de reexecutar a suíte focada em 2026-09-08, os testes não foram iniciados porque o
`backend/.venv/bin/python` aponta para um interpretador indisponível no contexto de execução. Portanto,
este documento não afirma uma nova passagem da suíte nessa data. A próxima validação deve registrar o
comando, a revisão Git, o total de testes aprovados e eventuais falhas.

## Fora do escopo desta entrega

- Rotação ou expiração automática de tokens de dispositivo.
- Editor de política HuJSON bruta do Headscale.
- Reconciliação de franquia de horas entre `Client.support_plan` e os contratos do Darckware.
- Implementação da interface `/cliente/` no repositório ForgeHub; ela pertence ao projeto Darckware.
- Conexão direta entre os bancos ForgeHub e Darckware ou acesso do navegador do cliente diretamente ao
  ForgeHub.

Referência: [seção 9 da especificação](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md#9-explicitly-deferred-not-part-of-this-spec).

## Critério para atualização

Ao concluir uma pendência, mover o item para **Concluído** e anexar:

- revisão ou commit integrado;
- migration aplicada, quando houver;
- comando e resultado dos testes;
- evidência de deploy/smoke test, quando o item afetar runtime;
- referência à especificação ou ao plano executado.
