# Checklist de contexto e alinhamento da missão — FileNest

Data: 06/11/2026. Estado: planejamento documental preparado; baseline de execução ainda não aprovada.

## Objetivo e decisões confirmadas

Usar o **FileNest**, em `/root/project/filenest`, como projeto real para validar a integração
Missão → Service Factory → Messages → Operação 24x7 → Atividades dos Agentes → evidência → revisão → aceite.
Marcelo escolheu o projeto e pediu concluir o planejamento com um checklist de contexto e alinhamento.

O projeto Plano integrado continua acompanhando a evolução do ForgeHub. C.0/C.1 continuam como
missão de contexto prevista na Onda 1; a escolha do FileNest acrescenta o piloto de aplicação real,
sem remover a política e o isolamento de contexto exigidos antes de ampliar a operação.
O aceite da Onda 1 continua necessário antes da execução do piloto na Onda 2.

**Proposta de recorte técnico:** a etapa 4 do plano vigente do FileNest — acesso individual dos
agentes à API e às telas, com autorização e auditoria. A proposta aproveita uma pendência real,
mas depende da etapa 3 (usuários, perfis, permissões e auditoria). A escolha desse recorte ainda
precisa constar da baseline; não foi atribuída ao Marcelo como decisão já tomada.

Os checkboxes abaixo representam provas de alinhamento. Só estão marcados os fatos conferidos
nesta preparação. Referências de tarefas são ids locais do plano, nunca números inventados do sistema.

## 1. Contexto disponível

- [x] Projeto indicado por Marcelo: FileNest, `/root/project/filenest`.
- [x] Repositório e fontes de contexto consultados em 06/11; HEAD observado `608bbf9`, sem alterações locais na consulta.
- [x] README, AGENTS.md, estado da implementação, plano geral e pendência de acesso dos agentes lidos.
- [x] Backend ASP.NET Core/.NET 10, frontend React/TypeScript e PostgreSQL identificados no repositório.
- [x] Registro de implementação de 04/11 informa versão 0.3.0, login, MFA e integração ForgeVault.
- [x] Código de autenticação existente consultado; sessão humana usa cookie e recusa anônimos na API protegida.
- [x] Acesso individual dos agentes identificado como pendente na documentação do FileNest.
- [ ] Revalidar HEAD, branches, alterações em andamento e ambiente realmente publicado ao abrir a missão.
- [ ] Registrar inventário funcional atualizado: entregue, parcial, pendente e bloqueado, sem considerar telas de planejamento como operacionais.
- [ ] Corrigir o AGENTS.md do FileNest, que ainda afirma não existir código, manifests ou testes; conferir o plano geral contra o estado de implementação mais recente.

Fontes locais do FileNest: `README.md`, `AGENTS.md`, `docs/IMPLEMENTACAO-STATUS.md`,
`docs/PENDENCIA-ACESSO-DOS-AGENTES.md`, `docs/superpowers/plans/2026-11-04-plano-geral-execucao.md`,
`apps/api/Program.cs` e `compose.identity-test.yml`. Caminhos relativos nesta lista partem de
`/root/project/filenest`. Nenhum teste ou acesso ao domínio público foi executado nesta preparação.

## 2. Brief e fronteira da missão

### Contrato de construção centralizado no FileNest

Atualização de 06/11/2026, por pedido de Marcelo: toda documentação do sistema está centralizada
em `/root/project/filenest/docs`. O [índice local do FileNest](/root/project/filenest/docs/README.md)
reúne spec, planos para IA, arquitetura, banco, Docker, metodologia, design e segurança.
README/AGENTS/DESIGN/CHANGELOG da raiz são pontos de entrada para essa pasta.

