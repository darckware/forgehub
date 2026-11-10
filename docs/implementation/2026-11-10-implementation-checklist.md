# Checklist de implementação e retomada

Atualizado em 2026-11-10, America/Sao_Paulo.

Objetivo: preservar todo o contexto e concluir o amadurecimento de Missões,
Messages, Operação 24x7 e Service Factory até a entrega verificada. O plano não
se limita ao subconjunto já implementado.

Fontes: [plano completo](../superpowers/plans/2026-11-09-mission-messages-maturation.md),
[matriz de requisitos e continuidade](../reports/2026-11-09-development-continuity.md),
[histórico dos pedidos](2026-11-10-user-requirements-history.md) e
[progresso por etapa](../reports/2026-11-09-maturation-implementation-progress.md).

## Entregas verificadas nesta retomada

- [x] Recuperar a sessão anterior e identificar o plano aprovado e sua revisão.
- [x] Preservar R01–R20, incluindo os pedidos acrescentados depois da aprovação.
- [x] Acrescentar T8–T13 com âncoras existentes, dependências e critérios de aceite.
- [x] Salvar arquitetura, análises e continuidade em commit; `e34b318` na branch
  de implementação, incorporado como `2976999` em develop.
- [x] Push da branch `feat/messages-triage` com o planejamento e o hotfix.
- [x] Preservar 73 mensagens do usuário em ordem cronológica, incluindo pedidos
  posteriores, autorizações e a solicitação dos nomes das abas.
- [x] Criar e enviar ao remoto o snapshot do código incompleto:
  `checkpoint/messages-maturation-2026-11-10`, commit `c9cc7f4` (61 arquivos de
  código/checkpoint, incluindo arquivos novos). O worktree original foi mantido.
  Esse snapshot é explicitamente WIP e não deve ser publicado como release.
- [x] Confirmar a causa da queda: OOM do build seguido de parada do scope tmux
  inteiro por `OOMPolicy=stop`.
- [x] Observar teste de regressão falhar; corrigir o lançamento com
  `--property=OOMPolicy=continue`; executar 6 testes do terminal com sucesso.
- [x] Revisão independente do hotfix e dos documentos, sem achados bloqueantes.
- [x] Aplicar `OOMPolicy=continue` também ao scope já ativo por drop-in em `/run`.
  A alteração direta por `systemctl set-property` foi recusada e não aplicada.
- [x] Deploy apenas do bridge: release `terminal-oom-0343e23`, saúde HTTP 200.
- [x] Verificar mesmos PIDs do servidor tmux e dos três panes após deploy;
  as três sessões voltaram conectadas. Nenhuma sessão foi encerrada pelo deploy.
- [x] Criar instância tmux em socket isolado e verificar que seu novo scope
  usa `OOMPolicy=continue`; encerrar somente essa instância de teste.

Evidência operacional: `/root/.forgehub/releases/terminal-oom-0343e23/release.json`
e `live-policy.json`. O release registra diretório anterior, checksum e rollback.
O hotfix impede a parada em cascata pelo systemd; não garante sobrevivência de
um processo escolhido diretamente pelo kernel em falta de memória.

## Pedido adicional: nomes e conexão das sessões do terminal

- [x] Reproduzir ausência dos nomes salvos na lista de Controle do Sistema.
- [x] Usar os metadados persistidos já compartilhados com as abas do Workspace.
- [x] Mostrar nome como identificação principal e UUID como detalhe.
- [x] Reabrir a sessão com o mesmo ID e nome; nomear a confirmação de encerramento.
- [x] Substituir “Órfã” por “Sem conexão”, sem inferir abandono ou fim do processo.
- [x] Reproduzir a classificação errada com dois clientes tmux conectados e
  corrigir a condição para qualquer quantidade maior que zero.
- [x] Cobrir nome ausente, falha dos nomes, erro da listagem e confirmação destrutiva.
  Seleção executada: 10 testes de UI e 9 testes de bridge passaram.
- [x] Suíte completa do frontend: 108 arquivos e 502 testes passaram, com um worker.
- [x] Executar auditoria estática: 50 achados no repositório; nenhum nos arquivos
  alterados da lista de sessões. Não confundir esse resultado com auditoria geral
  aprovada; os achados fora do escopo permanecem pendentes.
- [x] Build, TypeScript e locales passaram com heap de 2560 MB, após a tentativa
  inicial insuficiente de 1536 MB; o tmux permaneceu ativo.
- [x] Navegador desktop/mobile: nomes, estados, confirmação, Escape e foco passaram.
- [x] Revisão independente e commit `be4677f`; deploy isolado de frontend/bridge.
- [x] Verificar HTML exato servido, imagem `fh-be4677f`, proxy de autenticação,
  saúde e preservação do backend; nomes reais existentes confirmados no banco.
  A abertura com mesmo ID/nome foi exercitada no teste da página. O navegador
  isolado usou dados simulados; não houve execução destrutiva em produção.

Comprovantes e screenshots: [evidências do terminal](evidence/2026-11-10-terminal/verification.md).
O primeiro rollout da UI foi revertido pelo healthcheck incorreto; a repetição
corrigida passou. O release atual do bridge é `terminal-names-be4677f` e carrega
também a proteção OOM anterior.

Este pedido é R21, posterior ao checkpoint original. Adicioná-lo não substitui
nem conclui o escopo principal abaixo.

## Escopo principal: pronto no código não significa aceito/publicado

