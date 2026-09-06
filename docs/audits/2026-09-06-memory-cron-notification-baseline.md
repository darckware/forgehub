# Baseline P0 — memória, crons e notificações

**Data da coleta:** 2026-09-06  
**Ambiente:** local  
**Estado:** auditoria inicial; nenhuma restauração, compactação ou correção executada.  
**Plano:** [gestão de memória coletiva](../superpowers/plans/2026-09-06-collective-memory-governance.md)

## Resultado executivo

Foram confirmados problemas operacionais em memória curta e crons. A origem exata da perda
relatada ainda precisa ser delimitada antes de restaurar dados. O planejamento local/VPS do
Claude continua sendo uma dependência para qualquer alteração de arquitetura ou infraestrutura.

| Prioridade | Fluxo | Fonte de verdade observada | Evidência | Diagnóstico atual | Próxima ação segura |
|---|---|---|---|---|---|
| P0 | Memória curta Aegis | Configuração e `memories/MEMORY.md` do perfil | 2.195/2.200 caracteres, 10 entradas, round-trip válido | Capacidade crítica confirmada | Aegis propõe consolidação após backup, sem apagar fontes duráveis |
| P0 | Perfil do operador em Aegis, Daedalus e Hephaestus | Configuração e `memories/USER.md` de cada perfil | 3.342/1.375 caracteres, uma entrada por perfil, round-trip válido | Limite excedido em três perfis | Cada proprietário corrige o próprio arquivo; comparar a entrada compartilhada com a fonte autorizada |
| P0 | Scheduler Athos | `/root/.hermes/profiles/athos/cron/jobs.json` | 9 jobs atuais; 7 em erro | Scheduler amplamente degradado | Diagnosticar e corrigir o executor Hermes antes de reativar rotinas |
| P0 | Execução restart-safe | Estado dos jobs | Erro comum: `systemd-run --user --scope is unavailable` | Causa dominante dos erros atuais; ainda não corrigida | Validar serviço/sessão systemd e contrato da versão instalada do Hermes |
| P0 | Retenção Hindsight | Job `523651ba9c5e` e diretório de scripts | Job habilitado; `/root/.hermes/profiles/athos/scripts/hindsight_prune.py` ausente | Cadastro incompleto confirmado | Recuperar ou implementar o script a partir de requisito aprovado; manter job sem execução até teste |
| P1 | Backup semanal | Job `2f917a71a212` e `weekly_backup.sh` | Arquivos compactados passam em `zstd -t`, mas o `tar` não lê dois diretórios PostgreSQL atuais por permissão | Excludes apontam para topologia antiga; stderr oculto e pipeline encerra antes da retenção | Conciliar caminhos com o plano do Claude, corrigir excludes/log e testar restauração |
| P1 | Notificações de cron | `backend/app/api/routes/notifications.py` | O ingestor cria notificação para sucesso e falha | Incompatível com alerta por exceção | Alterar produtor e testes para registrar somente condições acionáveis |
| P1 | Feedback de Messages | `backend/app/core/feedback.py` | Conclusão normal pode criar notificação interna | Regra antiga diverge da orientação atual | Separar devolução de resultado de alerta e preservar idempotência |
| P1 | Hindsight | Banco `foundation`, schema `hindsight` | 17.028 unidades, 2.179 documentos, banco com 407.804.951 bytes | Baseline de capacidade; não mede qualidade | Auditar duplicação/proveniência antes de qualquer prune |
| P2 | Caminhos de conhecimento | Hooks e manifestos | Referências ativas ainda usam links antigos em `/root/.hermes` | Compatibilidade funciona, contexto está desatualizado | Cada runtime atualiza sua configuração após conciliação com o plano do Claude |
| P2 | Documentação de cron | `docs/screens/crons.md` e código atual | Documento menciona truncamento; código atual preserva prompt completo | Documento desatualizado | Corrigir documentação junto da implementação validada |

## Comparação das fontes de cron