- [x] Tecnologias e direção de construção documentadas no contrato do projeto.
- [x] PostgreSQL 17 e arquitetura modular .NET 10/React definidos; diferenças entre stack desejada e código atual identificadas.
- [x] Deploy Docker Compose, ambientes separados, persistência e recuperação documentados.
- [x] Metodologia incremental com spec, baseline, testes, revisão independente e versionamento registrada.
- [x] Design system e UX definem sidebar, temas claro/escuro, formulários em página/painel à direita e confirmação padrão.
- [x] Contas, perfis, MFA, reCAPTCHA, sessão, bloqueio e limite de conexões por conta especificados.
- [ ] Fixar na baseline os parâmetros ainda propostos: teto de conexões e timeout de inatividade; verificar implementação de cada controle antes do aceite.

Essas marcações comprovam a preparação documental, não implementação dos requisitos. O
[checklist de abertura local](/root/project/filenest/docs/CHECKLIST-MISSAO.md) é a entrada de
trabalho do FileNest; este documento continua sendo o checklist de coordenação da integração.

- [x] Resultado pretendido: comprovar uma entrega real do FileNest gerenciada pelo fluxo integrado.
- [ ] Fixar título, resultado único e recorte na baseline; proposta: “FileNest — acesso auditável dos agentes em homologação”.
- [ ] Nomear os projetos coordenador e executor, com produto, versão editável, ids reais e vínculo entre ambos.
- [ ] Conferir se o produto FileNest já existe no ForgeHub; reutilizar o cadastro e não duplicar projetos ou tarefas em execução.
- [ ] Confirmar o recorte proposto da etapa 4 e registrar quais capacidades da etapa 3 ele requer; entregar essas capacidades antes de depender delas.
- [ ] Relacionar cada requisito a uma tarefa, prova esperada e critério de aceite verificável.
- [ ] Registrar exclusões do piloto: arquivos de clientes, agentes nativos Windows/Linux, transporte Tailscale/LAN, edição Google, backup de arquivos e conclusão do produto completo.
- [ ] Definir prazo, orçamento/teto, prioridade e regra de parada na baseline concreta; não presumir valores aprovados.

## 3. Contexto que acompanha cada execução

- [ ] Pacote versionado com brief, recorte, critérios, mapa de dependências, commits e documentos vigentes.
- [ ] Informar caminho de trabalho real `/root/project/filenest`, branch/worktree reservado e arquivos permitidos por tarefa.
- [ ] Registrar fonte, versão, hash, ambiente e consumidores autorizados do pacote.
- [ ] Incluir decisões anteriores relevantes e pendências conhecidas; resolver divergências com a instrução atual e o estado verificado.
- [ ] Listar skills necessárias para executor e revisor e comprovar disponibilidade antes do despacho.
- [ ] Incluir apenas referências de credenciais; nenhum token, senha, cookie, código MFA ou dado pessoal no contexto.
- [ ] Revalidar os filtros C.2.R/C.2b.R e provar que contexto pessoal/cliente não é recuperado indevidamente.

## 4. Responsáveis e permissões

Papéis propostos seguem a divisão técnica registrada em 03/11. As atribuições reais e a capacidade
disponível devem ser confirmadas no cadastro antes de aprovar a baseline.

| Papel | Proposta | Prova necessária |
|---|---|---|
| Orquestração | Athos | Vínculo à missão, delegação e regras de escalonamento |
| Backend, infraestrutura de teste e contratos | Aramis | Atribuição, skills e caminho FileNest |
| Frontend e validação de telas | Dartan | Atribuição, skills e ambiente de navegador |
| Revisão do backend | Dartan | Identidade diferente de autor/coautor |
| Revisão do frontend | Aramis | Identidade diferente de autor/coautor |
| Consolidação do dossiê | Orquestrador, com fontes fornecidas pelos executores | Rastreabilidade por requisito e verificação independente |
| Aceite do resultado | Marcelo | Aprovação vinculada à missão e versão/hash do dossiê |

- [ ] Conferir ids registrados, membros e permissões por projeto; o nome de um runtime não cria outra identidade.
- [ ] Confirmar disponibilidade de executor/revisor e substituição em caso de cota, erro ou ausência.
- [ ] Impedir que autor ou coautor aprove sua própria entrega, inclusive quando duas fatias alterarem o mesmo arquivo.
- [ ] Registrar dependências entre tarefas; uma mensagem dizendo “depois de” não cria a dependência.

