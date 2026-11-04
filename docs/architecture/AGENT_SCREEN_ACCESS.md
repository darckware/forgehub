# Acesso dos agentes aos sistemas sem login

Pedido do Marcelo em 03/11/2026. Implementado primeiro no ForgeHub. Vale para todos os sistemas do ecossistema.

## O que todo sistema precisa ter

O agente entra na API e **nas telas** sem login, senha ou 2FA, para testar telas e fazer manuais. A credencial fica no ForgeVault. Quem pode entrar, e o que pode ver, é configurado no próprio sistema, e todo acesso fica auditado.

A regra da credencial é a da Foundation: `36_governance/APPLICATION_AGENT_ACCESS.md`. Este documento acrescenta a entrada nas telas, o controle por agente e a auditoria.

### 1. Credencial
- Conta de serviço **`svc-agente`**, com o mesmo nome em todos os sistemas. Nunca é conta de pessoa.
- Chave própria de cada sistema. O sistema guarda só o hash.
- A chave fica no ForgeVault: organização `darckware`, projeto do sistema, ambiente `Production`.
- Segredos `<SISTEMA>_AGENT_USERNAME`, `<SISTEMA>_AGENT_API_KEY` e `<SISTEMA>_AGENT_BASE_URL`, com os ids em `~/.config/forgevault/<sistema>-forgevault.json`.
- Cada agente recebe leitura por concessão própria no ForgeVault.
- A conta não entra pelo formulário de login.

### 2. Entrada nas telas
- Uma rota troca a chave por uma sessão de navegador, igual à de uma pessoa.
- Sessão curta (30 minutos), sem renovação e sem "manter conectado".
- Sem reCAPTCHA e sem 2FA, porque a chave já substitui os dois.
- A rota de renovação de sessão não pode estender essa sessão nem tirar os limites dela.

### 3. Controle de acesso
- Somente leitura por padrão. Escrita exige aprovação do Marcelo para aquele sistema.
- O limite é aplicado **no backend**. Não basta esconder botão, e não basta o perfil se as rotas não conferem permissão.
- Recusar por padrão: lista explícita de áreas abertas. Área nova começa fechada.
- Sempre fechados: dados pessoais, conversas, terminal, arquivos do servidor, segredos, cadastro de usuários e administração.
- Controle por agente, em uma tela do sistema, só para administrador: liberar, bloquear, ver a última sessão.
- Bloquear o agente, desativar `svc-agente` ou revogar a chave encerra a sessão aberta na requisição seguinte.
- Testes que gravam dados acontecem no ambiente de teste do sistema, nunca em produção.

### 4. Auditoria de acesso
Campos: agente, evento, alvo ou motivo, IP, navegador, data e hora. Eventos mínimos:

| Evento | Quando |
|---|---|
| `session_opened` | Sessão aberta |
| `session_refused` | Tentativa recusada, inclusive com chave desconhecida |
| `area_read` | Primeira leitura de cada área na sessão, sem registrar cada requisição |
| `request_denied` | Tentativa de gravar ou de abrir área fechada |
| `access_changed` | Administrador liberou ou bloqueou um agente |

Nunca gravar a chave, o corpo da requisição nem parâmetros de busca. Mostrar a auditoria em tela, com filtro por agente.

### 5. Checklist de pronto
- [ ] Conta `svc-agente` e chave criadas; hash no banco, valor só no ForgeVault
- [ ] Segredos e ids registrados; agentes com concessão própria
- [ ] Rota que abre sessão, com 30 minutos e sem renovação
- [ ] Bloqueio no backend de gravação e de área fechada
- [ ] Tela de controle por agente e tela de auditoria
- [ ] Testes: chave errada e revogada, gravação recusada, área fechada, bloqueio encerra sessão, renovação não estende, auditoria completa
- [ ] Prova real: abrir as telas no navegador sem digitar senha
- [ ] Linha do sistema atualizada em `APPLICATION_AGENT_ACCESS.md` (pelo Athos)

## Referência no ForgeHub

| Peça | Onde |
|---|---|
| Regras e auditoria | `backend/app/core/agent_session.py` |
| Abertura da sessão | `POST /api/v1/auth/agent-session`, em `api/routes/auth.py` |
| Bloqueio de cada requisição | `RequireAuthMiddleware`, em `backend/app/main.py` |
| Controle por agente e auditoria | `/api/v1/agent-access`, em `api/routes/agent_access.py` |
| Tela | Configurações, `frontend/src/pages/settings/AgentAccessCard.tsx` |
| Conta e perfil | Migration `d5e93a7b2c18`: usuário `svc-agente`, perfil `Agente leitura` |
| Testes | `backend/app/tests/test_agent_screen_session.py` |

No ForgeHub a chave é a credencial `agt_` de cada agente, que já identifica quem acessa. Por isso o controle é por agente, e a sessão roda como `svc-agente`.

### Como o agente abre as telas

```js
const res = await fetch(`${API}/api/v1/auth/agent-session`, {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.FORGEHUB_AGENT_TOKEN}` },
});
const s = await res.json();
await context.addInitScript((state) => {
  localStorage.setItem("forgehub-auth", JSON.stringify({ state, version: 0 }));
}, { token: s.access_token, user: s.user, permissions: s.permissions, actions: s.actions });
await page.goto(`${APP}/cockpit`);
```

Obtenha o token com `/root/.hermes/scripts/forgehub_vault_token.py <agente> <comando>`, que o entrega só ao processo. Nunca grave o token em arquivo.
