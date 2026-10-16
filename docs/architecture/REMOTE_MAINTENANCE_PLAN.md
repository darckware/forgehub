# Acesso Remoto e manutenção de estações via SSH

Plano vivo (2026-10-15, Marcelo). Marque cada item na mesma mudança que o entrega.

## Objetivo

Manter as estações de trabalho (e servidores) dos clientes pela rede privada Tailscale:
estações agrupadas por cliente, comandos avulsos ou em lote executados por agente,
manutenções agendadas, credenciais na ForgeVault e tudo documentado/auditado.

## Decisões tomadas

- A manutenção é feita **pela tailnet** (Tailscale). Nada pelo IP público.
- A tela "VPN" vira **Acesso Remoto** (`/remote-access`; `/vpn` redireciona). A API continua em
  `/api/v1/vpn` e o módulo de permissão continua `vpn`, para não quebrar perfis já concedidos.
- **Toda chave e senha criada fica na ForgeVault.** O ForgeHub guarda só `forgevault_secret_id`,
  chave pública e fingerprint. A privada nunca em disco: carregada num `ssh-agent` efêmero.
- ~~Chave SSH por identidade (agente)~~ → **uma chave por máquina** (decisão 6, 2026-10-16); quem pediu
  cada execução fica no log de execuções do ForgeHub (decisão 7), não no fingerprint.
- Cadastro da estação tem **SO (Windows/Linux/macOS)** e **login do administrador**; o
  "Instalar chave" usa um script por SO (mesmo fluxo de `/servers/{id}/install-key`).
  Pré-requisito: comando de preparação por SO (ativar OpenSSH/Login Remoto), rodado uma vez via RustDesk.
- **Rotação de senha forte** por SSH, gravada antes na ForgeVault, validada depois:
  - admin local: `WS_<CLIENTE>_<HOSTNAME>_LOGIN`
  - RustDesk (senha permanente, `rustdesk --password`): `WS_<CLIENTE>_<HOSTNAME>_RUSTDESK`,
    com **botão de rotação** individual e em lote. Só a senha — config do servidor RustDesk fora do escopo.
- **Indicador de prontidão** por estação: Pronta / Ocupada / Online sem acesso / Offline /
  Não preparada / Desconhecido (falha de leitura nunca vira "offline").
- Agente **nunca recebe a chave**: todo comando passa pelo ForgeHub (`host_exec`), que busca a
  chave na ForgeVault em nome do agente (auditado) e executa via host-bridge.

## Fases

### Fase 1 — Acesso Remoto (tela VPN corrigida)
- [x] Ler o `tailscale status --json` inteiro (antes cortado em 8 KB → "Indisponível").
- [x] Modelo "este servidor + todos os dispositivos da tailnet" no lugar de notebook↔VPS fixos.
- [x] Remover "connect"/"disconnect" (o connect renomearia o VPS) e o restart remoto via chave em arquivo.
- [x] Teste de conectividade (`tailscale ping`) por dispositivo, resolvido pelo ID do status atual.
- [x] Renomear para Acesso Remoto.

### Fase 2 — Inventário de estações
- [x] Host com `kind` (server/workstation), SO, login do admin, cliente Darckware, local, grupos (N:N), nó tailnet
      (`servers` + `host_groups`/`host_group_members`, migration `9d1d2daaa64f`).
- [x] Sincronizar da tailnet (`POST /servers/tailnet:sync`): vincula por nó, IP ou nome; servidor mantém o IP
      pelo qual é alcançado; dispositivo novo só vira estação se for **marcado para importar** (um excluído não
      volta sozinho); sugere cliente pela tag `tag:client-<slug>`; nunca apaga.
- [x] Indicador de prontidão (`GET /servers/readiness`: tailnet a cada chamada, sonda SSH em cache de 5 min),
      polling de 30 s, resumo por cliente/grupo no card "Estações de trabalho" do Acesso Remoto.
      "Ocupada" fica reservado para a Fase 4. Pendente: conferência visual em 390/1440 px.