## 5. Ambiente de teste próprio do FileNest

O `compose.identity-test.yml` existente prova apenas a intenção de isolamento do teste de schema;
não demonstra um ambiente completo de homologação da API, frontend e sessão dos agentes.
A área de teste do ForgeHub também não substitui a do FileNest.

- [ ] Inventariar capacidade e definir um Compose de homologação FileNest com nome, rede, banco, volumes e portas próprios.
- [ ] Adaptar os testes a HTTPS local e origem de homologação explícita: o código atual exige cookie Secure e origem `https://filenest.darckware.net` em mutações de `/api/auth`.
- [ ] Usar identidades, chaves de cookies, criptografia e dados fictícios exclusivos do teste; não carregar segredos Production.
- [ ] Simular reCAPTCHA e integrações externas somente na configuração de teste; comprovar que produção não aceita o simulador.
- [ ] Negar acesso a bancos/volumes/serviços de produção e envios externos; conferir configuração antes de iniciar a suíte.
- [ ] Garantir seed/reset reproduzível e que limpeza opere somente no projeto Compose de homologação.
- [ ] Registrar endpoints reais de API/frontend, revisão do banco e versão do pacote testado.
- [ ] Fazer smoke e teste negativo de isolamento antes dos testes mutantes.

## 6. Contrato da entrega piloto proposta

- [ ] Especificar autenticação por token próprio de cada agente, específico do FileNest e do ambiente; aplicação guarda hash, valor fica no ForgeVault com concessão individual.
- [ ] Especificar rota de troca do token por sessão de navegador de 30 minutos, sem renovação nem persistência; não usar conta humana ou `svc-agente`.
- [ ] Aplicar autorização no backend, leitura por padrão e lista explícita de áreas permitidas; nova área começa fechada.
- [ ] Fechar para agentes dados pessoais, conversas, terminal, arquivos do servidor, segredos e administração; telas administrativas são operadas por administrador humano autorizado.
- [ ] Definir bloqueio/revogação com efeito na requisição seguinte e encerramento de conexões pelo administrador.
- [ ] Definir auditoria: agente, evento, alvo/motivo, IP, navegador e data/hora; sem token, corpo ou parâmetros de busca.
- [ ] Cobrir `session_opened`, `session_refused`, `area_read`, `request_denied`, `access_changed` e `sessions_ended`.
- [ ] Fixar endpoints, erros, migrations, limites, telas e testes antes da implementação; preservar os limites atuais de sessão humana/MFA.

Esse contrato aplica o padrão existente; o detalhamento de implementação pertence ao projeto FileNest.
Não exige implantar a identidade assimétrica futura F.2–F.9 como condição para testar o token individual.

## 7. Sequência executável e dependências

| Etapa | Entrega | Pré-condição | Evidência de saída |
|---|---|---|---|
| Alinhamento | Brief, inventário, recorte, membros e pacote de contexto | M0.1 e estado real do FileNest conferidos | Documentos versionados e ids reais |
| Preparação | Contratos, perfis/auditoria necessários e homologação isolada | Recorte definido; isolamento conferido antes de mutações | Testes negativos, seed/reset e contratos revisados |
| Abertura | Missão FileNest com projetos vinculados e baseline aprovada | Aceite da Onda 1, incluindo C.0/C.1 e C.2b.R; revisão P1–P8 | Baseline com hash, orçamento, prazo e critérios aprovados |
| Backend | Tokens, sessões, autorização e eventos de auditoria | Baseline vigente e ambiente de teste liberado | Testes de segurança, execução e revisão independente |
| Frontend | Entrada por sessão, controle administrativo e auditoria | Contrato API revisado; backend disponível no teste | Testes de fluxo/telas e revisão independente |
| Validação integrada | Percurso pelo ForgeHub e navegador FileNest | Backend/frontend integrados e revisados | Provas por critério e bloqueios corretamente visíveis |
| Aceite | Dossiê final e decisão | Validação integrada sem bloqueantes | Aprovação ligada à versão/hash, ou recusa com correção |

