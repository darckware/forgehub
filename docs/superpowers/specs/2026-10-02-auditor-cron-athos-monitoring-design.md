# Auditoria, Cron e Monitoramento do Athos — Especificação

**Data:** 2026-10-02  
**Status:** Aprovada; revisada em 2026-10-02 (conferência + catálogo v2 em proposta)  
**Escopo:** ForgeHub Auditor, ForgeHub Crons, checklist semanal do Athos e scripts operacionais relacionados

## Objetivo

Entregar uma visão operacional única para a saúde da auditoria do ecossistema. A tela Auditor deve mostrar o estado do checklist e do job que o executa; a tela Cron deve mostrar a execução e a integridade dos scripts; o Athos deve permanecer responsável pelo disparo semanal e pela escalada de falhas.

O resultado esperado é detectar rapidamente quatro situações distintas: auditoria saudável, auditoria atrasada ou ausente, check que falhou e cron ou script que não consegue executar. Uma falha de um check não deve ser confundida com uma falha do scheduler.

## Descobertas que orientam o desenho

- O catálogo de verificações ativo no script `checklist_verifier.py` possui `ECO-001` a `ECO-041`; a documentação da tela ainda cita apenas 39 controles.
- O job semanal real do Athos é `ecosystem-weekly-audit`, agendado para domingo às 19:00, e chama `POST /api/v1/audit/run-internal` com o token do bridge.
- A documentação e o módulo da API ainda usam o nome antigo `forgehub-audit-checklist` em alguns textos.
- `foundation-clear` falhou porque o worker externo do Hermes não importou `ruamel.yaml`.
- `daily_hermes_update_check` marcou o cron como erro porque `hermes update --check` retornou código diferente de zero durante uma verificação não destrutiva.
- O frontend da Auditoria e de Cron possui traduções disponíveis, mas grande parte do texto é escrita diretamente em inglês nos componentes.
- O catálogo central de scripts foi descontinuado; o estado canônico agora é por perfil.
- Há remediações históricas que apontam para nomes de scripts não existentes, como `weekly_backup.sh`.

## Princípios

1. **Uma fonte de verdade para o checklist:** o catálogo persistido no ForgeHub deve corresponder ao mapa de checks executável pelo `checklist_verifier.py`.
2. **Scheduler separado do resultado do check:** o job pode executar corretamente e registrar checks falhos; isso não transforma automaticamente o job em erro de infraestrutura.
3. **Evidência preservada:** funções ou checks descontinuados deixam de participar de novas execuções, mas o histórico de runs não é apagado.
4. **Athos como monitor:** o Athos dispara a auditoria e recebe a responsabilidade pela escalada, mas não duplica a lógica de persistência do ForgeHub.
5. **Perfil como escopo:** scripts, jobs e arquivos são resolvidos no diretório do perfil; referências ao catálogo central não serão usadas como fallback.
6. **Operações seguras:** qualquer correção automática continua explícita, limitada e seguida de verificação independente.

## Arquitetura

### Catálogo e ciclo de vida dos checks

O backend mantém os checks e seus runs em `company.audit_checks` e `company.audit_check_runs`. Uma atualização de catálogo reconcilia as entradas persistidas com os IDs presentes no verificador canônico:

- checks canônicos permanecem habilitados quando válidos;
- checks sem implementação correspondente são marcados como descontinuados e deixam de ser enviados para `/run` e `/run-internal`;
- o histórico permanece consultável;
- remediações apontam somente para scripts existentes e aprovados;
- a tela diferencia `ativo`, `descontinuado`, `nunca executado`, `falhou` e `saudável`.

O contrato de execução continua sendo `0 = ok`, código diferente de zero = falha, timeout separado e erro de transporte separado. O resultado do check é sempre persistido com `requested_by` igual a `manual`, `cron`, `athos-remediation` ou `remediation-verification`.

### Monitor do job do Athos

O status operacional da Auditoria passa a incluir um bloco de monitoramento derivado do job semanal do perfil Athos. O monitor valida:

