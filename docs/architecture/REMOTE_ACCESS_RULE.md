# Regra de acesso dos agentes às máquinas

> **Precedência operacional — 14/11/2026:** a decisão já publicada em
> `/root/.hermes/foundation/47_migrations/2026-11-14-development-access.md` e a seção
> `Active development policy` da política Foundation substituem as restrições
> conflitantes abaixo para desenvolvimento direto autorizado com Marcelo. Essa
> exceção vale para Porthus/Claude, Aramis/Codex e Dartan/agy, com host, operação/path,
> validade finita, credencial protegida sem leitura da chave e captura independente
> confiável verificada antes de operar. Dispensa Task/run somente nesse modo direto;
> grants, pausa, revogação, expiração e elevação continuam obrigatórios. O backend
> colaborativo descrito abaixo é uma implementação API separada e desligada; sua
> homologação não condiciona a vigência da decisão procedimental já publicada.
> Companion de integração: `.claude/worktrees/development-access-rule/docs/plans/development-access-foundation.md`.

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

### Execução colaborativa autorizada em sessão ativa — formalização inativa

**Histórico procedimental substituído pela decisão acima.** Os parágrafos de
enforcement abaixo documentam a feature API desligada, com suas próprias exigências
de Task/run, sem revogar a exceção direta aprovada na Foundation.

Esta seção é somente uma formalização procedimental e documental. **Ela está inativa e não
habilita nenhuma operação agora.** Na formalização (#42347), a implementação não mantinha nem valida um estado ou ID de
sessão ativa com Marcelo, não validava o término da sessão por comando e não restringia cada comando
à operação específica autorizada (o enforcement, desligado, veio depois; ver abaixo). Portanto, nenhum agente, Marcelo ou operador pode executar uma
operação com base nesta exceção; a regra normal continua valendo integralmente.

Uma ativação futura exigirá, antes de qualquer uso, mudança implementada que permita verificar de
forma fail-closed: a sessão ativa e seu ID vinculados a Marcelo e ao agente; a tarefa ou run dirigido
ao agente; a máquina autorizada; a operação específica e cada comando correspondente; e o término,
revogação, pausa ou expiração da autorização. Também exigirá revisão independente e homologação. Até
que esses controles existam e sejam homologados, não há autorização excepcional válida.

Quando e se for ativada após esse enforcement, **execução colaborativa direta** significará somente
a interação operacional em tempo real entre Marcelo e o agente pelo ForgeHub; nunca conexão direta
do agente à máquina. A chave privada SSH da máquina é um artefato distinto: permanece somente no
ForgeVault, é usada somente pelo ForgeHub e nunca é lida, recebida, copiada, entregue ou exposta ao
agente. A credencial individual task-bound do run é outro artefato, administrado pelo ForgeHub,
vinculado à tarefa/run e revogado no encerramento; ela não é a chave privada SSH e não concede ao
agente acesso a essa chave.

Mesmo após eventual ativação, Marcelo teria de autorizar previamente a máquina e a operação
específicas, o escopo permaneceria estritamente limitado a elas, a validade terminaria no primeiro
fim da sessão ou do run, e toda execução continuaria sujeita à auditoria obrigatória do ForgeHub.
Revogação, pausa ou expiração bloqueariam novas operações imediatamente.

É proibido ao agente, inclusive em qualquer futura sessão, usar SSH, `scp` ou `rsync` diretamente;
ler, usar, copiar, entregar ou expor a chave privada SSH; ampliar a máquina, a operação ou o escopo
autorizados; ou reutilizar a autorização depois do encerramento da sessão ou do run. Qualquer
operação fora desses limites é recusada. Fora de uma futura ativação implementada e homologada,
permanece proibido qualquer acesso direto fora do ForgeHub.

**Enforcement implementado, desligado (2026-11-14).** O controle fail-closed descrito acima agora
existe no código, atrás da chave `REMOTE_COLLABORATION_ENABLED` (padrão desligada) e de
`REMOTE_COLLABORATION_OWNER_USER_ID` (o UUID de Marcelo); com a chave desligada ou o dono vazio ou
inválido, toda rota recusa (`COLLABORATION_DISABLED`). Somente Marcelo, administrador, numa sessão
de navegador ativa (JWT com `sid` vivo), abre a sessão colaborativa (`remote_collaboration_sessions`:
seu ID, a sessão de navegador dele, o agente, a tarefa e o run despachados naquele momento, uma
máquina, a operação autorizada, elevação e validade de até 4 h) e autoriza cada comando antes, texto
e shell exatos (`remote_collaboration_commands`, com SHA-256). A cada comando, o ForgeHub verifica de
novo, sem cache: chave e dono; pausa global; sessão ativa e não expirada; dono ainda administrador e
sua sessão de navegador ainda ativa (logout, revogação ou timeout encerram); o agente da sessão, com a
credencial individual `dispatch:<run>` da tarefa ainda em execução e o mesmo run da abertura; somente
a máquina autorizada, preparada com a conta `darckware`; e o comando autorizado, não usado, idêntico
ao enviado, consumido uma única vez na mesma transação que registra a execução. Elevação exige
permissão na sessão e no comando. Toda abertura, autorização, execução e encerramento ficam na
auditoria da sessão e no histórico da máquina. Um comando que a execução marcaria como pulada
(acesso desligado, sem login ou endereço, shell incompatível com o sistema) é recusado antes
(`MACHINE_NOT_RUNNABLE`) sem consumir a autorização, e apagar a sessão de navegador ou a máquina não
apaga o registro: o vínculo vira nulo e a sessão deixa de valer. A linha da máquina fica travada
(`FOR NO KEY UPDATE`, o mesmo lock de `run_direct_command`) da verificação final até o commit da
execução: nenhuma edição da máquina (login, endereço, chave), nenhum `run_direct_command`, nenhuma
outra sessão colaborativa nem a rota padrão de scripts do agente (`agent_create_execution`) na mesma
máquina passa no meio; a rota de scripts também mantém o lock até `launch_execution` confirmar o
registro. A concorrência entre comando colaborativo e script padrão é coberta por teste de integração
no banco isolado. Não há ferramenta MCP nem tela nesta mudança.
**A exceção continua inativa**: só poderá ser ligada depois de revisão independente, homologação e
ativação explícita de Marcelo; até lá, nenhuma operação pode se basear nela.

## Limites conhecidos

- O suporte a segredo restrito no ForgeVault exige grant explícito para leitura, inclusive para Admin/Owner. A ativação nas chaves reais é uma operação separada, verificável e reversível; sem essa ativação, a regra 3 continua dependendo de cumprimento e da ECO-060. Mesmo após ativar, papéis com SecretWrite podem alterar a restrição ou grants, com auditoria: isto não é isolamento absoluto.
- Os agentes rodam como `root` na VPS, então um bloqueio absoluto exigiria rodá-los com outro usuário.
- A opção de `sudo` é detecção de texto, não barreira. A barreira real é o poder da conta na máquina.