### Fase 3 — ForgeVault e preparação
- [ ] ServiceAccount do ForgeHub na ForgeVault (**precisa token admin de organização**).
- [ ] Projeto `infra`, ambiente por cliente; chaves por identidade.
- [x] Comando de preparação por SO — botão **Preparar** (`POST /servers/{id}/preparation`,
      `core/host_preparation.py`): garante a chave da estação (bridge `/v1/servers/ensure-key`, cópia
      criptografada no cadastro) e devolve o script para colar uma vez pelo RustDesk (Windows: OpenSSH +
      firewall só da tailnet + `administrators_authorized_keys`; Linux: sshd + ufw; macOS: Login Remoto).
      Idempotente; só adiciona, nunca remove contas ou chaves.
- [ ] Host key fixada na preparação (hoje: aceita na primeira conexão, recusa se mudar).
- [ ] Migrar as chaves Fernet de `servers` e arquivos em `/root/agents/aegis/...` para a ForgeVault.
- [ ] Rotação de senha admin e RustDesk (manual, com validação).

### Fase 4 — Execução avulsa
- [x] Comando numa estação/grupo, resultado por estação, AuditEvent, mascaramento de segredos
      (`host_executions`/`host_execution_results`, migration `9d97a3417ce1`; bridge `POST /v1/servers/exec`
      em `host-bridge/host_exec.py`; `core/secret_masking.py`). Uma execução por máquina por vez
      (ocupada = "Não executada" com motivo, e "Ocupada" na prontidão). Recuperação por heartbeat:
      só fecha como "interrompida" o que parou de dar sinal (dev e produção dividem o banco).
- [x] **Tela de execução** (`/remote-access/executions/:id`): por estação, saída (stdout/stderr), exit code,
      duração e veredito (concluída com sucesso / falhou / não executada, com o motivo); parar as que não começaram.
- [x] **Em caso de erro, encadear correção**: "Corrigir as que falharam" roda outro comando só nas estações
      que falharam; a nova execução fica ligada à original (falha → correção → resultado).
      Escolher o script da biblioteca entra com a Fase 5.
- [ ] Terminal/Explorer para Windows (PowerShell) — os atuais assumem shell POSIX.
- [ ] Validar PowerShell numa estação Windows real (piloto). **Pendente (2026-10-15):** `gat-adm-pc01`
      importada (cliente HW Clube de Tiros, login `administrador`, chave `.../ssh_keys/100_82_42_10_key`
      com cópia no cofre); as três máquinas Gatling respondem na tailnet mas sem SSH — falta rodar o
      script do "Preparar" nelas pelo RustDesk. Depois: validar login, `Get-ComputerInfo` e a tela de execução. PowerShell por enquanto limitado a ~2.800
      caracteres (linha de comando do cmd.exe); scripts maiores chegam com a biblioteca (cópia para a estação).

### Fase 5 — Roteiros, lote e agendamento
- [ ] **Biblioteca de scripts (tarefas pré-cadastradas)**, reutilizáveis, versionados,
      classificados pelo tipo de comando: **Linux** (bash/sh), **PowerShell** (Windows) e
      **macOS** (zsh/bash). O tipo filtra onde o script pode rodar: só aparece/roda em estações
      do SO compatível. Cada script: nome, descrição, categoria, parâmetros, risco
      (leitura/alteração/destrutivo), timeout, e quem cadastrou/alterou.
- [ ] Lote com canário e parada por limite de falhas; uma execução por estação.
- [ ] Agendamento com janela no fuso do cliente; offline aguarda; janela fechada = "não executada".
- [ ] Aprovação (Approval) para destrutivo/avulso; botão "parar todas as execuções".
- [ ] Rotação em lote (sob demanda — sem rotação periódica, decisão 2).

