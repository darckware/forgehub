# Pendências — Nexo, Headscale e Darckware

> **Atualizado em:** 2026-09-14
> **Escopo:** acompanhamento da entrega descrita em
> [`architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md`](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md).

Este é o registro central do estado da entrega. Ele não substitui especificações nem planos: um item
só migra para **Concluído** quando existe código e evidência verificável.

## Fronteira entre os sistemas

- **Darckware** será a fonte canônica do cadastro do cliente e abriga site, CRM, área administrativa
  e área do cliente.
- **ForgeHub** gerencia a operação de projetos, serviços e desenvolvimento, além de estações e
  instalações Nexo. Essas entidades devem se associar ao cliente por uma referência estável do
  Darckware, sem recriar um segundo cadastro mestre. Quando necessário, o ForgeHub poderá manter
  apenas uma projeção de exibição, sincronizada e somente leitura.
- **ForgeRouter** permanece como proxy de LLMs e não é alterado por esta entrega.

A migração do cadastro atual e o vínculo externo ainda **não estão implementados**. A integração deve
continuar por API server-to-server; acoplamento direto entre bancos permanece fora do escopo.

## Concluído

### Fundação de monitoramento Nexo

- Domínio `Client`, `Workstation` e `Irregularity`, com migrations no schema `company`.
- Emissão/revogação do token, ingestão autenticada, regras de irregularidade e detecção de estações
  sem comunicação.
- APIs e telas internas de clientes, estações e irregularidades.

Referências: [plano da fundação](superpowers/plans/2026-09-06-nexo-client-monitoring-foundation-implementation.md),
commit integrado `1e19a07` e migration `e9ae96a2c664`.

### Administração de rede Nexo

- Concessão/revogação auditável de comunicação entre estações do mesmo cliente.
- Política Headscale determinística, publicação pelo host bridge e rollback em falha.
- APIs, hooks e telas administrativas.

Referências: [plano de administração de rede](superpowers/plans/2026-09-06-nexo-network-administration-implementation.md)
e migration `40e6bb284f7b`.

## Integrado — validação operacional pendente

### Instalador, distribuição e monitoramento da instalação

Implementação de `feature/nexo-installer-monitoring` integrada em `develop` pelo merge `ec81c3f`,
incluindo a revisão funcional `27679d9` e a documentação `be1a98d`. A verificação de 14/09 abaixo
foi executada no checkout integrado; build real, instalação e deploy continuam pendentes.

- Builds Linux e Windows catalogadas por revisão Git e plataforma, com artefatos persistentes e
  verificação de tamanho/SHA-256.
- Fronteira allowlisted no host bridge, sem comando, ref ou caminho arbitrário enviado pelo browser.
- ZIP temporário por estação com binário, `agent.yaml`, instalador, manifesto e instruções; o token
  em claro existe somente dentro do pacote e é substituído a cada nova geração.
- Estados atuais e histórico imutável de instalação, promovendo para `online` apenas após relatório
  autenticado da geração vigente.
- Área `/nexo-agents` e ações contextuais na página do cliente, com textos em inglês, português e
  espanhol.

Referências: [especificação](superpowers/specs/2026-09-08-nexo-installer-monitoring-design.md),
[plano](superpowers/plans/2026-09-08-nexo-installer-monitoring-implementation.md) e
[runbook operacional](runbooks/NEXO_AGENT_PACKAGES.md).

## Pendente — funcional

### Relatórios

Ainda é necessário definir formato e tecnologia, gerar relatórios mensais e sob demanda, armazenar e
revisar os documentos e expor leitura com isolamento correto por cliente.