| Fonte | Data observada | Hash SHA-256 | Jobs | Interpretação |
|---|---|---|---:|---|
| `athos/cron/jobs.json` | 2026-09-05 | `c58d4fea7ace518a187a5e1e8d7b62aacfbb38424b665b339f49a939a7c05271` | 9 | Estado atual |
| `athos/cron/.jobs.json.good` | 2026-09-06 | mesmo hash do atual | 9 | Cópia parseável atual; não é prova de completude |
| Snapshot pré-update | arquivo observado em 2026-08-17 | `0ff29d4998066e617b0ae753854cd1cf5ac2c7890bf9f27617269e26feed8a9b` | 6 | Histórico antigo, insuficiente para restauração integral |
| Curadoria 2026-08-18 | 2026-08-17 | `a608283d11aab431c49d85a9be97dea71590ab3dfdd10a398f4a7591816ddf23` | 13 | Contém cinco jobs ausentes hoje |
| Curadoria 2026-08-25 | 2026-08-25 | `fad885650031b7478944c84ad2c5deda969073dd341e1edc248a1f99490aaba9` | 8 | Os cinco jobs já não aparecem |
| Curadoria 2026-09-01 | 2026-09-01 | `a10237d55d5efad1d30899047563e15a7554964fe20aab418fb7254bcfc21381` | 9 | Mesmo conjunto funcional atual, incluindo Hindsight prune |

Jobs presentes somente na cópia de 18/08:

- `kairos-outbound-check` — desabilitado no backup;
- `kairos-intel-scan` — desabilitado;
- `kairos-proposal-queue` — desabilitado;
- `kairos-partner-ping` — desabilitado;
- `athos-inbox-monitor` — habilitado no backup.

Não há referência ativa a esses cinco nomes fora da cópia de 18/08 entre os diretórios
operacionais consultados. Eles já estavam ausentes na cópia de 25/08. Isso não comprova perda
nem retirada deliberada; portanto, não devem ser restaurados sem evidência adicional.

O conjunto de campos funcionais da cópia de 01/09 coincide com o atual após remover apenas
telemetria de execução. Não foi detectada perda de cadastro depois desse backup. O job
`hindsight-daily-prune` apareceu após a cópia de 25/08, mas foi cadastrado sem o script que
seu prompt manda executar.

## Estado atual dos nove jobs do Athos

| Job | Estado observado | Falhas consecutivas | Observação |
|---|---|---:|---|
| Battery monitor | erro | 2.432 | Falha restart-safe; alta repetição |
| foundation-clear | ok | 0 | Última execução observada em 30/08 |
| ai-news-noon | erro | 2 | Falha restart-safe |
| ecosystem-weekly-audit | ok | 0 | Última execução observada em 30/08 |
| db-integrity-healthcheck | erro | 3 | Falha restart-safe |
| memory-maintenance | erro | 3 | Falha restart-safe; rotina também não cobre limites curtos de todos os perfis |
| weekly-backup | erro | 2 | Script saiu com código 1 |
| Hermes Daily News | erro | 2 | Falha restart-safe |
| hindsight-daily-prune | erro | 2 | Falha restart-safe e script ausente |

O valor 2.432 do battery monitor indica que o erro não é recente nem isolado. Uma correção
de notificação não resolve a indisponibilidade do executor; ela apenas evita ruído enquanto
o incidente persiste.

### Causa do executor restart-safe

O gateway Athos roda como serviço **system-level** em
`/etc/systemd/system/hermes-gateway-athos.service`, usuário `root`. Nesse processo,
`systemctl --user` não consegue conectar ao bus. A versão instalada do Hermes, por sua vez,
exige `systemd-run --user --scope` para destacar filhos que precisam sobreviver ao reinício
do gateway e falha de forma fechada quando o user bus não está disponível. A incompatibilidade
entre a forma de instalação do gateway e o contrato do executor é a causa confirmada do erro
comum. A escolha entre mudar a unidade/sessão systemd ou adaptar o mecanismo de isolamento
precisa ser conciliada com o planejamento de ambientes do Claude.

