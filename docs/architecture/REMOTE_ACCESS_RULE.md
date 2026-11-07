# Regra de acesso dos agentes às máquinas

Definida por Marcelo em 2026-11-06. Vale a partir dessa data para todo servidor e estação cadastrados no ForgeHub. Detalhes técnicos: `REMOTE_MAINTENANCE_PLAN.md`.

## A regra

1. **Conta única.** Toda máquina tem a conta `darckware`. É a única conta usada por agentes.
2. **Quem prepara.** Marcelo prepara as máquinas, uma a uma. Agente não cria nem altera conta de máquina.
3. **Chave.** A chave SSH da conta fica no ForgeVault. O ForgeHub é o único que a usa. Nenhum agente recebe, lê ou guarda a chave.
4. **Como o agente acessa.** Sempre pelo ForgeHub: script da biblioteca, proposta aprovada por hash ou comando no acesso direto (`run_remote_command`). SSH direto de agente é proibido, mesmo com uma chave ao alcance.
5. **Quem autoriza.** Marcelo escolhe os agentes da lista e abre o acesso direto em Acesso Remoto, por máquina e por tempo (1 h, 4 h ou 24 h). `sudo` e `docker` ficam desligados, salvo quando ele marca a opção.
6. **Pausa.** O botão Pausar bloqueia todos os agentes em todos os caminhos do ForgeHub. Pessoas continuam com acesso.
7. **Auditoria.** O ForgeHub registra sozinho cada execução, com o nome do agente que executou, a máquina, o comando, o motivo e o resultado. O agente não faz o próprio registro. Como a conta é única, o log do servidor mostra só `darckware`: o histórico da máquina no ForgeHub é a fonte de quem fez o quê.
8. **Alarme.** A checagem ECO-060 do Auditor falha se alguém além do ForgeHub ler uma chave SSH no cofre.

## Preparar uma máquina

1. Em Acesso Remoto › Máquinas, use **Configurar acesso** com uma conta administrativa da máquina. O ForgeHub cria a conta `darckware`, instala a chave e guarda a chave no cofre.
2. Linux: a conta fica com `sudo` sem senha, porque os scripts usam `sudo -n`. Windows: a conta fica como administradora local.
3. Confira que a máquina aparece como `complete` em Máquinas, que `remote_user` é `darckware` e que um comando simples responde.
4. Só depois disso desative a conta antiga da máquina, como `aegis`. Nunca antes: a máquina ficaria sem acesso.

## Exceções

pfSense, Proxmox e NAS podem não aceitar esse padrão. Cada caso é decidido por Marcelo, e a exceção fica registrada na descrição da máquina.

## Limites conhecidos

- Enquanto os agentes forem `Admin` no ForgeVault, a regra 3 depende de eles a cumprirem. A ECO-060 acusa o descumprimento.
- Os agentes rodam como `root` na VPS, então um bloqueio absoluto exigiria rodá-los com outro usuário.
- A opção de `sudo` é detecção de texto, não barreira. A barreira real é o poder da conta na máquina.