Leitura e preparação documental podem avançar antes do aceite da Onda 1. O fluxo de execução
do piloto respeita a ordem entre ondas; não depende da implementação completa das Ondas 2/3.
Usa as ferramentas M0 disponíveis, a publicação manual existente se necessária e registra cada
lacuna encontrada como defeito. A sequência desta tabela não cria tarefas no ForgeHub.

## 8. Provas da integração entre os módulos

- [ ] Service Factory contém plano, tarefas, dependências, responsáveis, documentação e critérios associados ao FileNest.
- [ ] Despacho cria um único Messages vinculado à tarefa, com working_path FileNest, run real e versão de contexto; retentativa não duplica execução.
- [ ] Operação 24x7 registra decisão, motivo e próxima ação; falha/cota/dependência mantém bloqueio compreensível e retomada pelo fluxo existente.
- [ ] Atividades exibe executor, execução e desfecho coerentes com Messages/TaskExecution.
- [ ] Conclusão do runtime permanece relato até evidência verificada e revisão independente; commit não integrado não encerra entrega de código.
- [ ] Alterar brief/critério após aprovação invalida a autorização anterior; dependência inacabada impede despacho.
- [ ] Documentos e observações do projeto são recuperados no contexto permitido e aparecem na versão do despacho.
- [ ] Missão só chega ao aceite quando todos os critérios possuem provas; tarefa concluída isoladamente não declara o conjunto entregue.

## 9. Testes e dossiê de aceite

- [ ] Executar no FileNest isolado `dotnet build apps/api/FileNest.Api.csproj --configuration Release` e `dotnet test tests/FileNest.Security.Tests`.
- [ ] Executar `npm ci` e `npm run build` em `apps/web`; `bash scripts/test-smoke.sh` e `bash scripts/test-postgres.sh` na raiz, após conferir alvos e portas.
- [ ] Acrescentar testes do piloto: token inválido/revogado, agente bloqueado, escrita/área fechada, expiração em 30 minutos, renovação/persistência recusadas e auditoria completa.
- [ ] Reexecutar regressão de login humano, MFA, sessão de 8 horas e persistência de 30 dias; o reCAPTCHA real continua sendo interação humana.
- [ ] Demonstrar no navegador a entrada de um agente sem senha/MFA e a recusa das operações fora do escopo, usando dados fictícios.
- [ ] Verificar estados de carregamento, vazio, erro, acesso negado e expiração nas telas afetadas, incluindo 390 e 1440 px.
- [ ] Anexar commit, comando, resultado, ambiente, horário, execução, revisor e capturas sanitizadas a cada critério.
- [ ] Registrar defeitos com reprodução, impacto, correção sugerida e dependentes; bloqueantes impedem aceite.
- [ ] Consolidar dossiê com hash e limitações; obter aceite pelo fluxo governado.
- [ ] Se houver publicação: preparar pacote exato, backup/restauração, rollback, autorização aplicável e smoke da versão realmente ativa. Homologação não comprova publicação.

## 10. Situação de fechamento do planejamento

**Definidos:** projeto real, caminho, objetivo da validação, contexto de partida, proposta de recorte,
dependências, divisão de papéis, sequência, checklist de segurança e provas de aceite.

**A preencher/verificar na abertura:** escolha final da entrega piloto, ids e inventário atuais,
ambiente de homologação completo, contratos detalhados, capacidade dos responsáveis, prazo,
orçamento e baseline assinada. Nenhum desses campos pode ser marcado como aprovado por este documento.

As pendências anteriores da Onda 1 seguem na [matriz canônica](onda1-tarefas.json). Este checklist
não as conclui nem cria um segundo grafo de tarefas. O cadastro das tarefas do piloto usa a versão
aprovada deste contexto e deve reutilizar trabalho FileNest já existente.

---
[← Índice](README.md)
