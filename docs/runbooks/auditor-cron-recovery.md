# Recuperação do Auditor e do cron do Athos

## Estado verificado em 2026-10-04

- Hermes Agent `v0.21.5+6146.g46904a3.dirty`, gateway multiplex ativo e scheduler com heartbeat recente.
- `hermes update --check` terminou com código 0 e informou atualização disponível. A falha antiga de lock da ref Git não se repetiu; nenhuma atualização foi instalada.
- `daily_hermes_update_check` (`e6423c0296cf`) executado manualmente às 19:43 BRT: `ok`.
- `foundation-clear` (`b5fd19ff7a16`) executado manualmente às 19:45 BRT: `ok`, sem erro de `ruamel`.
- `ecosystem-weekly-audit` (`2718ef651fec`) executado manualmente às 19:46 BRT: job `ok`, agenda `0 19 * * 0`. Gravou 52 runs `requested_by=cron` no ForgeHub: 39 `ok` e 13 `fail`. O scheduler saudável e os checks falhos aparecem separadamente.
- O job desativado `cron-worker-smoke-test` (`a4c7594034c9`) foi removido após conferir que só havia referência em saída histórica.
- Verificador v2 instalado em `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`; cópia anterior em `/tmp/checklist_verifier.py.pre-v2-20261004`. Store anterior em `/tmp/athos-jobs.pre-v2-20261004.json` (modo 0600).
- Migrações `ae4d91c72b60` e `c84e2f619ab0` aplicadas ao schema `company`. As duas linhas legadas de `company.cron_scripts` foram preservadas em `/tmp/forgehub-legacy-cron-rows-20261004.jsonl` (modo 0600) antes da reconciliação.

## Execução e diagnóstico

1. Consultar `hermes --profile athos cron status` e o último estado do job `ecosystem-weekly-audit`.
2. Conferir `GET /api/v1/audit/status`: `athos_monitor` descreve a saúde do scheduler; o resumo de checks descreve as falhas individuais.
3. Para repetir o cron pelo CLI instalado: `hermes --profile athos cron run 2718ef651fec`. Isso cria evidências novas; usar só quando uma nova execução for necessária.
4. Para investigar um check, consultar o último run no ForgeHub e executar `python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-NNN`. O comando grava resultado no checklist do Hindsight.
5. Se o store de cron estiver corrompido, preservar o arquivo atual antes da restauração. Nunca imprimir prompts, tokens ou destinos do `jobs.json` em logs ou commits.

## Falhas e ativações pendentes

- O catálogo v2 mantém `ECO-048`, `ECO-050`, `ECO-055`, `ECO-056` e `ECO-058` desabilitados até haver as provas descritas no plano. `ECO-058` depende do primeiro snapshot externo e de uma restauração de amostra; o backup continua adiado.
- A primeira execução dos checks novos encontrou perfis Kairos/Lara incompletos (`ECO-042/043`), permissões amplas em `.env` do ForgeVault (`ECO-019`), interfaces e documentação pública fora da allow-list (`ECO-047`) e rotação de logs/limite de cache sem política aprovada (`ECO-039`). Cada falha deve ser tratada por seu responsável, mantendo o check vermelho até nova evidência.
- Permanecem sem script de reparo automático os checks de voz `ECO-040/041`; a recuperação SQL manual de `ECO-012` ainda precisa de um artefato validado. Nenhuma remediação foi inventada para esses casos.

Nenhum deploy do Darckware faz parte deste procedimento.
