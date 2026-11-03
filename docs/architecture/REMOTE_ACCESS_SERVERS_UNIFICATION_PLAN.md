# Unificação de Servidores e Acesso Remoto

Plano (2026-10-17, Marcelo: "preciso unificar as duas telas Acesso remoto e servidores").
Status: **concluído em 2026-10-17** (fases 0–6). Pendências operacionais no fim da Fase 5.

## Problema

Hoje há duas telas sobre a mesma tabela (`company.servers`), separadas só pelo `kind`:

| | Servidores (`/servers`) | Acesso Remoto (`/remote-access`) |
|---|---|---|
| Mostra | `kind="server"` | `kind="workstation"` (aba Máquinas) |
| Permissão | módulo `servers` | `adminOnly` (módulo `vpn`) |
| Agrupamento | VPS / SEMED (`environment`) | cliente Darckware, grupos (`host_groups`) |
| Configurar acesso | **Instalar chave**: gera e guarda no ForgeVault, instala a parte pública com senha de admin; sem chave privada local ou cópia no banco | **Preparar estação**: cria `darckware`, chave e senhas na ForgeVault (`ssh_key_ref`), desativa o admin |
| Extras | serviços publicados, importar CSV, verificar estado, liga/desliga acesso, cofre da chave | importar da Tailscale, prontidão, senhas (revelar/rotacionar), RustDesk |
| Scripts | — | aba Scripts e execuções (roda em qualquer máquina) |
| Rede | — | aba Rede (Tailscale da VPS, dispositivos, ACL, histórico) |

Consequências: o mesmo conceito ("uma máquina que o ForgeHub acessa por SSH") tem dois cadastros,
dois fluxos de chave e dois lugares de armazenamento da chave; a aba Rede repete a lista de
máquinas como "dispositivos" e não diz para que serve.

## Modelo proposto (revisão 2026-10-17, Marcelo)

Marcelo: "preciso ter uma visão das máquinas que têm a instalação do Tailscale, porque tenho em
máquinas do Tailscale a configuração de subnet ... a tela dos dispositivos do Tailscale é igual à
de máquinas com algumas particularidades ... deixar os computadores que não têm Tailscale
agrupados ou como filtro."

Uma lista só de **máquinas**, classificada pelo **caminho de acesso** a partir da VPS do ForgeHub:

| Caminho | O que é | Exemplos hoje |
|---|---|---|
| **Tailscale** | Tailscale instalado; acesso direto pelo IP 100.x | srv-sup, srv-app01 (100.124.97.54), gat-srv-01, estações GAT/SEMED |
| ↳ **Roteador de sub-rede** | Nó Tailscale que anuncia rotas (ex.: 172.15.0.0/16) | *nenhum aprovado hoje* (ver Diagnóstico) |
| **Via sub-rede** | Sem Tailscale; IP dentro de uma rota anunciada; acesso através do roteador | host-pve01/02, srv-ad03/04, srv-nas01/02, PFsense, srv-vm01, srv-app02/05 |
| **Sem caminho** | Sem Tailscale e fora de qualquer rota | 172.15.x.x enquanto não houver rota aprovada |
| *Não cadastrado* | Dispositivo da tailnet sem linha em `servers` (celular, notebook) | NotebookSTI, POCO F5 Pro, T3010D |

- A lista de **dispositivos** da aba Rede e a de **máquinas** viram a mesma tabela: um dispositivo
  da tailnet já cadastrado é uma linha só (casada por `tailnet_node_id`, depois por IP); um não
  cadastrado aparece com a ação "Cadastrar".
- Máquinas **via sub-rede** aparecem agrupadas sob o roteador que as alcança (ou como filtro
  "Sem Tailscale"), com o mesmo "Configurar acesso" (instalar chave SSH / preparar estação) —
  o SSH chega pelo IP da sub-rede, através do roteador.
- Filtros: caminho (Tailscale / roteadores / via sub-rede / sem caminho / não cadastrados),
  tipo (servidor/estação), cliente, estado.
- A aba **Rede Tailscale** fica só com diagnóstico: Tailscale da própria VPS (incluindo se aceita
  rotas), rotas anunciadas × aprovadas, política ACL e histórico.

## Diagnóstico (2026-10-17)

Lido na VPS (`tailscale status --json`, `ip route`, teste de porta 22):