| Etapa | Encontrado no worktree `messages-triage` | O que impede marcar concluída |
|---|---|---|
| T1 · Etiquetas, legenda e encerramento factual | Classificador, catálogo, painel, traduções e perguntas nos grupos de Pessoal | Navegador/teclado, revisão integrada e publicação |
| T2 · Recuperação de espera/evento | Sweep periódico, intenção persistida, varredura justa e migration | Regressão final, revisão de admissão/concorrência e migration em produção |
| T3 · Comandos/ciclo recuperáveis | Recibos/hash, versão de contexto, decisões pendentes e efeitos transacionais | Casos restantes de recuperação, migration/restore, revisão e publicação |
| T4 · Ajuda contextual à decisão | Enriquecimento limitado e fallback factual | Qualificação integrada, revisão e publicação |
| T5 · Executor compatível/paralelismo | Elegibilidade compartilhada e revalidação na reserva | Política de origem completa, concorrência, recursos e capacidades efetivas |
| T6 · Continuidade multicanal | Continuação ligada à tarefa canônica, contexto atual, tentativa própria e resposta tardia | Revisão de incerteza/consumidor/transporte, regressão final e publicação |
| T7 · Supervisão e entrega aceita | Supervisão por tarefa, ciclo ausente e verificação real do dossiê | Ponta a ponta, serviço real, revisão, integração, restauração e aceite |
| T8 · Runtime contextual/skills | Análise e pacote de trabalho no plano | Implementação do contrato aditivo, skills por CLI e prova de conteúdo/capacidade |
| T9 · Delegação nativa | Requisitos/pacote no plano | Limites, isolamento, contexto, integração e provas por runtime |
| T10 · Aprendizagem/contexto | Histórico, matriz e plano versionados; política descrita | Recuperação executável e exemplo de aprendizagem com evidência/revisão/versionamento |
| T11 · Service Factory/rotinas | Modelos existentes, arquitetura e lacunas identificadas | Evidência por linha, serviço/ocorrência real, documentação e fechamento ponta a ponta |
| T12 · SSH/navegador | Infraestrutura existente e contrato descrito | Acesso efetivo por runtime, página compartilhada, grants atuais e resultado incerto |
| T13 · Terminal/validação resiliente | Hotfix OOM publicado e scope atual corrigido | Continuar validação pesada em sequência e preservar checkpoint a cada etapa |

- [ ] Recuperar a falha da regressão backend interrompida; o log anterior não tem
  resumo final. Não chamá-la de suíte aprovada.
- [ ] Reexecutar o build da implementação principal em separado: o anterior
  terminou em `Killed`. Build da correção pontual não qualifica o worktree maior.
- [ ] Concluir os cenários de cancelamento/resultado incerto e de continuidade
  de serviços listados na auditoria do pipeline.
- [ ] Concluir testes/migrations/backup/restore/revisão do escopo a publicar.
- [ ] Commit/push/deploy dos artefatos exatos; verificar estado e flags reais.
- [ ] Manter gestor automático desabilitado até qualificação específica.
- [ ] Conferir R01–R21 antes de declarar a entrega completa.

## Regra de retomada

Abrir este checklist e a matriz antes de modificar código. O trabalho principal
continua em `/root/project/forgehub/.claude/worktrees/messages-triage`; não limpar
nem substituir suas alterações pendentes. Develop contém outras alterações de
Filenest/ECO047 que não fazem parte da publicação pontual do terminal.

Depois de cada etapa, registrar decisão, arquivos/commit, comando e resultado,
estado real de publicação, pendências e primeira próxima ação. Preservar os
pedidos posteriores e as decisões, sem reduzir o objetivo ao que já passou.

## Retomada de finalização — 10/11, validação em andamento

- [x] Reproduzir e corrigir regressões de admissão: preservar tarefas comuns,
  exigir elegibilidade de missão quando aplicável e usar a execução vinculada.
- [x] Cancelamento do runtime só se torna final após observar a saída do processo;
  processo resistente a TERM permanece identificado como ativo.
- [x] Resultado `stale` preserva identidade e exige reconciliação antes de repetir.
- [x] Evidência `host:<uuid>` verifica vínculo à tentativa canônica e resultado
  de todas as máquinas; admite relatório apenas da tentativa correspondente.
- [x] Implementar pedido de aceite, decisão de critério e decisão humana pelo
  mecanismo existente de governança; conferir SHA-256 real e contrato da entrega.
- [x] Seleção de backend: 17 testes passaram; UI: 47 testes em 4 arquivos passaram.
- [x] Ruff configurado passou. Regressão backend anterior: 2.140 passaram, 21
  ignorados e 1 falhou; a falha de auditoria de credencial foi corrigida e seu
  cenário passou na seleção de 17. Ainda falta repetir a suíte integral.
- [x] Regressão completa do checkpoint: 2.147 passaram, 21 ignorados.
- [x] Revisão independente identificou dez falhas importantes; os casos foram
  reproduzidos e o passe dirigido após correção passou: 135 backend, 29 UI.
  Veja [achados e evidências](../reports/2026-11-10-mission-release-review.md).
- [ ] Qualificar migrations e ponta a ponta no candidato que incorpora a Maia.
- [ ] Executar novamente regressão integral, build e navegador da integração.
- [ ] Revisão final, publicação da integração e conferência do release servido.

A política de aceite foi aplicada **somente ao banco isolado de testes**.
A integração continua sem deploy; o release pontual do terminal permanece ativo.
T8–T12 permanecem no plano e não foram concluídas por esta seleção de testes.
