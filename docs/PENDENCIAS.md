# Pendências — Nexo, Headscale e Darckware

> **Atualizado em:** 2026-09-10  
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

### Instalador, distribuição e monitoramento da instalação

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

## Evidências verificadas em 2026-09-10

Na revisão `7d653d1` antes desta atualização documental:

- `alembic current`: `5a8c1e7d9f20 (head)`;
- suíte backend relevante: **61 testes aprovados** em 12,59 s;
- Ruff em `backend/app`: **todos os checks aprovados**;
- suíte frontend focada: **40 testes aprovados** em 4 arquivos; permaneceram somente dois avisos já
  conhecidos de flags futuras do React Router;
- build de produção: **concluído**, 5.238 módulos transformados em 49,03 s; permaneceram avisos de
  chunk grande e import misto do Mermaid;
- fluxo sintético focado (catálogo das duas plataformas, ZIP Linux/Windows, rotação e primeiro
  relatório): **5 testes aprovados** em 4,99 s, com fixtures isoladas e limpeza automática.

Esse último resultado valida os contratos sintéticos, mas não equivale a uma execução única contra o
host bridge, repositório Nexo ou estações reais.

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