- Nenhum peer tem `PrimaryRoutes`/sub-rede em `AllowedIPs`: **nenhuma rota de sub-rede aprovada**.
- A VPS está com `RouteAll=false` (não aceita rotas).
- 172.15.2.2, 172.15.5.98, 172.15.1.3: porta 22 **inalcançável** da VPS. 100.107.175.100 (srv-sup,
  via Tailscale): alcançável.
- Não há `ProxyJump` em `/root/.ssh/config` nem no código.

Marcelo confirma que acessa a sub-rede do próprio notebook (Tailscale instalado). A cópia da
política registrada no ForgeHub (2026-10-16) explica a diferença: a regra da SEMED cita "a sub-rede
física anunciada" 172.15.0.0/16 e `tag:darckware-admin`/`autogroup:admin` alcançam `*`, mas
`tag:darckware-infra` (a VPS) não tem grant para 172.15.0.0/16 — e a Tailscale só entrega a cada
nó as rotas que a ACL permite a ele. Por isso a rota não aparece na VPS. (Essa cópia está
desatualizada — também não libera a VPS para `tag:semed-srv`, e esse acesso funciona.)

Os servidores 172.15.x.x **não são alcançáveis pelo ForgeHub hoje**. Para o modelo funcionar,
fora do código:
1. Confirmar no painel (Machines › srv-sup › Subnets) que srv-sup anuncia **e** tem aprovada
   172.15.0.0/16; se não, `tailscale set --advertise-routes=172.15.0.0/16` no srv-sup e aprovar.
2. ACL: grant `tag:darckware-infra` → `172.15.0.0/16` (`tcp:22`, e `tcp:3389` se o RDP for usado).
3. VPS: `tailscale set --accept-routes`. As redes Docker usam 172.17–172.31, sem conflito com
   172.15.0.0/16 — conferido antes de aplicar.
4. Cadastrar a chave de API da Tailscale no ForgeHub (Acesso Remoto › Rede) para a tela mostrar
   rotas anunciadas × aprovadas; sem ela, só as aprovadas e visíveis à VPS aparecem.

## Decisões (aprovadas em 2026-10-17)

1. **Nome e rota**: tela `Acesso Remoto` em `/remote-access`; `/servers` redireciona (como `/vpn`).
2. **Permissão** (aprovada): a tela usa o módulo `servers`; ações sensíveis (preparar, rotacionar, revelar
   senha, scripts, rede) continuam só para admin.
3. **Modelo de caminhos** acima (Tailscale / roteador / via sub-rede / sem caminho / não cadastrado).
4. **Rede da SEMED**: roteador **srv-sup**, faixa **172.15.0.0/16** (Marcelo, 2026-10-17).
5. **Chaves**: as chaves em disco (`ssh_key_path`) migram para a ForgeVault (Fase 5).

## Fases

Cada fase é entregue, testada (vitest + pytest quando houver backend), verificada em 390px e
1440px e implantada antes da próxima.

### Fase 0 — Decisões e equivalência
- [x] Marcelo aprova as decisões 1–5 (2026-10-17).
- [x] Tabela "antes → depois" de toda ação das duas telas (feita ao fechar, 2026-10-17):

| Antes | Depois |
|---|---|
| Servidores › Verificar estado (todos) | Máquinas › Verificar agora (probe da prontidão, `refresh=true`) |
| Servidores › ↻ por linha | *sem botão por linha*: a prontidão reprova a cada 5 min e "Verificar agora" força todas |
| Servidores › Importar CSV / Novo servidor | Máquinas › Importar CSV / Nova máquina (módulo `servers`, escrita) |
| Servidores › abas VPS / SEMED (`environment`) | filtros caminho (Tailscale / via sub-rede) e cliente; `environment` segue no formulário |
| Servidores › ligar/desligar, terminal, editar, excluir, serviços publicados | mesmas ações na linha da máquina |
| Servidores › Instalar chave | Configurar acesso (servidor), chave vai para a ForgeVault |
| Servidores › botão do assistente (`AssistantToggleButton`) | *removido* (o assistente segue no restante do app) |
| Acesso Remoto › Máquinas (estações por cliente, grupos, senhas, RustDesk, sync) | Máquinas, mesma linha para servidor e estação |
| Acesso Remoto › Preparar estação | Configurar acesso (estação) e o botão rápido Preparar estação |
| Rede › dispositivos (busca, grupo por tag, testar) | Máquinas: dispositivo cadastrado = a linha da máquina (testar Tailscale); não cadastrado = seção própria com Cadastrar |
| Rede › VPS, reiniciar Tailscale, histórico, ACL | Rede Tailscale, + rotas de sub-rede por roteador |