- existência de exatamente um job canônico;
- nome e script esperados (`ecosystem-weekly-audit` / `ecosystem_weekly_audit.sh`);
- agenda esperada (`0 19 * * 0`);
- job habilitado;
- última execução e seu resultado;
- próxima execução;
- idade da última auditoria registrada no ForgeHub.

O estado do monitor será `healthy`, `degraded`, `failed` ou `not_configured`. `degraded` cobre auditoria atrasada, store vazio, script ausente ou divergência de configuração. `failed` cobre falha de execução do scheduler ou falha de transporte que impeça a gravação do run.

O endpoint de status deve retornar o resumo existente dos checks e esse bloco de monitoramento em uma resposta compatível com consumidores atuais. O disparo protegido por `X-Bridge-Token` permanece no endpoint interno; não será criado um segundo endpoint público nem um segundo scheduler.

### Saúde dos Crons

O endpoint de Crons continua lendo os stores por perfil e os logs de execução. A resposta deve tornar explícitos:

- saúde do job (`ok`, `error`, `overdue`, `never_ran`, `off`);
- existência e localização do script no perfil;
- indicação de script descontinuado ou de referência ao catálogo central;
- relação opcional com o job de auditoria do Athos;
- erro do store quando o scheduler não consegue carregá-lo.

O frontend não tenta mais encontrar scripts em uma pasta `central`. Quando o script não existe no perfil, o job aparece como quebrado e com ação de diagnóstico, sem mascarar o problema com um arquivo de outro escopo.

### Tratamento das falhas atuais

As correções operacionais serão separadas das mudanças de produto:

1. Ajustar o runtime usado pelo worker Hermes para disponibilizar `ruamel.yaml` no mesmo ambiente que executa os crons.
2. Alterar `daily_hermes_update_check.py` para tratar `doctor` e verificação de atualização como diagnóstico; apenas falha de execução do próprio script deve resultar em erro do cron.
3. Executar manualmente `foundation-clear`, `daily_hermes_update_check` e `ecosystem-weekly-audit` após a correção e conferir logs e runs persistidos.
4. Remover ou desabilitar o job de smoke test já descontinuado somente depois de criar um snapshot do store e confirmar que não é referenciado por outro fluxo.

Essas operações não colocam credenciais no repositório e não alteram o endpoint do ForgeRouter.

## Experiência da tela Auditor

A página `/auditor` será reorganizada em quatro áreas:

1. **Resumo:** contagem de checks ativos, saudáveis, falhos e nunca executados.
2. **Monitor Athos:** estado, agenda, última execução, próxima execução e ação para abrir Crons.
3. **Checklist:** filtros por categoria, perfil responsável e ciclo de vida; execução manual da lista e de um check.
4. **Evidência:** saída mais recente, histórico limitado, remediação explícita e escalada para Inbox quando a verificação continuar falhando.

Todo texto visível usará i18n existente ou novas chaves nos catálogos português e inglês. Comandos e saídas técnicas continuam em bloco monoespaçado e não serão enviados para o histórico de tradução.

## Experiência da tela Cron

A página `/crons` exibirá um resumo de saúde antes da tabela, destacará jobs com erro, atrasados, sem execução ou script quebrado e identificará visualmente o job de auditoria do Athos. A tabela continuará oferecendo executar, ativar/desativar, redefinir, visualizar o script e enviar contexto ao assistente.

O fluxo de exclusão continuará protegido por confirmação. O fluxo de execução exibirá erro dentro da interface, sem depender de `window.alert`. O editor não oferecerá campos que reintroduzam o catálogo central.

## Compatibilidade e segurança

- O bridge token continua apenas no host e nas variáveis de ambiente existentes.
- O endpoint interno continua fora da autenticação de usuário somente porque valida o token compartilhado.
- Comandos de auditoria continuam sendo executados pelo bridge, com timeout limitado e saída truncada.
- A remediação não será disparada por uma execução normal da auditoria.
- Nenhuma alteração apagará runs históricos automaticamente.

## Critérios de aceitação

