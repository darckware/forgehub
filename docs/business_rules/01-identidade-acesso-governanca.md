# 01 — Identidade, acesso e governança

Base: `main` em `43a6a7f`. O status descreve o enforcement no código desse commit.

## Identidade e sessão

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| IAM-001 | IMPLEMENTADA | Pessoa só recebe sessão normal após autenticação válida, conta ativa e verificação de CAPTCHA; se TOTP estiver habilitado, conclui TOTP antes de receber a sessão normal. O bootstrap de desenvolvimento configurado pode criar a identidade administrativa quando ainda não há usuário correspondente. | `backend/app/api/routes/auth.py:90,120`; `backend/app/tests/test_auth.py:45` |
| IAM-002 | IMPLEMENTADA | Sessão tem dono único (pessoa ou agente), validade e revogação; o banco guarda hash do identificador. A sessão humana pode renovar enquanto válida; a sessão de tela do agente não se renova em `/auth/me`. | `backend/app/core/user_session.py:20,44`; `backend/app/db/models/user_session.py:12`; `backend/app/api/routes/auth.py:221` |
| IAM-003 | IMPLEMENTADA | Token de agente identifica o agente pelo UUID da credencial; credencial revogada/expirada ou agente inativo é recusado. O valor em texto puro só é entregue na emissão, enquanto o banco guarda o hash. Emissão/revogação é administrativa. | `backend/app/core/deps.py:32`; `backend/app/api/routes/governed_approval.py:224`; `backend/app/db/models/agent.py:239`; testes `test_auth.py`, `test_governed_authority.py` |
| IAM-004 | IMPLEMENTADA | A sessão de tela de agente é própria daquele agente, dura no máximo 30 minutos e é somente leitura nas rotas explicitamente permitidas. Não é identidade humana nem autoriza escrita; acesso à tela precisa estar habilitado por administrador. Revogar a credencial ou desativar o agente encerra a sessão no próximo pedido. | `backend/app/api/routes/auth.py:160`; `backend/app/core/agent_session.py:31,106`; `backend/app/tests/test_agent_screen_session.py:73,183` |

## Permissões e delegações

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| IAM-005 | IMPLEMENTADA | Administrador gerencia perfis. Perfil pode definir permissões de módulo (`view/query/write/delete`) e ações sensíveis de uma lista conhecida; ação sensível desconhecida é recusada. | `backend/app/api/routes/profiles.py:34,47,124`; `backend/app/db/models/profile.py:19` |
| IAM-006 | GAP | **Não assuma que permissões do perfil protegem globalmente toda rota.** A checagem de módulo ocorre nas rotas que chamam explicitamente `require_perm`; o middleware global exige autenticação, mas não aplica automaticamente a matriz de módulos. Antes de adicionar ou alterar uma rota, confirme a dependência usada e acrescente teste de acesso permitido/negado. | `backend/app/main.py:296`; `backend/app/core/deps.py:68,178`; `backend/app/db/models/profile.py:1`. A documentação do perfil descreve um modelo mais amplo que o middleware atual. |
| IAM-007 | IMPLEMENTADA | Ação de agente é negada sem delegação ativa, dentro do período, com a ação exata, escopo de produto/projeto, limite de risco e orçamento aplicáveis. Ação desconhecida, escopo de máquina vazio ou delegação revogada não concede acesso. | `backend/app/core/deps.py:102`; `backend/app/api/routes/governed_approval.py:142`; `backend/app/tests/test_governed_authority.py:161` |
| IAM-008 | IMPLEMENTADA | Uma pessoa com autoridade adequada concede a delegação; para manutenção de máquinas, execução de navegador e gestão de rotinas, a concessão é administrativa. Outorgante ou administrador pode revogá-la; a mudança é auditada. | `backend/app/api/routes/governed_approval.py:147,155,197`; testes `test_governed_authority.py` |
| IAM-009 | IMPLEMENTADA | Executor não aprova o próprio trabalho quando a decisão exige independência. A decisão usa a regra específica de aprovação governada e grava a trilha antes de notificações best-effort. | `backend/app/api/routes/governed_approval.py:81,109`; `backend/app/tests/test_task_governed_approval.py:343` |
| IAM-010 | IMPLEMENTADA | Eventos de auditoria de governança são append-only pela API: há leitura e criação, sem rota de alteração ou exclusão do histórico. | `backend/app/api/routes/governance.py`; teste `backend/app/tests/test_governance.py` |

## Como aplicar ao implementar

- Em toda rota nova, declare e teste a dependência de autenticação, o tipo de principal,
  o escopo da delegação e a permissão específica. Não dependa apenas de a tela esconder
  um botão.
- Separe identidade humana, credencial de agente, sessão de tela de agente e delegação;
  uma não substitui a outra.
- Em decisões governadas, teste recusa de autoaprovação, identidade do aprovador,
  expiração/revogação e efeito persistido. Falha de notificação não deve desfazer uma
  decisão já confirmada.
- Se uma mudança ampliar o middleware para aplicar permissões de perfil globalmente,
  trate IAM-006 como mudança de segurança com teste de compatibilidade por rota; não
  documente esse enforcement antes de existir.

## Referências

- Arquitetura e precedência documental: [`docs/README.md`](../README.md#hierarquia-de-autoridade).
- Modelo de delegação e aprovação: `backend/app/db/models/governance.py` e
  `backend/app/api/routes/governed_approval.py`.
- Regras gerais de sessão de agente: `docs/architecture/AGENT_SCREEN_ACCESS.md`.
