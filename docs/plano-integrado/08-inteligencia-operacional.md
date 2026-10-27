# Inteligência operacional própria ("nossa AGI")


## O que é realista

Nenhuma integração de sistemas produz uma AGI geral, e o plano não promete isso. O que dá para
construir com Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk e Darckware é uma **organização de
agentes autônoma e que melhora sozinha**:
- recebe objetivos;
- planeja e executa com evidência;
- mantém sistemas e máquinas;
- aprende com o resultado;
- melhora o próprio software, dentro de limites que o Marcelo controla.

O plano até a seção 6 cobre o **corpo** desse sistema: executar, registrar, vigiar e coordenar. A
análise abaixo mostra o que ainda falta para que ele **aprenda, se avalie e se corrija** de forma
mensurável e segura.

## O que já existe e o que falta

| Capacidade | Já existe | Falta | Fase |
|---|---|---|---|
| Agir no mundo | Messages, Acesso Remoto (Tailscale/RustDesk), Deploy, MCP, tools | — | — |
| Planejar | Service Factory, Missão (proposta), cartas | Hierarquia de objetivos acima das missões | G.1 |
| Perceber | Telemetria, Auditor, notificações, Messages, canais, Darckware (site, chat, leads, portal) | Um fluxo único de eventos que dispare iniciativa | G.2 |
| Lembrar | Hindsight, KB, Foundation, `MEMORY.md` | Controle das camadas com precedência, proveniência e isolamento | **Fase C** |
| Conhecer o próprio ambiente | Blueprints, máquinas, deploy, checks, scripts — em telas separadas | Um mapa único do ecossistema (o que existe, depende de quê, quem é dono) | G.4 |
| Verificar o próprio trabalho | `STATUS: DONE`, evidência `git:`/`file:`/`db:`, revisão do Porthus | Verificação independente do resultado por tipo de tarefa (não só "existe") | G.5 |
| **Medir a própria capacidade** | Evolução mede operação (falhas, prazos) | **Avaliações de capacidade (evals)**: tarefas-padrão por agente e domínio, repetidas, com nota. Sem isso não há como saber se uma mudança de modelo, skill ou prompt melhorou ou piorou | G.6 |
| **Aprender com o resultado** | Hindsight retém conversa; curator de skills; Evolução registra mudanças | **Lições estruturadas**: cada falha ou retrabalho gera uma lição com causa e evidência, que vira proposta de skill, carta ou rotina, avaliada pelos evals antes de valer | G.7 |
| **Melhorar o próprio software** | Retrospectiva propõe; A2 vai ao Marcelo | O laço completo: proposta → Missão → projeto → implementação pelos externos → evals → deploy → medição, de ponta a ponta | G.8 |
| Escolher o modelo certo | ForgeRouter (roteamento, fallback) | Seleção guiada pelos evals por tipo de tarefa — **no projeto ForgeRouter**, não no ForgeHub | G.9 (fora) |
| Segurança da autonomia | A0/A1/A2, delegações, redação de segredos, "dados não são instruções" | **Parada global** (pausar toda autonomia, ou a de um agente, num toque), orçamento de autonomia, testes de injeção de prompt vindos de WhatsApp/e-mail/web, registro de toda ação autônoma reversível | G.10 |
| Decisões do Marcelo | Aprovações, dúvidas, A2, incubação, aceite de missão — em telas diferentes | **Fila mínima G.11a na Onda 2**; unificação completa G.11b na Onda 3 | G.11a/G.11b |
| Continuidade | Snapshots de alguns alvos observados; cobertura/restauração dos alvos críticos ainda não comprovadas nesta consolidação | Recuperação testada do estado dos agentes (perfis, memória, banco) | G.12 |

## Fase G — Capacidade de aprender e decisões

G.11a é a fatia mínima antecipada para a Onda 2. As demais capacidades permanecem na Onda 3.
Nenhuma contagem histórica de execução verde autoriza aumentar autonomia.

