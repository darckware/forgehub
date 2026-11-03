# Área de teste e identidade dos agentes pelo ForgeVault

**Pedido do Marcelo (24/10):** "preciso criar uma área de teste; os agentes cadastrados no ForgeVault
podem fazer login direto nos sistemas e serviços, para garantir a segurança e o acesso ao sistema e
serviços."

São duas peças que se apoiam:
- a **área de teste** é onde os agentes trabalham e validam sem tocar a produção;
- a **identidade única no ForgeVault** é como entram em cada sistema, com uma credencial só, de vida
  curta, revogável num lugar e auditada.

**Atualização 27/10:** T.2+T.3 são pré-requisitos de V-a/N.0 e testes mutantes. Linux T.4a é a fatia da Onda 1; Windows T.4b aguarda alvo autorizado (D-4). B0 restaura dados reais apenas em quarentena de recuperação dedicada e protegida, sem aplicações, mensageria ou agentes comuns; não copia dados reais para seed/suíte de teste. A descrição abaixo registra diagnóstico de 24/10, não prova que nada mudou desde então. Não limpar resíduos de produção como efeito colateral de T.1.

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
| **Bancos** | Um banco de teste por sistema, separado da produção (ex.: `forgehub_test` em contêiner próprio, volume/rede/porta/credencial próprios, com usuário sem acesso ao banco de produção). Os testes automatizados e o `dev.sh` passam a usar só ele |
| **Aplicações** | Uma cópia de cada sistema rodando em modo teste (`ENVIRONMENT=homolog`), em portas e endereços próprios só na rede interna/Tailscale (ex.: `teste.forgehub…`) |
| **Dados** | Base de teste reproduzível (seed): produtos, projetos, agentes, clientes e máquinas fictícios; nada pessoal nem de cliente real |
| **Segredos** | Ambiente "teste" no ForgeVault, com segredos próprios (chaves de teste do ForgeRouter com orçamento baixo, tokens de teste) |
| **Integrações externas** | Desligadas ou simuladas: e-mail não sai (fila só registra), Telegram é stub local sem envio de rede (chat real de teste somente em etapa com aprovação específica), Darckware de teste sem portal público |
| **Máquinas** | Uma ou duas máquinas de teste no Tailscale (contêiner ou VM com Linux e uma estação Windows de teste), para validar scripts de manutenção sem tocar cliente |
| **Agentes** | Agentes/runner simulados e credenciais agt_ próprias da base de teste, sem permissão em produção; identidade assimétrica F.2 é futura; V-a/V-b mutantes, evals e ensaios de tarefas que alteram sistemas rodam aqui primeiro; o registro da missão real permanece em produção (F6), com C.0+C.1 de leitura/política |
| **Promoção** | Nada passa do teste para a produção sem gate. Na Onda 1, o gate manual existente exige testes/build pertinentes, revisão independente, homologação/rollback testados, backup elegível e aprovação explícita do conteúdo/ambiente; não depende da automação Q.5 ainda não implementada. Q.5 automatiza esse mesmo controle na Onda 2 |
| **Limpeza** | Reset do ambiente de teste por comando (recria bancos a partir do seed); auditoria do que cada agente fez no teste |

## 3. Fases

As tarefas das Fases T (área de teste) e F (identidade) estão no planejamento único: [07 — Fases de implementação](07-fases-de-implementacao.md).

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
