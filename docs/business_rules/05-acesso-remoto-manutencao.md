# 05 — Acesso remoto e manutenção

Base: `main` em `43a6a7f`. Esta página não concede acesso a máquinas; autorizações
são avaliadas pelo ForgeHub em cada operação e dependem do principal e do alvo.

**Decisão posterior ao commit-base:** a política publicada na Foundation em
14/11/2026 autoriza a exceção de desenvolvimento abaixo e prevalece sobre a seção
inativa de 13/11. Fonte: `/root/.hermes/foundation/52_policies/REMOTE_ACCESS_RULE.md`,
seção `Active development policy`, e `47_migrations/2026-11-14-development-access.md`.
Isso é autorização procedimental vigente, não prova de transporte instalado.

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| REM-001 | IMPLEMENTADA | Operação de agente exige acesso direto explicitamente concedido, ativo e dentro de validade. Escopo por máquina/grupo e elevação são distintos; `all_machines` inclui máquinas futuras. Escopo de máquina vazio não concede acesso. | `backend/app/api/routes/direct_access.py`; `backend/app/core/deps.py`; `backend/app/tests/test_direct_access.py` |
| REM-002 | IMPLEMENTADA | Para agente, autorização de manutenção pode ser concedida somente por autoridade administrativa e é revogável/auditada. Pausa global de agentes fecha novas operações; ausência do controle ou estado pausado falha fechado. Sessões humanas/terminal do Workspace seguem seu próprio fluxo. | `backend/app/api/routes/direct_access.py:255`; `backend/app/core/remote_authority.py`; `backend/app/tests/test_direct_access.py`; `backend/app/api/routes/system_control.py` |
| REM-003 | IMPLEMENTADA | Via API, comando, script ou transferência iniciados por agente precisam corresponder à tarefa/dispatch/run em execução, credencial do agente e máquina autorizada. Não aceite comando livre fora do contexto exato autorizado pela API. Exceção procedimental direta: REM-005. | `backend/app/api/routes/host_execution.py`; `backend/app/core/host_exec_runner.py`; `backend/app/api/routes/demand.py`; `backend/app/tests/test_host_execution.py` |
| REM-004 | IMPLEMENTADA | Acesso de máquina gerenciado pelo ForgeHub usa identidade de serviço darckware, chave/segredo referenciado no ForgeVault e chave pública cadastrada/verificada. A chave privada não é entregue ao agente. | `backend/app/api/routes/host_execution.py:41,376,446`; `backend/app/api/routes/direct_access.py`; `docs/operations/DARCKWARE_FORGEVAULT.md`; `docs/runbooks/MACHINE_VAULT_RECONFIGURATION.md` |
| REM-005 | POLÍTICA | Regra normal é conexão pelo ForgeHub. A decisão publicada em 14/11 permite SSH/scp/rsync direto para Porthus/Claude, Aramis/Codex e Dartan/agy durante desenvolvimento ativo com Marcelo, para host/operação/plugin/caminho e validade finita explicitados. Exige credencial protegida sem acesso do agente à chave e captura confiável independente, verificadas antes da primeira operação; perda da captura bloqueia novas operações. Grants de máquina/escopo, pausa, revogação, expiração e elevação continuam obrigatórios. Task/run são dispensados apenas nesse modo direto autorizado; seguem exigidos pela API. | Foundation `52_policies/REMOTE_ACCESS_RULE.md`, `47_migrations/2026-11-14-development-access.md`; companion em `.claude/worktrees/development-access-rule/docs/plans/development-access-foundation.md` |
| REM-006 | IMPLEMENTADA | Transferência de arquivo é confinada aos diretórios da tarefa/execução, rejeita destinos fora da raiz permitida e valida limites e hash. Limite e restrições específicas (como Windows) são enforcement, não sugestão do agente. | `backend/app/api/routes/host_execution.py`; `backend/app/tests/test_host_execution.py` |
| REM-007 | PARCIAL | Detecção textual de `sudo`/`docker` e modos de elevação não equivalem a sandbox de sistema operacional. Alteração de parser/policy deve preservar negação por padrão e cobrir comandos compostos, shell e caminhos alternativos. | `backend/app/api/routes/host_execution.py`; `backend/app/tests/test_host_execution.py` |
| REM-008 | GAP | O commit-base não inclui tela/MCP colaborativos nem brokering de credencial/captura para o modo direto. O backend colaborativo não integrado exige Task/run e comandos exatos para a API; não é pré-requisito documental da exceção direta aprovada. Confirme transporte protegido e captura realmente disponíveis antes de operar; nunca leia chave privada para suprir a lacuna. | Base `43a6a7f`; `backend/app/api/routes/host_execution.py`; política posterior REM-005 |

## Instruções para agentes

- Antes de toda operação remota confira principal, grant atual, pausa global, alvo,
  tarefa/run, limites do comando e segredo referenciado. Autorização em tela ou
  autorização para uma máquina não é consentimento para todas as máquinas.
- Não exponha chave privada, senha ou token em prompt, argumento, log, artefato ou
  saída de ferramenta. Identificador de segredo não substitui validação de acesso.
- Falha de execução não autoriza relaxar a regra de forma temporária ou permanente.
  Investigue a causa, corrija enforcement e preserve auditoria antes de nova tentativa.
- No modo direto autorizado, confirme REM-005 e seus pré-requisitos verificáveis.
  Falha exclusiva de Task/run/transporte da API não revoga essa exceção, mas nunca
  contorne recusa de máquina, escopo, pausa, revogação, expiração ou elevação.
- Operação humana no terminal Workspace e operação autônoma de agente têm modelos de
  autorização distintos; não os misture ao alterar a pausa ou o grant.

## Referências

- [Regra de acesso remoto](../architecture/REMOTE_ACCESS_RULE.md)
- [Runbook de Vault das máquinas](../runbooks/MACHINE_VAULT_RECONFIGURATION.md)
- [Darckware e ForgeVault](../operations/DARCKWARE_FORGEVAULT.md)
- `backend/app/api/routes/host_execution.py`, `agent_access.py`, `agent_control.py`.