| # | Tarefa | Dono | Verificador | Depende | Aceite |
|---|---|---|---|---|---|
| G.1 | Objetivos trimestrais com métrica acima das missões | Aramis (apoio Dartan) | Porthus | M.1 | Objetivo por missão; exceção da Onda 1 documentada, sem bloquear C.0+C.1 |
| G.2 | Evento operacional comum com fonte/chave de dedupe/abertura/fechamento/auditoria, compartilhado com I.12/D.11 | Aramis | Porthus | A.5 | Iniciativa cita evento; reprocesso não duplica trabalho |
| G.3 | Coberto pela Fase C | — | — | — | Não abrir implementação duplicada |
| G.4 | Mapa dos sistemas, máquinas, serviços, checks, donos e dependências | Aramis (apoio Dartan) | Porthus | B.1 | Consulta MCP responde dependências e dono com fonte |
| G.5 | Ampliar os verificadores da M0.6a para manutenção/browser/documentação | Aramis | Porthus | M0.6a, I.5, N.3, D.2 | Prova do tipo e revisor independente, sem reimplementar o guard da Onda 1 |
| G.6 | Evals seguros, repetíveis, com nota antes/depois por agente/domínio | Aramis (desenho Daedalus) | Porthus | G.5, A.4, T.2, T.3 | Rodar somente no teste; regressão impede promover modelo/skill/prompt |
| G.7 | Falha/PARTIAL/retrabalho/rejeição gera lição com fonte e proposta avaliada | Aramis (apoio Athos) | Porthus | G.6 | Dedupe; alteração de skill depende de avaliação e aprovação aplicáveis |
| G.8 | Proposta aprovada percorre missão→projeto→código→evals→deploy→medição | Aramis | Porthus | G.6, M.1 | Evidência em cada etapa; proposta não se autoaprova |
| G.9 | Seleção de modelo guiada pelos evals, no projeto ForgeRouter | Atlas (planejamento) | Daedalus | G.6 | Fora do código deste plano; ForgeHub fornece notas |
| G.10 | Parada global/perfil e orçamento de autonomia, suíte de injeção e registro/desfazer | Aramis (apoio Aegis) | Porthus | A.1, F.8 | Suspensão efetiva e suíte verde antes de elevar N; não existe parada global só por haver botão |
| G.11a | **Fila mínima Onda 2:** agregar aprovações, dúvidas e bloqueios já existentes, com fonte, recomendação, link e permissão de origem | Aramis (apoio Dartan) | Porthus | V-b, P.2 | Fontes disponíveis/indisponíveis distintas; sem autoaprovar; P.6 consome este contrato sem depender de M.1/G.2/O.2 |
| G.11b | **Fila completa Onda 3:** acrescentar aceite de missão, A2, incubação madura e integrações restantes/Telegram | Aramis (apoio Dartan) | Porthus | G.11a, M.1, O.2, G.2 | Todas as classes com dedupe, escopo e ação protegida; ausência de fonte não vira fila vazia |
| G.12 | Inventariar cobertura de backup por destino crítico; ordenar restauração, RPO/RTO e responsáveis; restaurar amostra no teste | Hephaestus (apoio Aramis) | Aegis | T.2, T.3, inventário e snapshots elegíveis | Snapshot recente identificado por alvo, restauração e integridade comprovadas; falha/ausência em um alvo mantém recuperação pendente |

### Regra de backup (F4 e revisão de 26/10)

Antes de dizer que recuperação está pronta: identificar todos os alvos críticos (banco, perfis,
Foundation, KB e Hindsight conforme inventário), última execução e último snapshot confirmado por
alvo, política RPO/RTO e ordem de restauração. Um upload ou snapshot bem-sucedido de outro projeto
não encerra uma falha do sistema. Quota/caminho/destino sem verificação recente são pendências.
A cópia SQL local não prova proteção externa. Fazer teste de restauração de amostra isolada;
nenhuma sobrescrita de produção, exclusão de backup ou contratação de armazenamento está autorizada
por esta consolidação. Revisar a prova no mínimo trimestralmente e após mudança crítica.

## Níveis de autonomia da missão (A6)

**N0–N3** são níveis da missão; **M0** designa apenas o pacote mínimo de implementação do 07.
A0/A1/A2 continuam a classificação de mudanças da Foundation. Não são sinônimos de N0/N1/N2.

| Nível | Comportamento e gate |
|---|---|
| N0 | Marcelo aprova a baseline; agentes executam somente o conteúdo, ambiente e permissões autorizados; revisão e aceite continuam independentes |
| N1 | Coordenador propõe o plano; Marcelo aprova. Exige G.10, G.11b e evidência de 10 missões N0, ≥80% entregas aceitas na primeira tentativa e documentação completa |
| N2 | Despacho de tarefas de baixo risco no escopo delegado; exige G.5/G.6, N1 estável por 30 dias e nenhum incidente de contexto. Código, produção e contatos externos mantêm os gates aplicáveis |
| N3 | Propor novas missões em rascunho; exige G.1/G.2/G.7/G.8, N2 estável e suíte G.10 verde. Propor nunca significa aprovar ou executar |

Nível N não revoga A0/A1/A2, RBAC, limites de custo ou a autoridade de Marcelo. Mudança de identidade,
Foundation, política comum ou ação externa continua sujeita à sua aprovação e ao dono canônico.
Onda 1 opera em N0; esta revisão documental não eleva nenhum nível no sistema.

## Ordem

Onda 2: V-b/P.2 → G.11a → P.6. Onda 3: ampliar M.1/F.8/G.5/G.6/G.10 conforme dependências,
G.11a+M.1+O.2+G.2 → G.11b; só depois avaliar promoção de autonomia. G.12 tem suas próprias provas
por alvo e nunca se deduz do sucesso agregado de outras rotinas.

---
[← Índice](README.md)
