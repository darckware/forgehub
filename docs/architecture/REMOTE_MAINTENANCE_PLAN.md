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
- **Chave SSH por identidade (agente), não por máquina** — o fingerprint no log da estação diz
  quem entrou. `SSH_<IDENTIDADE>_PRIVATE_KEY`.
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
- [ ] Comando de preparação por SO; "Instalar chave" por SO; host key fixada na preparação.
- [ ] Migrar as chaves Fernet de `servers` e arquivos em `/root/agents/aegis/...` para a ForgeVault.
- [ ] Rotação de senha admin e RustDesk (manual, com validação).

### Fase 4 — Execução avulsa
- [ ] Comando numa estação/grupo, resultado por estação, AuditEvent, mascaramento de segredos.
- [ ] **Tela de execução** (Marcelo, 2026-10-15): por estação, o retorno de cada comando —
      saída (stdout/stderr), exit code, duração — e o veredito claro: concluída com sucesso / falhou.
- [ ] **Em caso de erro, encadear outros scripts**: a partir de uma execução com falha, escolher
      um ou mais scripts da biblioteca e rodar só nas estações que falharam; a nova execução fica
      ligada à original (histórico mostra a sequência: falha → correção → resultado).
- [ ] Terminal/Explorer para Windows (PowerShell) — os atuais assumem shell POSIX.

### Fase 5 — Roteiros, lote e agendamento
- [ ] **Biblioteca de scripts (tarefas pré-cadastradas)**, reutilizáveis, versionados,
      classificados pelo tipo de comando: **Linux** (bash/sh), **PowerShell** (Windows) e
      **macOS** (zsh/bash). O tipo filtra onde o script pode rodar: só aparece/roda em estações
      do SO compatível. Cada script: nome, descrição, categoria, parâmetros, risco
      (leitura/alteração/destrutivo), timeout, e quem cadastrou/alterou.
- [ ] Lote com canário e parada por limite de falhas; uma execução por estação.
- [ ] Agendamento com janela no fuso do cliente; offline aguarda; janela fechada = "não executada".
- [ ] Aprovação (Approval) para destrutivo/avulso; botão "parar todas as execuções".
- [ ] Rotação em lote, periódica e após revelação.

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

## Decisões pendentes
1. Rotacionar a conta admin do cliente ou uma conta nossa (`darckware-adm`)?
2. Intervalo padrão de rotação (30 dias?) e rotação após revelar (sim/não)?
3. Aprovação também para "alteração" ou só "destrutivo"?
4. Manutenção consome franquia / entra no informe?
5. Servidores SEMED 172.15.x: subnet router no `srv-sup` ou ProxyJump? (172.15/16 não é faixa privada.)
6. Estação piloto (sugestão: GAT-ADM-PC01 ou NotebookSTI).