### Fase 6 — Agente
- [ ] MCP `list_hosts`/`host_exec`/`run_runbook`; despacho pelo Messages.
- [ ] Saída de comando tratada como dado, nunca instrução; allowlist por risco.

### Fase 7 — Documentação
- [ ] Histórico por estação, relatório por execução, vínculo com chamado/demanda Darckware,
      horas na franquia e informe mensal.

## Lacunas a cobrir antes de estação real
Host key fixada · acesso de emergência (backup da ForgeVault fora do VPS) · Windows no
Terminal/Explorer · saída como dado · lote em etapas · desligamento de cliente/estação.
Depois: aviso ao usuário, limites do SSH no Windows (sessão 0), repositório de instaladores,
permissões por cliente, fuso, sudo sem senha (Linux/macOS), inventário, alertas, relatório,
retenção/mascaramento de logs, LGPD/contrato, estação de testes.

## Replanejamento (2026-10-16)

Pedidos de Marcelo no dia: escolher **estação ou servidor**; ingressar por **SSH com usuário e senha**
(ForgeHub detecta Linux/Windows/macOS e instala tudo); instalar **Tailscale** (chave automática ou
informada) e, se preciso, **RustDesk** já configurado (rede da Darckware) com **senha rotacionável**;
e uma **tela única de scripts**: escolher máquinas, biblioteca de scripts com classificação e
descrição, executar ou **agendar**.

### Análise da estrutura atual
| Peça | Onde está | Problema |
|---|---|---|
| Servidores | página Servidores (`kind=server`) | inventário separado das estações; "Instalar chave" só lá |
| Estações | card no Acesso Remoto (`kind=workstation`) | mesma tabela `servers`, telas diferentes |
| Entrar no suporte | Sincronizar/Importar, Preparar, Ingressar, Instalar chave | 4 caminhos que se sobrepõem |
| Executar | diálogo "Executar comando" + card Execuções + tela da execução | comando avulso; sem biblioteca nem agendamento |
| Rede | estado da tailnet + card da política | ok |
| Instalador Windows | `darckware-remote` (fora do ForgeHub) | já faz Tailscale+RustDesk com hash/assinatura — **reaproveitar**, não duplicar |
| Segredos | Fernet no cadastro (chave SSH, senha `darckware`, chave API Tailscale) | provisório até a ForgeVault |

### Estrutura proposta — Acesso Remoto com 3 abas
1. **Máquinas** — inventário único (servidores + estações), filtro por tipo/cliente/grupo/SO/prontidão,
   botão **Adicionar máquina** (assistente) e, por linha, só: Senha, RustDesk (ID, senha), Editar.
   **Sem botão Executar nem Preparar por linha** (Marcelo, 2026-10-16): toda execução parte da tela de
   scripts, e preparação/ingresso/rotação viram **scripts de sistema** da biblioteca.
2. **Scripts e execuções** — biblioteca de scripts + tela única de execução (escolher máquinas → script
   → agora ou agendado) + histórico (já existente: tela da execução, correção nas que falharam).
3. **Rede** — tailnet, política (ACL), dispositivos.

A página Servidores continua para serviços web e cofre de chave de infraestrutura, apontando para cá.

### Assistente "Adicionar máquina"
- Tipo: estação ou servidor · Cliente · Tag da tailnet · Local/grupo.
- Caminho de acesso:
  a) **Já está na tailnet** → importar (sync existente);
  b) **Script pelo RustDesk** → script único para colar (SO escolhido);
  c) **SSH com usuário e senha** → ForgeHub conecta uma vez, **detecta o SO**, roda a instalação e mostra
     a saída na tela de execução; a senha informada não é gravada.
- Instala: Tailscale (chave de uso único gerada pela API, ou colada) · OpenSSH (Windows) · conta
  `darckware` (admin, senha única gerada e guardada) · chave do ForgeHub · RustDesk opcional
  (padrão: sim em estação, não em servidor) configurado com o servidor da Darckware.
