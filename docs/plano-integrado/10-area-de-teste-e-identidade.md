# Área de teste e identidade dos agentes pelo ForgeVault

**Pedido do Marcelo (24/10):** "preciso criar uma área de teste; os agentes cadastrados no ForgeVault
podem fazer login direto nos sistemas e serviços, para garantir a segurança e o acesso ao sistema e
serviços."

São duas peças que se apoiam:
- a **área de teste** é onde os agentes trabalham e validam sem tocar a produção;
- a **identidade única no ForgeVault** é como entram em cada sistema, com uma credencial só, de vida
  curta, revogável num lugar e auditada.

## 1. Situação atual (levantada em 24/10)

| Item | Hoje | Problema |
|---|---|---|
| Ambiente de teste | Não existe. O `dev.sh` do ForgeHub usa o **mesmo banco da produção**; os testes automatizados também gravam na produção (agentes de teste "Global Owner/Scoped Owner 95d695fb" ficaram ativos) | Agente validando ou testando altera dado real |
| Credencial do agente no ForgeHub | Token `agt_` por agente (`AgentServiceCredential`), de longa duração | Um token por sistema |
| No Darckware | Token de agente + token aprovador (de propósito diferentes) | Idem |
| No ForgeRouter | Chave de API por agente, importada do registro do ForgeRouter | Idem |
| No CoreTI | Token de API do agente | Idem |
| Nas máquinas (Tailscale) | Chave SSH da conta `darckware`, guardada no ForgeVault, usada pelo host-bridge | Já centralizada; o agente nunca vê a chave (bom) |
| No ForgeVault | Identidades (usuários e contas de serviço), papéis, permissões por segredo, atribuição de MCP, tokens de conta de serviço revogáveis; hierarquia com **ambientes** | Os JWT emitidos são assinados com chave simétrica (HS256) e só servem para a API do próprio ForgeVault: **ele ainda não é provedor de identidade para os outros sistemas** |

Resultado: são cinco credenciais longas por agente, em cinco lugares. Revogar um agente exige mexer em
todos eles, e não há uma visão única de quem acessou o quê.

## 2. Desenho proposto

### 2.1 Identidade única: o ForgeVault como provedor de identidade dos agentes

```
Agente ──(token da conta de serviço no ForgeVault)──► ForgeVault /token-exchange
                                                          │ verifica: identidade ativa, papel,
                                                          │ ambiente, sistema pedido, parada global
                                                          ▼
                     token curto (5–15 min), assinado com chave assimétrica,
                     audiência = o sistema (forgehub | darckware | forgerouter | coreti),
                     ambiente = teste | produção, papéis e escopos do agente
                                                          │
       ┌──────────────────┬───────────────────┬───────────┴──────┐
       ▼                  ▼                   ▼                  ▼
   ForgeHub           Darckware          ForgeRouter          CoreTI
   valida pela chave pública do ForgeVault (JWKS), sem segredo compartilhado,
   e mapeia para o agente e as permissões locais
```

- **Uma credencial por agente:** a conta de serviço no ForgeVault. O resto são tokens curtos derivados dela.
- **Revogar num lugar:** desativar a identidade no ForgeVault corta o acesso a todos os sistemas em
  minutos. É também a **parada global** da autonomia (G.10).
- **Ambiente no token:** um token de teste não abre a produção. Por padrão os agentes recebem só o
  ambiente de teste; a produção exige concessão explícita por papel (ex.: Hephaestus para deploy) ou
  por missão.
- **Auditoria única:** toda emissão de token fica no ForgeVault (quem, para qual sistema, ambiente,
  quando, resultado). Cada sistema continua auditando o que o agente fez lá dentro.
- **Máquinas:** continuam pelo host-bridge, com a chave no ForgeVault, que o agente nunca vê
  (modo "broker" da especificação do ForgeVault). O que muda é que a permissão do agente para uma
  máquina passa a vir do token (papel e ambiente), além da delegação que já existe.
- **Pessoas:** o login do Marcelo nos sistemas pode usar o mesmo provedor depois (fora da primeira
  etapa). O 2FA continua obrigatório.

**Por que não só guardar os tokens atuais no ForgeVault?** Ajudaria a guardar, mas o agente
continuaria recebendo credenciais longas. A revogação seguiria espalhada e o mesmo token abriria teste
e produção. Isso fica apenas como **transição**.

### 2.2 Área de teste

| Peça | Como |
|---|---|
| **Bancos** | Um banco de teste por sistema, separado da produção (ex.: `forgehub_test` numa instância própria ou no mesmo container com usuário diferente sem acesso ao banco de produção). Os testes automatizados e o `dev.sh` passam a usar só ele |
| **Aplicações** | Uma cópia de cada sistema rodando em modo teste (`ENVIRONMENT=homolog`), em portas e endereços próprios só na rede interna/Tailscale (ex.: `teste.forgehub…`) |
| **Dados** | Base de teste reproduzível (seed): produtos, projetos, agentes, clientes e máquinas fictícios; nada pessoal nem de cliente real |
| **Segredos** | Ambiente "teste" no ForgeVault, com segredos próprios (chaves de teste do ForgeRouter com orçamento baixo, tokens de teste) |
| **Integrações externas** | Desligadas ou simuladas: e-mail não sai (fila só registra), Telegram vai para um chat de teste, Darckware de teste sem portal público |
| **Máquinas** | Uma ou duas máquinas de teste no Tailscale (contêiner ou VM com Linux e uma estação Windows de teste), para validar scripts de manutenção sem tocar cliente |
| **Agentes** | Os mesmos agentes, com token de ambiente "teste"; a validação do Service Factory (V), os evals (G.6) e a primeira missão rodam aqui primeiro |
| **Promoção** | Nada passa do teste para a produção sem o gate de produção (Q.5): CI verde, revisão, homologação aprovada, aprovação |
| **Limpeza** | Reset do ambiente de teste por comando (recria bancos a partir do seed); auditoria do que cada agente fez no teste |

