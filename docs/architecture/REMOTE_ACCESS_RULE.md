# Regra de acesso dos agentes às máquinas

Definida por Marcelo em 2026-11-06. Vale a partir dessa data para todo servidor e estação cadastrados no ForgeHub. Detalhes técnicos: `REMOTE_MAINTENANCE_PLAN.md`.

## A regra

1. **Conta única.** Toda máquina tem a conta `darckware`. É a única conta usada por agentes.
2. **Quem prepara.** Marcelo prepara as máquinas, uma a uma. Agente não cria nem altera conta de máquina.
3. **Chave.** Cada máquina tem a sua própria chave SSH para a conta `darckware`; nunca a mesma chave em duas máquinas (Marcelo, 2026-11-12). Ela fica no ForgeVault, num segredo da máquina (`WS_<CLIENTE>_<MÁQUINA>_<SUFIXO>_SSH_KEY`; nomes antigos sem sufixo ou com o sufixo no fim continuam valendo). O ForgeHub é o único que a usa. Nenhum agente recebe, lê ou guarda a chave.
4. **Como o agente acessa.** Sempre pelo ForgeHub: script da biblioteca, proposta aprovada por hash ou comando no acesso direto (`run_remote_command`). SSH direto de agente é proibido, mesmo com uma chave ao alcance.
5. **Quem autoriza.** Marcelo configura cada agente na lista de Acesso Remoto. Não há abertura avulsa nem botão Encerrar. O padrão do formulário é **todas as máquinas**, duração **0 h (indeterminado)** e `sudo/docker` desligado; o acesso só vale depois de salvar e confirmar a ampliação sensível. Todas inclui máquinas preparadas no futuro. Selecionar máquinas/grupos restringe o acesso às máquinas atuais dessa seleção. Motivo e finalidade são opcionais; 1 h, 4 h e 24 h continuam disponíveis. Escopo vazio não dá acesso. Alterar a configuração vale para o próximo comando. Excluir da lista, pausar ou vencer o prazo bloqueia novas operações.
6. **Pausa.** O botão Pausar bloqueia todos os agentes em todos os caminhos do ForgeHub. Pessoas continuam com acesso.
7. **Auditoria.** O ForgeHub registra sozinho cada execução, com o nome do agente que executou, a máquina, o comando, o motivo e o resultado. O agente não faz o próprio registro. Como a conta é única, o log do servidor mostra só `darckware`: o histórico da máquina no ForgeHub é a fonte de quem fez o quê.
8. **Tarefa e execução.** Comandos, scripts e transferências exigem tarefa em execução dirigida ao agente e credencial individual vinculada ao mesmo run. Ao terminar, falhar, cancelar ou esgotar o run, a credencial é revogada; a validade temporal fica como proteção adicional. Operação já enviada termina sozinha ou no timeout.
9. **Arquivos.** Upload/download passa pelo ForgeHub, que conecta por SSH; o agente não recebe a chave. Há confinamento de caminhos locais, bloqueio de segredos, limite de 200 MiB, hash SHA-256 e publicação atômica; sobrescrita exige opção explícita e fica registrada. O histórico guarda metadados, nunca conteúdo. Transferência exige POSIX; Windows é recusado explicitamente nesta versão.
10. **Retenção.** Após 90 dias, somente stdout/stderr de execuções encerradas expiram. Comando, agente, tarefa, máquina, motivo, datas, resultado e auditoria permanecem; a tela informa saída expirada.
11. **Alarme.** A checagem ECO-060 do Auditor falha se alguém além do ForgeHub ler uma chave SSH no cofre.

## Preparar uma máquina

1. Em Acesso Remoto › Máquinas, use **Configurar acesso** com uma conta administrativa da máquina. O ForgeHub cria a conta `darckware`, instala a chave e guarda a chave no cofre.
2. Linux: a conta fica com `sudo` sem senha, porque os scripts usam `sudo -n`. Windows: a conta fica como administradora local.
3. Confira que a máquina aparece como `complete` em Máquinas, que `remote_user` é `darckware` e que um comando simples responde.
4. Só depois disso desative a conta antiga da máquina, como `aegis`. Nunca antes: a máquina ficaria sem acesso.

## Exceções

pfSense, Proxmox e NAS podem não aceitar esse padrão. Cada caso é decidido por Marcelo, e a exceção fica registrada na descrição da máquina.

## Limites conhecidos

- O suporte a segredo restrito no ForgeVault exige grant explícito para leitura, inclusive para Admin/Owner. A ativação nas chaves reais é uma operação separada, verificável e reversível; sem essa ativação, a regra 3 continua dependendo de cumprimento e da ECO-060. Mesmo após ativar, papéis com SecretWrite podem alterar a restrição ou grants, com auditoria: isto não é isolamento absoluto.
- Os agentes rodam como `root` na VPS, então um bloqueio absoluto exigiria rodá-los com outro usuário.
- A opção de `sudo` é detecção de texto, não barreira. A barreira real é o poder da conta na máquina.