- Windows usa o instalador `darckware-remote` (fixado num commit) para Tailscale+RustDesk; Linux usa
  script próprio (Tailscale `install.sh`, RustDesk .deb 1.4.9). macOS fica para depois.
- Ao final o ForgeHub registra IP da tailnet e o **ID do RustDesk** e a máquina fica Pronta.

### RustDesk
- ID e senha permanente guardados por máquina (criptografados); **Rotacionar** troca via SSH e só grava a
  nova após sucesso; revelar é auditado. Rotação só quando pedida (decisão 2), individual ou em lote.

### Scripts e agendamento
- Script: nome, **classificação** (categoria), **descrição**, tipo (PowerShell / Linux sh / macOS),
  risco (leitura / alteração / destrutivo), timeout, parâmetros, versões, autor.
- Tela única: filtro de máquinas (cliente, grupo, SO, prontidão) → script da biblioteca (só os
  compatíveis com o SO) ou avulso → **Executar agora** ou **Agendar** (data/hora no fuso do cliente;
  máquina offline aguarda até o fim da janela, depois "não executada").
- Usa o motor atual (`host_executions`): resultado por máquina, correção nas que falharam.
- **Scripts de sistema** (cadastrados pelo ForgeHub, classificação "Instalação/Ingresso"): preparação,
  ingresso (Tailscale/OpenSSH/darckware/RustDesk), rotação da senha do RustDesk. Parâmetros por máquina
  (chave do ForgeHub, senha gerada, chave Tailscale de uso único) são preenchidos na hora e mascarados.
- **Rotação na tela de execução** (Marcelo, 2026-10-16), por máquina ou em lote, como scripts de sistema:
  - **senha da conta `darckware`**: gera → grava nova versão na ForgeVault → aplica por SSH → valida login
    com a nova → só então vira a versão atual (falha = a anterior continua valendo);
  - **chave SSH**: gera par novo → adiciona a pública nova usando a chave atual → valida login com a nova →
    remove a pública antiga → nova versão na ForgeVault (nunca fica sem acesso no meio do caminho);
  - **senha do RustDesk**: mesmo fluxo da senha (`rustdesk --password`).
- **Todas as senhas e chaves das máquinas na ForgeVault** (Marcelo, 2026-10-16) — nada mais em coluna
  criptografada no cadastro nem em arquivo em `/root/agents/aegis/...`. O ForgeHub guarda só o
  `forgevault_secret_id`. Na execução, a chave privada é buscada na ForgeVault e carregada num `ssh-agent`
  efêmero do bridge (nunca em disco); cada busca fica na auditoria da ForgeVault.
  Pré-requisito: projeto da ForgeVault para infraestrutura e ServiceAccount do ForgeHub com permissão de
  criar/rotacionar segredos nele (precisa de um admin da organização, uma vez). Migração: chaves e senhas
  hoje no cadastro (Fernet) e arquivos em `/root/agents/aegis/server-management/ssh_keys/`.
- Máquina ainda sem acesso (não preparada): a tela oferece **executar por SSH com usuário e senha**
  (informados na hora, não gravados) ou **copiar o script pronto** para colar pelo RustDesk.

### Tela Servidores e Workspace: o que fica, o que muda, o que sai (análise 2026-10-16)
| Recurso da tela Servidores | Destino |
|---|---|
| Lista agrupada VPS/SEMED + filtro de ambiente | **vira a aba Máquinas** (filtros tipo/cliente/grupo/SO/prontidão; ambiente vira filtro) |
| Verificar status (sonda SSH) | **substituído pela prontidão** (mesma sonda do bridge, com cache) |
| Ligar/desligar acesso (estacionar) | **fica**, na aba Máquinas |
| Formulário (nome, IP, porta, usuário, ambiente, tipo, SO, cliente, grupos) | **reaproveitado** como cadastro da máquina; saem caminho da chave e passphrase |
| Instalar chave SSH com senha (cria usuário) | **sai** → script de sistema de ingresso/preparação ("SSH com usuário e senha") |
| Copiar chave pública / ler `.pub` do caminho | **sai** → chave pública vem da ForgeVault |
| Cofre de chave (backup/restaurar/colar/remover, Fernet) | **sai após migrar** para a ForgeVault |
| Passphrase da chave | **sai** (chaves geradas pelo ForgeHub não têm passphrase; ficam na ForgeVault) |
| Importar CSV | **fica**, adaptado aos campos novos (aba Máquinas) |
| Serviços web por porta + varredura | **fica**, como seção "Serviços" no detalhe da máquina |
| Copiar comando SSH / abrir terminal | **fica** como "Abrir terminal" (sessão interativa ≠ execução de script) |