1. A Auditoria mostra o estado do job semanal do Athos e diferencia scheduler saudável de check falho.
2. O catálogo exibido e executado corresponde aos checks canônicos atuais; referências descontinuadas não entram em novas execuções.
3. A tela Cron identifica script ausente, store corrompido, job atrasado, job desativado e job saudável sem fallback para catálogo central.
4. `foundation-clear`, `daily_hermes_update_check` e `ecosystem-weekly-audit` executam sem erro estrutural após a correção operacional.
5. A execução semanal registra runs com `requested_by=cron`; execução manual registra `requested_by=manual`.
6. Falha de verificação cria evidência e, quando a remediação não resolve, demanda de Inbox.
7. Testes backend cobrem reconciliação do catálogo, monitor do Athos e classificação de saúde dos crons.
8. Build e testes frontend cobrem o resumo, estados de erro e ausência do fallback central.
9. Deploy, commit e push só ocorrem após os critérios acima e verificação do ambiente implantado.

## Fora do escopo

- Criar um novo scheduler ou serviço de monitoramento independente.
- Alterar o provedor, base URL ou política do ForgeRouter.
- Alterar a retenção do Hindsight.
- Apagar evidência histórica da Auditoria.
- Reintroduzir catálogos centrais de scripts.

## Revisão 2026-10-02 — conferência e catálogo v2

A conferência do plano contra o código, o banco e o host corrigiu quatro descobertas desta especificação:

- O catálogo persistido no ForgeHub **já** é exatamente `ECO-001`…`ECO-041`; ECO-021 está desabilitado (aposentado no `audit.foundation_checklist`). Não há checks obsoletos a reconciliar.
- O `foundation-clear` falhou por `ruamel` em 2026-09-27, mas o runtime já importa o módulo hoje; basta validar.
- O `daily_hermes_update_check` falha por uma causa real (`cannot lock ref 'refs/remotes/origin/main'` no checkout do Hermes). O correto é reparar a ref, não rebaixar o passo para diagnóstico.
- As remediações têm um problema maior que `weekly_backup.sh`: ECO-005/020 reiniciam units por perfil que não existem mais (a política proíbe), ECO-010/012 usam containers aposentados, e ECO-012/040/041 chamam arquivos inexistentes.

Além disso, o catálogo ficou para trás em relação ao ecossistema. Decisão do Marcelo: criar uma **lista de auditoria atualizada** para o contexto atual e os novos módulos.

### Lacunas do catálogo atual

| Área | Situação em 2026-10-02 | Coberto hoje? |
|---|---|---|
| ForgeVault (web, api, postgres, redis; guarda as chaves) | Fora do ar após o reboot (`restart=no`). Acesso protegido pelo login próprio com 2FA (API 401 para anônimos) | Não |
| Darckware (+ chat do site com a Lara) e CoreTI | Fora do ar após o reboot; só recuperados manualmente | Não |
| Política de restart dos containers | Causa do incidente de 2026-10-02 | Não |
| Backup dos bancos de aplicação (forgehub, forgevault, forgerouter, darckware, coreti, hindsight) | Não existe dump em `/root/backup`, só o arquivo do `/root/.hermes` | Não |
| Acesso remoto (cloudflared, headscale, tailscaled, RustDesk hbbs/hbbr) | Ativos, sem verificação | Não |
| Perfis kairos, lara e prometheus | Profile checks param no themis (ECO-031…038); prometheus existe no disco sem registro de agente | Não |
| Runtimes externos (Porthus/claude, Aramis/codex, Dartan/agy) | Registrados, sem validação de home, arquivos e MCP | Parcial (ECO-004) |
| Telemetria Agent Activity (`hooks.outbound`) | Eventos só de 5 dos 10 perfis Hermes | Não |
| Messages (dispatch travado, falhas, feedback devido) | Sem verificação | Não |
| Chaves ForgeRouter por agente | Sem verificação | Não |
| Retenção do Hindsight (timer novo) | Sem verificação | Não |
| Janela 09:00–23:59 dos crons (ECO-021) | Regra abandonada | Aposentar |

