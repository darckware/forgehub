# Navegador dos agentes: testes de sistema e tarefas na internet

**Pedido do Marcelo (24/10):** "uma área em que o agente possa testar o sistema no navegador. Tenho
uma área no Workspace do ForgeHub de navegação na internet para os testes do sistema, que precisa ser
ajustada e melhorada. Preciso de uma área de navegação na internet para os agentes, um navegador
próprio para testes e execução de tarefas na internet, como captação de dados e gerenciamento de
redes sociais."

## 1. O que existe hoje (levantado em 24/10)

| Peça | Estado |
|---|---|
| **Navegador do Workspace** (`workspace_browser.py` + host-bridge) | Um único Chromium no host, CDP na porta 9223, perfil persistente `/root/.forgehub/browser/athos`; o Workspace mostra **capturas de tela por polling** e permite clicar, digitar, rolar, navegar, entrar no ForgeHub; registra quem está no controle (pessoa ou agente) |
| Rotinas de automação, testes em segundo plano, macros, sites avulsos | Construídos (tabelas `web_automation_routines`, `web_automation_test_runs`, `macro_instruction_sets`, `standalone_apps`), **com zero registros**: nunca usados |
| Uso pelos agentes | Pensado para o Athos se ligar ao mesmo navegador (`browser.cdp_url`), mas o `cdp_url` do Athos está **vazio**; o navegador **não estava rodando** (nada na porta 9223) |
| Ferramentas de navegador dos agentes Hermes | Os perfis Hermes têm a seção `browser` no `config.yaml` (ferramentas `browser_*` nativas do Hermes) |

**Limitações:**
- **Um navegador e uma aba para todos:** pessoa e agentes disputam a mesma sessão, e uma tarefa
  atrapalha a outra.
- **Um perfil só:** cookies e sessões de tudo o que acontece ficam juntos, inclusive login no ForgeHub
  e em redes sociais.
- **Visualização por capturas periódicas**, não ao vivo.
- **Sem separação entre teste e internet:** o mesmo navegador alcança o ForgeHub interno e a internet.
- **Sem política de rede:** um navegador que abre sites da internet não pode alcançar os serviços
  internos (API do ForgeHub em `localhost`, máquinas do Tailscale). Hoje não há essa barreira.
- **Sem credenciais de forma segura:** não há como logar numa rede social sem a senha passar pelo agente.
- **Sem evidência ligada ao trabalho:** nada liga uma navegação à tarefa do Service Factory.
- **Nunca validado em uso real.**

## 2. Desenho proposto: serviço de navegação com sessões isoladas

```
                 ┌───────────────────────── Serviço de navegação ─────────────────────────┐
 Agente ──MCP──► │ abre sessão (agente, finalidade, ambiente, tarefa) → navegador isolado │
 (Hermes por CDP │                                                                         │
  ou externo por │  modo TESTE: só alcança a área de teste (Fase T)                        │
  Playwright)    │  modo INTERNET: só alcança a internet (nunca localhost nem a tailnet)  │
                 │  perfil por finalidade/conta; credencial injetada pelo ForgeVault       │
                 │  gravação: capturas, vídeo, trilha (HAR/trace) → evidência da tarefa    │
                 └──────────────────────────┬──────────────────────────────────────────────┘
                                            ▼
                  Workspace: lista de sessões, visão ao vivo, assumir o controle
                  (ex.: 2FA ou captcha), devolver ao agente, encerrar
```

### 2.1 Dois modos, separados por rede

| Modo | Para quê | Alcança | Quem usa |
|---|---|---|---|
| **Teste** | Testar os sistemas como um usuário: fluxos de tela, regressão, celular (390 px) e desktop, homologação de design | **Só** a área de teste da Fase T (ForgeHub, Darckware, CoreTI de teste) | Dartan, Porthus, verificadores, evals (G.6) |
| **Internet** | Coleta de dados, pesquisa, gestão de redes sociais, acompanhamento de concorrentes, cadastro em plataformas | **Só** a internet pública; bloqueado para `localhost`, rede interna e tailnet | Kairos, Lara (pesquisa, nunca contato automático), quem a missão autorizar |

O navegador de internet roda **isolado** (contêiner próprio, sem acesso ao sistema de arquivos do host).
O conteúdo das páginas é tratado como dado, nunca como instrução, para evitar injeção de prompt.

### 2.2 Sessões, perfis e credenciais

- **Sessão por agente e tarefa**, com tempo máximo e encerramento automático. Várias em paralelo, dentro
  de um limite.
- **Perfis persistentes por finalidade e conta**: cada rede social (conta da Darckware no Instagram, no
  LinkedIn etc.) tem o próprio perfil. Os cookies não se misturam com testes nem com o ForgeHub.
- **Credenciais pelo ForgeVault, no modo "broker":** o serviço injeta o login no campo da página, e o
  agente nunca vê a senha. 2FA e captcha passam para o Marcelo pelo Workspace (ou por um aviso no
  Telegram), e o controle volta ao agente depois.
- **Downloads em quarentena:** varridos antes de qualquer uso.

### 2.3 Regras para tarefas na internet

| Tarefa | Regra |
|---|---|
| **Publicar em rede social** (post, resposta, mensagem) | **Nada sai sem aprovação**, como os e-mails do Darckware: o agente prepara, o Marcelo aprova o texto e a mídia exatos, e só então o serviço publica. Aprovação vale para aquela versão; qualquer edição a anula |
| **Gerenciar redes sociais** | Preferir a **API oficial** quando existir (Meta Graph API para Instagram/Facebook, LinkedIn API, X API): é mais estável, não é bloqueada e respeita os termos de uso. O navegador fica para o que a API não cobre |
| **Coleta de dados** | Respeitar termos de uso e `robots.txt`; nada de dado pessoal sem base legal (revisão da Themis, LGPD); limite de requisições; os dados coletados viram um artefato com origem, data e finalidade |
| **Domínios** | Lista de domínios permitidos por tarefa ou missão; fora dela, a navegação é bloqueada e registrada |
| **Endereço de saída** | Redes sociais costumam bloquear IP de servidor (datacenter). Opção: um **nó de navegação** numa máquina com internet residencial, ligado pelo Tailscale, usado só para o modo internet |