**Workspace (reflexo direto):**
- **Menu SSH do terminal** lê a mesma tabela: hoje lista tudo, inclusive estações, agrupado só VPS/SEMED, e
  monta `ssh -i <arquivo>`. Muda para: inventário único agrupado por cliente/tipo, **prontidão** no lugar da
  sonda própria, esconde máquina sem IP/não preparada, e **autenticação pela chave da ForgeVault** — o bridge
  carrega a chave num `ssh-agent` efêmero da sessão do terminal (sem `-i` arquivo). Windows abre em PowerShell.
- **Explorer remoto** (`/v1/remote-fs`) usa os mesmos dados e scripts POSIX: mesma troca de autenticação;
  em máquina Windows o botão fica oculto até existir o Explorer em PowerShell (Fase 4, pendente).
- Página Servidores **descontinuada** ao fim da migração; a rota `/servers` redireciona para Acesso Remoto › Máquinas.

### Entregue em 2026-10-16 (passo 1, ainda sem commit/deploy na redação desta nota)
- [x] Acesso Remoto em abas: **Máquinas / Scripts e execuções / Rede** (`?tab=&sub=&system=`).
- [x] Biblioteca de scripts (`host_scripts`, versões, classificação fixa ampliável, risco, parâmetros como
      variáveis entre aspas, segredos mascarados), tela única **Executar** (filtros de máquina, script
      compatível com o SO, agora / uma vez / toda semana, janela de nova tentativa), **Agendamentos**
      (`host_schedules`, laço de 1 min com `FOR UPDATE SKIP LOCKED`) e **Histórico** com filtro por agente,
      pessoa e origem (`host_executions.trigger/agent_id/script_*`).
- [x] Scripts de sistema: Instalar Tailscale, Instalar RustDesk, Trocar senha do RustDesk (Windows via
      `darckware-remote` fixado em commit; Linux próprio); botões na aba Máquinas; senha + ID do RustDesk
      gravados só após sucesso; revelar senha do RustDesk auditado.
- [x] "Copiar script pronto" para máquina sem SSH (render auditado, nunca gravado).
- [x] Bridge: SSH com usuário/senha (sshpass via ambiente), detecção de SO, PowerShell longo em partes.
- [x] Saiu o botão Executar por linha e o diálogo "Ingressar estação" (rotas de backend mantidas).
- [x] **Preparar estação** (ação da aba Máquinas, não mais por linha): OpenSSH (só tailnet, PowerShell como
      shell), conta `darckware` administradora com senha forte gerada e gravada na **ForgeVault**
      (`WS_<CLIENTE>_<MÁQUINA>_LOGIN`), chave do ForgeHub. Modo SSH: entra uma vez com o administrador do
      cliente (senha não gravada), testa o login da darckware pela chave e **só então** bloqueia o
      administrador; tudo vira uma execução visível. Modo copiar: script para colar pelo RustDesk.
- [x] **ForgeVault**: projeto `infra`/`Production`, service account `forgehub-remote-access` (criados pelo
      comando local `host-bootstrap` da ForgeVault); o bridge (`host-bridge/forgevault_proxy.py`) é o único que
      fala com o cofre; senhas da darckware e do RustDesk vão para lá e o cadastro guarda só o id
      (`login_password_ref`, `rustdesk_password_ref`). `RUSTDESK_SERVER_PUBLIC_KEY` gravada.