## 3. Fases

### Fase T — Área de teste (Onda 1; substitui a Q.4)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| T.1 | Banco de teste do ForgeHub separado da produção; `dev.sh` e suíte de testes passam a usá-lo; limpar da produção os registros deixados por testes (ex.: "Global Owner/Scoped Owner 95d695fb") | Claude Code + Hephaestus | — | Nenhum teste ou `dev.sh` alcança o banco de produção (verificado por credencial sem permissão) |
| T.2 | ForgeHub de teste rodando (backend + frontend) com seed reproduzível e comando de reset | Hephaestus + Aramis | T.1 | Reset recria o ambiente em minutos |
| T.3 | Ambiente "teste" no ForgeVault com os segredos de teste; integrações externas simuladas (e-mail, Telegram, portal) | Aegis + Aramis | T.2 | Nenhuma mensagem real sai do teste |
| T.4 | Máquinas de teste no Tailscale (Linux e Windows) cadastradas no ambiente de teste | Hephaestus | T.2 | Script de manutenção roda na máquina de teste com evidência |
| T.5 | Darckware, ForgeRouter e CoreTI de teste (um por vez, conforme as missões precisarem) | Hephaestus + dono de cada sistema | T.3 | Cada um com banco e segredos próprios |
| T.6 | Regra: validação (V), evals (G.6) e primeira execução de toda missão rodam no teste; produção só pelo gate (Q.5) | Athos (Foundation) | T.2 | Registrado na Foundation e na skill `forgehub` |

### Fase F — Identidade dos agentes pelo ForgeVault (desenho na Onda 1, implantação na Onda 2)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| F.1 | **Desenho** (documento no ForgeVault e no ForgeHub): troca de token, claims, audiências, ambientes, tempo de vida, rotação de chaves, mapeamento de papéis por sistema, falha quando o ForgeVault está fora | Porthus + Aegis | — | Revisado na rodada de revisão do plano |
| F.2 | ForgeVault emite token curto assinado com **chave assimétrica**, publica as chaves públicas (JWKS) e expõe a troca de token com checagem de identidade ativa, papel, ambiente e parada global | Aramis (ForgeVault, .NET) + Porthus revisa | F.1 | Teste: identidade desativada não obtém token; token de teste rejeitado pela produção |
| F.3 | Uma conta de serviço por agente no ForgeVault (os 13 das cartas), com papéis por ambiente | Aegis | F.2 | Inventário no ForgeVault bate com o registro de agentes do ForgeHub |
| F.4 | ForgeHub aceita o token do ForgeVault (rotas de agente e MCP), mantendo o `agt_` em paralelo durante a transição | Aramis | F.2 | MCP funciona com o token novo; `agt_` desligável por agente |
| F.5 | Darckware, ForgeRouter e CoreTI aceitam o token do ForgeVault (um por vez) | Aramis + dono de cada sistema | F.4 | Cada sistema valida pela chave pública, sem segredo compartilhado |
| F.6 | Clientes MCP e scripts dos agentes passam a obter token pelo ForgeVault (sem credencial longa no `.env` do perfil) | Aegis + Porthus | F.4 | Varredura não encontra credencial longa de agente nos perfis |
| F.7 | Desligar as credenciais antigas (`agt_`, tokens de agente por sistema) agente por agente, depois de 7 dias sem uso | Aegis | F.5, F.6 | Auditoria mostra zero uso antes de desligar |
| F.8 | Parada global (G.10) implementada como suspensão da identidade/escopo no ForgeVault + aviso aos sistemas | Aegis + Aramis | F.2 | Teste: parar um agente corta o acesso a todos os sistemas em até 15 min |
| F.9 | Painel de acessos: quem obteve token para qual sistema e ambiente, falhas e anomalias (no ForgeVault, com resumo nas Atividades dos Agentes) | Aramis + Dartan | F.2 | Acesso fora do padrão gera alerta |

## 4. Riscos e cuidados

- **O ForgeVault vira peça crítica de login.** Se ele cai, ninguém obtém token novo. Mitigação: tokens
  em cache até expirar, alta disponibilidade e alerta (módulo 10 da especificação do ForgeVault), e um
  procedimento de emergência documentado.
- **Transição longa:** os dois mecanismos convivem até a F.7. Cada desligamento é por agente, com
  auditoria de uso zero antes.
- **A área de teste também precisa de segurança:** dados fictícios, sem cliente real e sem segredo de
  produção. É isso que permite dar aos agentes liberdade de testar.
- **Documentação do ForgeVault desatualizada:** o `CLAUDE.md` do repositório ForgeVault diz que não há
  código, mas o sistema está implementado e em produção. Atualizar antes da F.2 (tarefa no produto
  ForgeVault).

---
[← Índice](README.md)