### 2.4 Ligação com o resto do plano

- **Service Factory:** cada sessão pertence a uma tarefa. As capturas, o vídeo e a trilha viram evidência
  (`browser_session:<id>`) e documento da tarefa. Um teste de tela aprovado entra na verificação (G.5).
- **Missão:** a missão define os domínios permitidos e se pode publicar (sempre com aprovação).
- **Atividades dos Agentes:** sessões abertas aparecem ao vivo, com agente, finalidade, domínio atual e
  tarefa; uma sessão parada ou fora da lista de domínios gera alerta.
- **Identidade (Fase F):** a sessão é aberta com o token do ForgeVault do agente, e o modo e o
  ambiente vêm do token.
- **Linha "Marketing e captação":** gestão de redes sociais e coleta de dados passam a ser serviços dessa
  linha, com o funil do Darckware (E.4) medindo o resultado.

## 3. Fase N — Navegador dos agentes

| # | Tarefa | Dono | Onda | Depende | Aceite |
|---|---|---|---|---|---|
| N.0 | Validar o navegador atual do Workspace (ligar, navegar, uma rotina, um teste em segundo plano) e registrar o que falha | Claude Code | 1 (junto da V-a) | — | Relatório do que funciona e do que falta |
| N.1 | **Serviço de navegação com sessões isoladas** (um navegador por sessão, contêiner próprio, limite de sessões, tempo máximo), substituindo o navegador único compartilhado; o Workspace passa a listar as sessões | Porthus (desenho) + Aramis | 2 | N.0, T.2 | Duas sessões em paralelo não interferem; sessão encerrada não deixa processo |
| N.2 | **Visão ao vivo** (screencast do CDP em vez de capturas periódicas) e **assumir/devolver o controle** no Workspace, com aviso no Telegram quando o agente pede ajuda (2FA, captcha) | Dartan + Aramis | 2 | N.1 | Visão fluida; o controle passa e volta sem perder a sessão |
| N.3 | **Modo teste:** sessões presas à área de teste; testes de tela (Playwright) por tarefa com vídeo e trilha como evidência; as rotinas e testes em segundo plano atuais passam a rodar aqui | Dartan + Aramis | 2 | N.1, T.2 | Teste de regressão de uma tela do ForgeHub roda na área de teste e anexa evidência à tarefa |
| N.4 | **Modo internet com política de rede:** saída só para a internet, bloqueio de `localhost`, rede interna e tailnet; domínios permitidos por tarefa; downloads em quarentena; conteúdo de página tratado como dado | Aegis + Aramis | 2 | N.1 | Teste: a sessão de internet não alcança a API interna nem uma máquina da tailnet |
| N.5 | **Ferramentas MCP de navegação** para todos os agentes (abrir sessão com finalidade, ambiente e tarefa; navegar; ler; capturar; pedir ajuda humana; encerrar). Hermes também por `cdp_url` da sessão, externos por Playwright | Aramis | 2 | N.1, F.4 | Um agente faz um teste de tela e uma pesquisa só pelo MCP |
| N.6 | **Perfis por conta e credenciais pelo ForgeVault (broker):** login injetado sem o agente ver a senha; 2FA pelo Marcelo | Aegis + Aramis | 3 | N.2, F.2 | Login numa conta de teste sem a senha aparecer em log, prompt ou resultado |
| N.7 | **Redes sociais:** fila de publicações com aprovação por versão exata (como os e-mails do Darckware); integração pela API oficial onde houver; navegador só para o resto | Kairos (conteúdo) + Aramis + Dartan | 3 | N.6, E.4 | Nenhuma publicação sai sem aprovação; editar anula a aprovação |
| N.8 | **Coleta de dados:** regras de LGPD e termos de uso (Themis), limite de requisições, resultado como artefato com origem e finalidade | Themis + Kairos + Aramis | 3 | N.4 | Coleta com dado pessoal sem base legal é recusada |
| N.9 | **Nó de navegação residencial** (opcional) pelo Tailscale para o modo internet, se as redes bloquearem o IP do VPS | Hephaestus | 3 | N.4 | Sessão de internet sai pelo nó escolhido |
| N.10 | **Navegação nas Atividades dos Agentes e na auditoria:** sessões ao vivo, domínio atual, alerta de domínio fora da lista ou sessão parada; trilha auditável | Aramis + Dartan | 2 | N.1, A.1 | Toda sessão aparece com agente, tarefa e finalidade |

## 4. Riscos

- **Injeção de prompt por páginas da internet** (o risco mais sério): o conteúdo é sempre dado, as
  ações sensíveis (publicar, logar, baixar) exigem aprovação ou passam pelo serviço, e a sessão de
  internet não alcança nada interno.
- **Bloqueio e termos de uso das redes sociais:** automação pelo navegador pode violar os termos e levar
  ao bloqueio da conta. Por isso a preferência pela API oficial, e as publicações sempre aprovadas.
- **LGPD na coleta de dados:** dado pessoal só com base legal e finalidade registradas.
- **Recurso do VPS:** cada navegador consome memória; o limite de sessões é obrigatório.

---
[← Índice](README.md)
