# Acesso dos agentes aos sistemas sem login

Pedido do Marcelo em 03/11/2026. Implementado primeiro no ForgeHub. Vale para todos os sistemas do ecossistema.

## O que todo sistema precisa ter

O agente entra na API e **nas telas** sem login, senha ou 2FA, para testar telas e fazer manuais. A credencial fica no ForgeVault. Quem pode entrar, e o que pode ver, é configurado no próprio sistema, e todo acesso fica auditado.

A regra da credencial é a da Foundation: `36_governance/APPLICATION_AGENT_ACCESS.md`. Este documento acrescenta a entrada nas telas, o controle por agente e a auditoria.

### 1. Credencial
- Cada agente entra com o **próprio token**. Não existe conta compartilhada: o `svc-agente` foi descontinuado pelo Marcelo em 04/11/2026.
- Um token por agente em cada sistema, para o sistema saber quem acessou. O sistema guarda só o hash.
- O token fica no ForgeVault: organização `darckware`, projeto do sistema, ambiente `Production`, com os ids em `~/.config/forgevault/<sistema>-forgevault.json`.
- Cada agente lê só o próprio token, por concessão própria no ForgeVault.
- O agente não é usuário do sistema e não passa pelo formulário de login.

### 2. Entrada nas telas
- Uma rota troca o token por uma sessão de navegador, igual à de uma pessoa.
- Sessão curta (30 minutos), sem renovação e sem "manter conectado".
- Sem reCAPTCHA e sem 2FA, porque o token já substitui os dois.
- A rota de renovação de sessão não pode estender essa sessão nem tirar os limites dela.

### 3. Controle de acesso
- Somente leitura por padrão. Escrita exige aprovação do Marcelo para aquele sistema.
- O limite é aplicado **no backend**. Não basta esconder botão, e não basta o perfil se as rotas não conferem permissão.
- Recusar por padrão: lista explícita de áreas abertas. Área nova começa fechada.
- Sempre fechados: dados pessoais, conversas, mensagens entre agentes, memórias, arquivos, documentos, scripts, terminal, segredos, cadastro de usuários e administração.
- Antes de abrir uma área, leia cada `GET` dela: procure `GET` que grava dados ou que devolve conteúdo privado. A revisão do ForgeHub (#41917) achou os dois casos e reprovou a primeira versão, que abria áreas inteiras.
- Controle por agente, em uma tela do sistema, só para administrador: liberar, bloquear, ver a última sessão e as conexões abertas, encerrar conexões.
- Bloquear o agente, remover o perfil dos agentes ou revogar o token encerra a sessão aberta na requisição seguinte.
- Testes que gravam dados acontecem no ambiente de teste do sistema, nunca em produção.

### 4. Auditoria de acesso
Campos: agente, evento, alvo ou motivo, IP, navegador, data e hora. Eventos mínimos:

| Evento | Quando |
|---|---|
| `session_opened` | Sessão aberta |
| `session_refused` | Tentativa recusada, inclusive com token desconhecido |
| `area_read` | Primeira leitura de cada área na sessão, sem registrar cada requisição |
| `request_denied` | Tentativa de gravar ou de abrir área fechada |
| `access_changed` | Administrador liberou ou bloqueou um agente |
| `sessions_ended` | Administrador encerrou as conexões de um agente |

Nunca gravar o token, o corpo da requisição nem parâmetros de busca. Caminho, navegador e IP vêm do cliente: limpe o que parecer token, valide o IP e registre tentativas repetidas uma só vez. Mostrar a auditoria em tela, com filtro por agente.

### 5. Checklist de pronto
- [ ] Token de cada agente criado; hash no banco, valor só no ForgeVault
- [ ] Segredos e ids registrados; agentes com concessão própria
- [ ] Rota que abre sessão, com 30 minutos e sem renovação
- [ ] Bloqueio no backend de gravação e de área fechada
- [ ] Tela de controle por agente e tela de auditoria
- [ ] Testes: token errado e revogado, gravação recusada, área fechada, bloqueio encerra sessão, renovação não estende, auditoria completa
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
| Dono da sessão e perfil | Migration `a3f1c7d92e04`: `user_sessions.agent_id`, sem usuário compartilhado. Perfil `Agente leitura` define os módulos |
| Áreas abertas | Produtos, Projetos, Tarefas, Missões, Planejamento, Pipelines, Cockpit, Linhas de serviço e a lista de agentes. Mensagens, Canais, Documentos, Foundation, Auditoria e Atividade dos agentes ficam fechados |
| Testes | `backend/app/tests/test_agent_screen_session.py` |

No ForgeHub o token é a credencial `agt_` de cada agente. A sessão pertence ao próprio agente, e os módulos que ele vê vêm do perfil `Agente leitura`, editável em Perfis.

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