### Fase 1 — Rotas de sub-rede no backend (só leitura)
- [x] `/api/v1/vpn/status` traz `subnet_routes` por nó (`PrimaryRoutes`/`AllowedIPs` sem host,
      tailnet ou exit node) — `host-bridge/vpn_control.py`; "aceita rotas" já vinha em `posture`.
      Anunciadas × aprovadas fica para quando a chave de API estiver cadastrada.
- [x] `/api/v1/servers/readiness` classifica cada máquina (`classify_access_path`, `access_path`/
      `access_via_*`/`tailscale_ipv4`) no caminho de acesso:
      `tailscale` | `subnet` (+ roteador) | `none`; casa por `tailnet_node_id`, depois IP, depois
      IP dentro de rota. Fonte ilegível = `unknown`, nunca "sem caminho".
- [x] Testes: `host-bridge/tests/test_vpn_control.py`, `app/tests/test_host_inventory.py`.

### Fase 2 — Habilitar a sub-rede (operação, com Marcelo)
- [x] srv-sup já anunciava e tinha aprovada 172.15.0.0/16 (confirmado em `PrimaryRoutes` após a ACL).
- [x] ACL: grant `tag:darckware-infra` → `172.15.0.0/16` `tcp:22` (Marcelo, 2026-10-17).
- [x] VPS: `tailscale set --accept-routes` (2026-10-17). Só `172.15.0.0/16 dev tailscale0` entrou na
      tabela 52; internet (eth0) e redes Docker (172.17–172.22) inalteradas.
- [x] Porta 22 a partir da VPS: OK srv-vm01, srv-ad03/04, srv-app01/02/05, host-pve01/02;
      **falha** srv-nas01/02 (:22) e PFsense 01 (:10022) / 02 (:22) — SSH desligado ou firewall local.
- [ ] Cadastrar a chave de API da Tailscale (rotas anunciadas × aprovadas na tela).
- [ ] Registrar a política atual na aba Rede (a cópia de 2026-10-16 está desatualizada).
- [ ] Conferir que 172.15.x.x:22 responde a partir da VPS e que as redes Docker seguem intactas.

### Fase 3 — Tabela única de máquinas
- [x] Aba **Máquinas** (`pages/remote-access/MachinesCard.tsx`) lista servidores, estações e
      dispositivos não cadastrados juntos, em seções por caminho, com filtros caminho/tipo/cliente/
      prontidão; roteadores mostram as rotas que anunciam; IP 100.x exibido quando o cadastro usa o da LAN.
- [x] Ações por linha conforme tipo e caminho: terminal SSH, verificar, testar conexão Tailscale,
      Configurar acesso, serviços publicados, senhas/RustDesk, editar, excluir, Cadastrar.
- [x] `useMachinesViewModel` (§21), absorvendo `useWorkstationsViewModel`, o estado de
      `pages/servers/index.tsx` e a lista de dispositivos de `useRemoteAccessViewModel`.
      `WorkstationsCard`/`useWorkstationsViewModel` removidos; diálogos de servidor extraídos para
      `pages/servers/ServerDialogs.tsx`. Verificado em 390px e 1440px (2026-10-17).

### Fase 4 — Uma tela, uma entrada no menu, Rede só diagnóstico
- [x] `/servers` → `/remote-access?tab=machines`; sidebar/Ctrl+K com uma entrada (módulo `servers`).
      Rota guardada por `RequireModule` (`components/auth/RequireAdmin.tsx`); `/remote-access/executions/:id`
      continua só admin.
- [x] `pages/servers/index.tsx` removido; `ServerForm`, `ServerServicesPanel` e `ServerDialogs` ficam
      em `pages/servers/` e são usados por Máquinas.
- [x] Aba **Rede Tailscale**: VPS (+ aceita rotas), rotas de sub-rede por roteador, totais, histórico, ACL.
      A lista de dispositivos saiu (está em Máquinas). Anunciadas × aprovadas segue dependendo da chave de API.
- [x] i18n: `servers.json` incorporado a `remoteAccess.json` (chave `servers`, via `keyPrefix`); órfãs
      (`devices.*` da lista antiga, `path.*`, `servers.page.*`, `servers.status.*`, `nav.servers`) apagadas.