- [x] Chaves SSH das máquinas na ForgeVault (`WS_<CLIENTE>_<MÁQUINA>_SSH_KEY`, `ssh_key_ref`): as execuções
      buscam a chave no cofre e o bridge a carrega num `ssh-agent` efêmero em `/dev/shm` só durante a conexão.
      Migração das chaves existentes: `POST /servers/keys:to-vault`. O terminal e o Explorer interativos ainda
      usam o arquivo do host (próxima melhoria: mesma troca para eles).
- [x] **Rotação sob demanda** (aba Máquinas → Rotacionar senha / Rotacionar chave SSH, uma ou várias máquinas,
      vira execução): senha da darckware (nova versão no cofre → aplica → testa; falha restaura a anterior) e
      chave SSH (nova instalada e testada antes de remover a antiga; nova privada no cofre).
- [x] Estação piloto `gat-adm-pc01` preparada de verdade pelo modo SSH (2026-10-16): darckware criada, login
      pela chave confirmado, `administrador` bloqueado.

### Ordem de entrega (revisada)
0. **ForgeVault**: projeto + ServiceAccount do ForgeHub; senhas/chaves passam a ser gravadas lá (bloqueia 1–3).
1. **Assistente "Adicionar máquina"** (em andamento: ingresso por script, chave API, senha no cadastro já
   prontos e testados; faltam SSH+senha, detecção de SO, RustDesk, tipo servidor).
2. **RustDesk**: ID, senha por máquina, revelar e rotacionar.
3. **Abas do Acesso Remoto** (Máquinas / Scripts e execuções / Rede) unificando as telas.
4. **Biblioteca de scripts + execução em tela única + agendamento.**
5. ForgeVault (Fase 3), host key fixada, Terminal/Explorer Windows, agentes (MCP), relatórios.

### Decisões (Marcelo, 2026-10-16)
1. **Inventário único** no Acesso Remoto (servidores + estações); página Servidores só para serviços/infra.
2. Senha do RustDesk **uma por máquina**.
3. Agendamento **único e recorrente** (ex.: toda segunda 22h).
4. Classificação de scripts em **lista fixa ampliável** (Diagnóstico, Manutenção, Instalação, Segurança, Limpeza).
5. **Não** instalar RustDesk em servidor Linux sem tela.
6. Chave SSH **uma por máquina** (substitui "por identidade" do plano original).
7. **Logs de execução por agente**: cada execução registra quem pediu — pessoa (tela) ou agente (MCP) —
   e a tela de logs filtra por agente (o que cada um executou, onde, resultado).

## Decisões pendentes
1. ~~Rotacionar a conta admin do cliente ou uma conta nossa?~~ **Decidido (Marcelo, 2026-10-15):**
   a preparação entra com a conta local do cliente (`administrador`; a senha é digitada no
   formulário a cada ação, nunca guardada). Ela cria em cada estação uma conta própria
   **`darckware`**, com **senha forte única por estação** gravada na ForgeVault
   (`WS_<CLIENTE>_<HOSTNAME>_LOGIN`) e a chave SSH instalada. Só depois de validar o login
   com a `darckware`, a conta `administrador` é **desativada** (nunca antes, para não trancar a
   estação). Daí em diante, a rotação é sempre da senha da `darckware`.
2. ~~Intervalo de rotação?~~ **Decidido (Marcelo, 2026-10-15): rotação só quando solicitada**
   (botão individual ou em lote), nunca automática por tempo nem disparada sozinha após revelar.
3. Aprovação também para "alteração" ou só "destrutivo"?
4. Manutenção consome franquia / entra no informe?
5. Servidores SEMED 172.15.x: subnet router no `srv-sup` ou ProxyJump? (172.15/16 não é faixa privada.)
6. Estação piloto (sugestão: GAT-ADM-PC01 ou NotebookSTI).
