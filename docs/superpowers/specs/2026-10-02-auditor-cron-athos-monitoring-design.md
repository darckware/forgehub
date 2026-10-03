# Auditoria, Cron e Monitoramento do Athos — Especificação

**Data:** 2026-10-02  
**Status:** Aprovada como direção; aguardando revisão do documento antes do plano de implementação  
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