### Catálogo v2 (proposta para aprovação)

Princípios: IDs existentes são mantidos (o histórico continua válido); checks novos começam em `ECO-042`; aposentados não são reutilizados; cada check tem um perfil responsável; um check que falha logo na primeira execução (ex.: backups de banco) é o comportamento esperado e vira pendência, não motivo para afrouxar o check.

**Mantidos, com escopo revisto**

- ECO-007/009/010/017/019 passam a cobrir **todas** as aplicações do host (forgehub, forgerouter, hindsight, forgevault, darckware, coreti), não só o núcleo. ECO-008 continua só para quem precisa da `foundation_network`.
- ECO-039 incorpora o limite do cache de build/imagens Docker (incidente de 2026-09-27).
- Demais mantidos sem mudança: 001–006, 011–016, 018, 020, 022–038, 040, 041.

**Aposentado:** ECO-021.

**Novos**

| ID | Categoria / responsável | Verificação |
|---|---|---|
| ECO-042 | profiles / kairos | Perfil Kairos válido (mesmo contrato de ECO-031…038) |
| ECO-043 | profiles / lara | Perfil Lara válido (hoje falha: falta AGENTS.md) |
| ECO-044 | agents / athos | Todo diretório em `/root/.hermes/profiles` (exceto `default`) e todo runtime externo corresponde a um agente registrado com `runtime_type` (hoje: prometheus sem registro) |
| ECO-045 | containers / hephaestus | Todo container do ecossistema tem `restart: unless-stopped` ou `always`, no compose e no container em execução |
| ECO-046 | backup / daedalus | Cada instância Postgres de aplicação tem dump recente (≤ 8 dias), não trivial e legível |
| ECO-047 | security / aegis | Nenhuma porta de aplicação ligada em `0.0.0.0` fora da allow-list; `/docs`, `/redoc` e `/openapi.json` fechados nos domínios públicos |
| ECO-048 | network / hephaestus | `cloudflared` ativo e cada domínio público responde; a API do ForgeVault responde 401 sem credencial; **credencial de agente só funciona localmente** (Marcelo: "só pode fornecer acesso para os agentes locais via api ou mcp"): o mesmo token de agente recebe 403 pelo domínio público e 200 em `127.0.0.1:8080`, e `/mcp` não é alcançável pelo domínio público. Comportamento confirmado em 2026-10-02 |
| ECO-049 | services / hephaestus | ForgeVault: api pronta, web, postgres e redis saudáveis |
| ECO-050 | services / hephaestus | Darckware: site e API respondem; chat do site com a Lara (`/v1/chat`, `channel=site`) recebe resposta |
| ECO-051 | services / hephaestus | CoreTI: web, api, nginx e postgres saudáveis |
| ECO-052 | network / aegis | Acesso remoto: headscale, tailscaled e RustDesk (hbbs/hbbr) ativos |
| ECO-053 | agents / athos | Todo perfil Hermes tem `hooks.outbound` apontando para `/api/v1/agent-activity/events` com o segredo configurado (verifica configuração, não atividade recente) |
| ECO-054 | agents / athos | Messages: nenhum dispatch `running` além do prazo, nenhum feedback devido há mais de 1 h, taxa de falha da semana abaixo do limite |
| ECO-055 | agents / athos | Runtimes externos: home, arquivos de perfil e MCP `forgehub` configurados para Porthus, Aramis e Dartan |
| ECO-056 | provider / atlas | Todo agente ativo tem chave ForgeRouter configurada e igual ao registro do ForgeRouter |
| ECO-057 | memory / mnemosyne | `forgehub-hindsight-retention.timer` ativo, com última execução bem-sucedida |

O verificador canônico (`checklist_verifier.py`, propriedade do Athos, fora do repositório) e o catálogo persistido do ForgeHub são atualizados juntos: o primeiro ganha as funções, o segundo uma migração de dados que insere `ECO-042`… e desabilita ECO-021. O ECO-025 passa a exigir o novo total.