### Causa do backup semanal

Os arquivos `NotebookSTI_2026-W34.tar.zst` e `NotebookSTI_2026-W35.tar.zst` passaram no teste
de integridade do Zstandard. A reprodução de leitura com o mesmo conjunto de excludes falhou
nos diretórios:

- `/root/.hermes/database/data/postgres/pgdata`;
- `/root/.hermes/database/data/postgres-company/pgdata`.

O script exclui caminhos antigos sob `/root/.hermes/foundation/data/postgres/`, mas não esses
diretórios efetivos. Ele também envia stderr do `tar` para `/dev/null`; com `pipefail`, o arquivo
compactado pode ser criado e validado, enquanto o job termina em erro antes de remover a semana
anterior. Há 881 GiB livres no filesystem observado, portanto falta de espaço não explica a
falha atual. A correção deve usar os caminhos finais definidos pelo trabalho local/VPS.

### Estado do prune Hindsight

Duas execuções anteriores, em 02/09 e 03/09, registraram explicitamente que
`hindsight_prune.py` não foi encontrado. O histórico consultado mostra o script como trabalho
pendente antes de o job surgir no cadastro. A evidência aponta para cadastro incompleto, não
para arquivo comprovadamente apagado. O job não deve ser reconstruído a partir do prompt sem
especificação e testes da política de retenção.

## Contagem normalizada das memórias Hermes

A contagem abaixo usa a mesma separação `\n§\n` e normalização do `MemoryStore` instalado.
Todos os arquivos listados fazem round-trip sem desvio textual.

| Perfil | Arquivo | Entradas | Uso | Limite | Estado |
|---|---|---:|---:|---:|---|
| aegis | `MEMORY.md` | 10 | 2.195 | 2.200 | crítico |
| aegis | `USER.md` | 1 | 3.342 | 1.375 | excedido |
| athos | `MEMORY.md` | 1 | 1.045 | 2.200 | normal |
| athos | `USER.md` | 4 | 974 | 1.375 | normal |
| daedalus | `MEMORY.md` | 7 | 1.561 | 2.200 | aviso |
| daedalus | `USER.md` | 1 | 3.342 | 1.375 | excedido |
| hephaestus | `MEMORY.md` | 7 | 1.561 | 2.200 | aviso |
| hephaestus | `USER.md` | 1 | 3.342 | 1.375 | excedido |
| lara | `MEMORY.md` | 1 | 411 | 2.200 | normal |

O conteúdo não foi incluído neste relatório para não promover memória privada a documentação
do projeto. O excesso precisa ser corrigido na origem pelo proprietário, com backup e revisão.

## Restrições de execução

- Não restaurar os cinco jobs históricos sem confirmação da finalidade e do responsável.
- Não executar o prune Hindsight enquanto o script, backup e critérios de preservação não forem testados.
- Não compactar arquivos privados de outros agentes a partir deste trabalho do Codex.
- Não alterar caminhos, compose, bridge, identidade ou schema antes da conclusão e conciliação
  do planejamento local/VPS do Claude.
- Não vincular a execução aos três projetos de teste encontrados no ForgeHub. Um projeto oficial
  do ForgeHub não apareceu na listagem atual e precisa ser criado pelo fluxo correto.

## Critérios para fechar o P0

1. Origem da retirada dos cinco jobs históricos classificada com evidência.
2. Executor restart-safe recuperado e testado sem produzir notificação de sucesso.
3. Script de retenção Hindsight presente, revisado, testado em dry-run e com restauração comprovada.
4. Backup semanal executado e restaurado em amostra controlada.
5. Aegis, Daedalus e Hephaestus entregam evidência da manutenção dos próprios arquivos.
6. Matriz de alertas por exceção aprovada e implementada nos produtores.
7. Planejamento local/VPS do Claude conciliado antes das alterações dependentes.