- [x] Permissão: não-admin com `servers.view` vê só Máquinas (sem abas, sem ações rápidas); dentro do
      card, criar/editar/importar/ligar-desligar pedem `can_write`, excluir `can_delete`; sincronizar/
      cadastrar/testar Tailscale, instalar chave e senhas só admin. `/vpn/status` não é buscado para
      não-admin. Backend: `GET /servers/readiness` passou de admin para `require_perm("servers","view")`.
      Testes: `test_readiness_is_open_to_the_servers_module`, `MachinesCard.test.tsx`, `index.test.tsx`,
      `RequireAdmin.test.tsx`, `navSections.test.tsx`. Verificado em 390px e 1440px (2026-10-17).

### Fase 5 — Um fluxo de "Configurar acesso"
- [x] Botão único **Configurar acesso** por máquina (admin, máquina não pronta): servidor → instalar chave
      com conta de admin; estação → Preparar estação com a máquina já escolhida. Funciona pelo IP Tailscale
      ou da sub-rede (o SSH sai da VPS, que já roteia 172.15.0.0/16).
- [x] Toda chave nova na ForgeVault: "Instalar chave" grava a chave na ForgeVault e troca para ela
      (`ServerInstallKeyResult.vault`); a preparação nunca gera uma segunda chave para uma máquina que já
      está na chave da ForgeVault; a rotação já gravava.
- [x] Em 2026-10-24, removidos os endpoints de leitura/gravação de chaves em arquivo, o fluxo migrador e o suporte ao diretório `/root/agents`. O inventário foi limpo: chaves continuam acessíveis via ForgeVault quando há referência; hosts sem referência precisam reinstalar o SSH.
- [x] Prontidão e `/check` usam a chave da ForgeVault quando há uma (mesma ordem do terminal, execuções
      e Explorer); o terminal aberto pela aba Máquinas passa pelo agente da ForgeVault.
- [x] Produção (2026-10-17): bridge reiniciado, implantado, migração rodada. Na ForgeVault e verificadas,
      sem arquivo: desk-semed-admin, srv-app01/02/05, srv-sup, vmi3547248 (srv-app01/02/05 passaram de
      "sem acesso" a prontas). Ficaram no arquivo: gat-adm-pc01/gat-ges-nb01 (offline; rodar de novo quando
      voltarem) e host-pve01/02 (o arquivo da chave nem existe no host -- precisam de "Configurar acesso").

Probe real em 2026-10-17 (cópia do bridge na 8911, só `exit`): srv-app01/02/05 **recusam a chave em
arquivo e aceitam a da ForgeVault** (a prontidão os mostrava sem acesso); host-pve01/02 recusam a chave
em arquivo (ficarão no arquivo); desk-semed-admin, srv-sup e vmi3547248 passam nos três modos;
gat-adm-pc01/gat-ges-nb01 offline. **srv-sup e srv-app05 estão cadastrados com o mesmo IP 172.15.2.5**
(o arquivo da chave do srv-sup indica 100.107.175.100) — corrigir o cadastro.

### Fase 6 — Limpeza e documentação
- [x] Removidos: `pages/servers/index.tsx` (fase 4), hooks de ingresso/chave de API da Tailscale sem tela
      (`useEnrollStation`, `useEnrollmentCheck`, `useTailscaleApiKey`, `useSaveTailscaleApiKey` — o diálogo
      saiu em 2026-10-16; as rotas do backend ficam) e ~60 traduções órfãs de `remoteAccess.json`.
- [x] `CLAUDE.md` (bullet "Servers and Remote Access are one screen"), `MOBILE_RESPONSIVE_PLAN.md`,
      `REMOTE_MAINTENANCE_PLAN.md`, `FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` atualizados.
- Não implementado (registrado para não parecer feito): rotas **anunciadas × aprovadas** — a chave de API
  da Tailscale só serve hoje ao ingresso de estação, e a aba Rede mostra apenas rotas aprovadas.

## Fora do escopo

- API (`/api/v1/servers`, `/api/v1/vpn`) e módulos de permissão mantêm os nomes.
- O Workspace (terminal SSH e Explorer) continua lendo `useServers()`; não muda.
- O agente Nexo remanescente em 24.152.126.186 é tratado à parte.

## Riscos

- **Permissão**: perfis não-admin que hoje veem Servidores não podem perder acesso nem ganhar
  ações de admin — coberto por teste de visibilidade por perfil na Fase 4.
- **Rotas na VPS**: `--accept-routes` muda a tabela de rotas da VPS; uma faixa anunciada que
  colida com redes Docker ou com a própria rede da VPS derrubaria serviços — conferido na Fase 2.
- **Chaves**: a Fase 4 mexe no que o Terminal usa para logar; cada servidor é verificado
  (`/check`) depois de migrado, e o caminho em disco só deixa de ser usado após sucesso.