Referência: [seção 7 da especificação](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md#7-report-generation).

### Identidade canônica e integração Darckware

Falta especificar e implementar:

- uma chave externa estável e única que associe projetos, serviços, desenvolvimento, estações e
  instalações do ForgeHub ao cliente canônico do Darckware;
- migração/deduplicação idempotente dos clientes já existentes, sem criar registros mestres iguais
  nos dois bancos;
- regras de unicidade, reconciliação, desativação e tratamento de vínculo ausente ou conflitante;
- projeção local opcional, sincronizada e somente leitura, limitada aos campos necessários à
  operação e exibição;
- API server-to-server client-scoped para irregularidades e relatórios, com credencial mínima,
  isolamento entre tenants e `404` para recursos de outro cliente;
- consumo dessa API pela área autenticada `/cliente/` do Darckware.

Não se deve introduzir foreign key entre bancos, leitura direta do banco Darckware pelo ForgeHub nem
um segundo fluxo de cadastro mestre no ForgeHub.

Referência: [seção 8 da especificação](architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md#8-client-facing-display-lives-in-the-darckware-sites-existing-client-area-not-here).

## Pendente — operacional

### Sincronização Git

O estado da branch e do remoto deve ser verificado novamente antes da integração. Este documento não
autoriza merge, rebase ou push.

### Validação com Headscale real

Os testes automatizados isolam o host bridge. Ainda falta validar, em ambiente autorizado, tags,
publicação/leitura de política, concessão/revogação, tráfego efetivo e rollback contra Headscale real.

### Deploy, migrations e smoke test real

A migration Nexo `5a8c1e7d9f20` está aplicada no banco local de testes, mas isso não prova o estado do
ambiente-alvo. Antes da implantação ainda é necessário reconciliar Git, comparar `alembic current`
com `alembic heads`, aplicar migrations pelo processo autorizado, construir/implantar a revisão e
executar health checks e smoke tests autenticados.

### Build real pelo host bridge

O contrato de build foi validado com bridge e artefatos sintéticos. Ainda falta executar e registrar
uma build Linux/Windows contra o repositório Nexo real e o host bridge implantado, confirmando
permissões e retenção em `/root/forgehub-data/nexo-agent-artifacts`.

Na inspeção de 14/09, `/root/project/nexo` estava em `c874e3d` com alterações locais em código,
testes e documentação. O catálogo exige checkout limpo em `inspect_source()`; essas alterações
precisam ser reconciliadas antes da build catalogada. Não foram descartadas nem incluídas em um
commit por esta verificação. O compilador `go` também não estava no `PATH` desta sessão;
há um toolchain em `/tmp/nexo-go-toolchain`, cuja existência não comprova a configuração do serviço.

## Pendências técnicas resolvidas e integradas

### Verificação sintética integrada do ciclo completo

O teste `test_synthetic_build_package_and_authenticated_report_flow`, incluído em `27679d9`,
solicita builds Linux/Windows, gera e inspeciona os dois ZIPs e usa o token do pacote Linux para
comprovar a transição para `online` e o histórico. A instalação Windows permanece `downloaded`;
o teste não comprova execução do agente Windows. Os registros descartáveis são removidos em
`finally`. Bridge e binários são sintéticos; a validação real continua pendente.

### Persistência de falha de empacotamento

A revisão `27679d9` registra `error`, `last_error` e evento auditável quando não existe geração
utilizável. Se há uma geração utilizável, preserva seu estado, build, datas e token e acrescenta
somente o diagnóstico e evento de falha. Mensagens persistidas e respostas de erro de domínio são
genéricas, sem token ou caminho privado. Ambos os cenários têm testes de regressão.

## Evidências verificadas em 2026-09-14

Checkout integrado `develop`, revisão de código `ec81c3f`. Testes backend executados com
`source /tmp/forgehub-pending-test-env`, apontando para o PostgreSQL dedicado de testes:

- `/tmp/forgehub-pending-venv/bin/python -m pytest app/tests/test_nexo_build_routes.py app/tests/test_nexo_package_routes.py app/tests/test_nexo_package_e2e.py app/tests/test_nexo_report_reconciliation.py app/tests/test_nexo_installation_models.py app/tests/test_nexo_installation_routes.py -q --tb=short -x`: **42 aprovados em 9,06 s**.
- `/tmp/forgehub-pending-venv/bin/python -m pytest app/tests/test_nexo_host_builds.py -q --tb=short -x`: **13 aprovados em 0,19 s**.
- `/tmp/forgehub-pending-venv/bin/ruff check app`: **aprovado**.
- `npm test -- --run src/pages/nexo-agents/index.test.tsx src/pages/clients/index.test.tsx src/lib/api.test.ts src/components/ui/confirm-dialog.test.tsx src/components/layout/navSections.test.tsx`: **44 aprovados em 5 arquivos**, com avisos conhecidos do React Router.
- `npm run build`: **aprovado**, 5.255 módulos transformados, etapa Vite em 40,10 s; avisos de chunks grandes e import estático/dinâmico do Mermaid permanecem.

Esses testes usam bridge/artefatos simulados. Não comprovam build real do agente, instalação em
estação, política Headscale real ou atualização dos serviços ativos.
Consulta Docker mostrou containers `forgehub-backend` e `forgehub-frontend` criados em 08/09,
ambos com tag `latest`; não houve deploy nesta verificação.

## Evidências verificadas em 2026-09-13

Worktree `feature/nexo-installer-monitoring`, revisão `27679d9`:

- `POSTGRES_HOST=127.0.0.1 timeout 60s .venv/bin/python -m pytest app/tests/test_nexo_package_routes.py app/tests/test_nexo_package_e2e.py -q --tb=short`: **16 aprovados em 4,96 s**, com o `.env` raiz carregado.
- `.venv/bin/ruff check app/api/routes/nexo_installation.py app/tests/test_nexo_package_routes.py app/tests/test_nexo_package_e2e.py`: **aprovado**.
- A primeira tentativa no sandbox falhou antes dos testes por bloqueio de socket; a execução com
  acesso ao PostgreSQL local produziu o resultado acima.

Não foram reexecutados build frontend, migration ou validações contra infraestrutura real nesta
revisão. As evidências anteriores abaixo mantêm sua data e revisão originais.

## Evidências verificadas em 2026-09-10

Na revisão `7d653d1` antes desta atualização documental:

- `alembic current`: `5a8c1e7d9f20 (head)`;
- suíte backend relevante: **61 testes aprovados** em 12,59 s;
- Ruff em `backend/app`: **todos os checks aprovados**;
- suíte frontend focada: **40 testes aprovados** em 4 arquivos; permaneceram somente dois avisos já
  conhecidos de flags futuras do React Router;
- build de produção: **concluído**, 5.238 módulos transformados em 49,03 s; permaneceram avisos de
  chunk grande e import misto do Mermaid;
- seleção de cinco testes sintéticos independentes (catálogo das duas plataformas, ZIP Linux/Windows,
  rotação e primeiro relatório): **5 testes aprovados** em 4,99 s, com fixtures isoladas e limpeza
  automática de cada teste.

Esse último resultado valida contratos isolados; não é uma execução E2E integrada nem uma validação
contra host bridge, repositório Nexo ou estações reais.

## Fora do escopo desta entrega

- Atualização remota, reinstalação, desinstalação ou execução de comandos nas estações.
- Editor de política HuJSON bruta e validação com Headscale real.
- Geração de relatórios/PDF e implementação da interface `/cliente/` do Darckware.
- Migração do cadastro mestre de clientes para Darckware.
- Conexão direta entre os bancos ForgeHub e Darckware ou acesso do navegador do cliente diretamente
  ao ForgeHub.
- Mudanças no ForgeRouter.

## Critério para atualização

Ao concluir uma pendência, mover o item para **Concluído** e anexar revisão/commit, migration quando
aplicável, comando e resultado dos testes e evidência de deploy/smoke test quando afetar runtime.
