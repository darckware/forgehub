# Plano de gestão de memória coletiva — Hermes e agentes externos

**Data:** 2026-09-06

**Status:** proposta para revisão de Marcelo; implementação não iniciada.

**Escopo autorizado nesta etapa:** diagnóstico e planejamento. Não alterar configurações,
memórias, cadastros, serviços ou dados da VPS; não despachar Messages.

**Objetivo:** tornar verificável, sustentável e coerente o uso de memória por Hermes,
Codex, Claude e Agy/Antigravity, recuperar dados/comandos de cron e revisar as rotinas
relacionadas do ForgeHub, com alertas somente quando houver necessidade de atenção.

**Restrições atuais de Marcelo:** cada agente externo corrige a própria configuração;
a arquitetura local/VPS está sendo planejada pelo Claude e deve ser aguardada antes de
qualquer implementação que a afete. Este documento não substitui nem altera esse trabalho.
Toda a documentação desta iniciativa fica em `docs/` do projeto ForgeHub.

**Cartilha vinculada:** [autoconfiguração dos agentes externos](../../runbooks/EXTERNAL_AGENT_ECOSYSTEM_SELF_CONFIGURATION.md).
Nenhuma tarefa foi despachada aos agentes nesta etapa.

## 1. Evidências e limites do diagnóstico

Inspeção realizada no ambiente local. Nenhuma conclusão de saúde da VPS foi validada
remotamente nesta etapa. Os documentos da VPS são referência de topologia, não prova
de funcionamento atual.

| Evidência local | Consequência para o plano |
|---|---|
| `/root/.hermes/foundation` é um link para `/root/memory/foundation`; `/root/.hermes/knowledge_base` aponta para `/root/memory/knowledge_base`. | Migrar referências ativas para as localizações atuais; preservar os links durante a transição. |
| A definição do serviço Hindsight está em `/root/memory/hindsight/docker-compose.yml`; o contêiner de banco ativo é `hindsight_postgres`. | Distinguir diretório de implantação, endpoint do serviço e armazenamento PostgreSQL. Hindsight não é um arquivo de memória Markdown. |
| `MANIFEST.yaml`, contratos de memória e `knowledge_cycle.py` de Codex, Claude e Gemini ainda citam caminhos antigos. | Corrigir as fontes que geram contexto, além dos arquivos exibidos ao operador. |
| Aegis: `memories/MEMORY.md` com 2.195 caracteres no arquivo; configuração com limite de 2.200. | Capacidade muito próxima do limite. Confirmar a contagem normalizada e a utilização efetiva dessa memória pelo runtime antes de intervir. |
| `memory_maintenance.sh` só acompanha `state.db`, Knowledge Base e logs do Athos; não mede o orçamento de `MEMORY.md`/`USER.md`. | A rotina existente não cobre o incidente relatado. |
| Job `memory-maintenance`, ID `7a59f61a1668`: agendado diariamente às 20:30; `failure_streak: 3`; erro sobre indisponibilidade de `systemd-run --user --scope`. | Corrigir e testar o mecanismo de execução, além do conteúdo da manutenção. Job habilitado não significa job funcionando. |
| O job de retenção Hindsight referencia `hindsight_prune.py`, ausente no caminho registrado. | Auditar origem, código e política desse job antes de reativar qualquer exclusão. |
| Status do adaptador Codex registrou timeout em `UserPromptSubmit`; `/health` do Hindsight respondeu `healthy` e `database: connected` na consulta direta. | Separar saúde do serviço de sucesso de recall, retenção, processamento e execução de hooks. Causa do timeout ainda não determinada. |
| O editor comum de perfis lê/escreve `MEMORY.md` diretamente na raiz do perfil. | Exibir separadamente o contrato do perfil e a memória curta real em `memories/MEMORY.md`; não aplicar o mesmo limite a arquivos com funções diferentes. |
| O contrato Agy/Dartan documenta hooks de Gemini CLI e arquivos em `/root/.gemini`; o executável `agy` existe. | Isso não prova que Antigravity execute esses hooks. Validar cada superfície real de uso. |
| Messages, Docs, Projects, Governance, Cockpit e fechamento de versão já aparecem na navegação. | A proposta reutiliza esses módulos; não cria outro gerenciador de tarefas. |
| O checkout tem alterações anteriores de banco, infraestrutura e Hindsight, além de uma proposta multiambiente. | Integrar com o trabalho em curso, preservando mudanças existentes. A proposta multiambiente não deve ser tratada como funcionalidade já entregue. |
| Contagem SQL direta no banco `foundation` da instância `hindsight_postgres`: 1 banco semântico, 17.028 unidades de memória, 2.179 documentos; tamanho PostgreSQL de 407.804.951 bytes, aproximadamente 389 MiB. | Baseline de dimensionamento; inclui estruturas além do texto semântico e não comprova ausência de perda histórica. |
| `_ingest_cron_notifications` gera registros para sucessos e falhas; `feedback.py` também notifica resultado de tarefa concluída. | Revisar os produtores de alerta conforme a instrução atual; filtrar só a interface não resolve. |
| Existem `.jobs.json.good`, snapshot antigo e cópias `cron-jobs.json` de curadoria, incluindo 2026-09-01. | Fontes candidatas à recuperação; existência não comprova integridade, completude ou versão correta. |
| `docs/screens/crons.md` ainda descreve truncamento em 300 caracteres; `_truncate_description` no código atual preserva o texto. | Documentação desatualizada nesse ponto. Verificar versão implantada e histórico antes de atribuir a perda atual à falha antiga. |

Fontes principais: `frontend/src/components/layout/navSections.ts`,
`backend/app/core/agent_profile_files.py`, `backend/app/api/routes/agent.py`,
`backend/app/api/routes/hindsight.py`, `host-bridge/app.py`,
`docs/architecture/MULTI_ENVIRONMENT_INFRA_AND_IDENTITY.md`,
`/root/.hermes/profiles/athos/cron/jobs.json`,
`/root/.hermes/profiles/athos/scripts/memory_maintenance.sh`,
`/root/.codex/memory/status.json`, `/root/memory/foundation/MANIFEST.yaml`,
`/root/memory/foundation/governance/KNOWLEDGE_ARCHITECTURE.md`,
`/root/memory/foundation/governance/COLLECTIVE_MEMORY_ARCHITECTURE.md`,
`/root/memory/foundation/governance/MULTI_ENVIRONMENT_OPERATING_RULE.md` e contratos
de adaptadores em `/root/memory/foundation/adapters/`.

## 2. Modelo proposto: responsabilidade de cada camada

| Camada | Conteúdo e autoridade | Gestão no ForgeHub |
|---|---|---|
| Foundation | Regras, contratos, arquitetura e decisões de governança aprovadas. | Foundation, documentação, revisão e histórico de versões. |
| Knowledge Base | Conhecimento durável com autoria: procedimentos, incidentes, decisões e descobertas. Candidatos continuam identificados como candidatos. | Knowledge Base, índice por agente, revisão e promoção por Mnemosyne/Scriba. |
| Memória curta do runtime | Preferências estáveis e poucos fatos de uso recorrente, dentro do orçamento real de cada runtime. | Agentes: ocupação, limite, origem, última manutenção e revisão de compactação. |
| Hindsight | Busca semântica derivada, com referência à fonte e à versão. Recall é consultivo. | Hindsight: saúde, recall, retenção, filas e proveniência. |
| Arquivo privado e memória estruturada | Conversas privadas e estado de continuidade no runtime; `knowledge.db` quando usado pelo perfil. | Inventário e saúde com controle de acesso; conteúdo não é publicado automaticamente. |
| Estado de desenvolvimento | Projetos, planejamento, tarefas, aprovações, execução, commits e releases. | Domínios já existentes da Software Factory. |
| Comunicação | Solicitações, despacho e respostas entre agentes e ambientes. | Messages, ligado às tarefas e evidências correspondentes. |

O conteúdo de uma tarefa não deve virar uma instrução permanente só porque apareceu em uma
conversa. Uma decisão durável pode gerar um documento revisado; o andamento da tarefa continua
no ForgeHub. Reindexar uma fonte no Hindsight não autoriza apagá-la.

### Identidade e proveniência

Separar identidade lógica do agente, runtime, instância e ambiente. O nome exibido não basta
para decidir quem escreveu uma memória. Os documentos atuais usam Aramis/Codex,
Porthus/Claude e Dartan/Gemini; a referência de Marcelo a Aramis no Claude deve ser
reconciliada com o cadastro e a sessão reais, sem renomeação presumida.

Metadados propostos para material coletivo: `document_id`, `source_uri`, versão/hash,
`source_agent_id`, `runtime`, `agent_instance_id`, `infra_environment_id`, escopo de
acesso, classificação, projeto quando aplicável, data, estado de revisão e
`supersedes` para correções. Expiração pertence ao tipo de informação; preferências e
decisões não devem ser descartadas por uma janela genérica de 90 dias.

## 3. Dependência do planejamento local/VPS do Claude

O desenho de ambientes, identidade entre instalações, infraestrutura, replicação,
retransmissão e implantação pertence ao planejamento em andamento pelo Claude. Aguardar
sua conclusão e conciliar os contratos antes de implementar. Não criar schema, cadastro,
ponte, configuração central alternativa ou alterações em compose por este plano.

Este trabalho fornece somente requisitos de integração:

- Cada instância precisa conhecer seu ambiente, caminhos autorizados, endpoint/banco
  Hindsight e versão do contrato. Consumir o mecanismo definido pelo planejamento do Claude.
- Foundation e KB locais observadas: `/root/memory/foundation` e
  `/root/memory/knowledge_base`. Valores físicos da VPS precisam de validação própria.
- Distinguir caminho do host, volume do contêiner e endpoint HTTP. Mesmo nome `hermes`
  em duas instalações não comprova memória sincronizada.
- Atualizar fontes de contexto, hooks, scripts e descrições de ferramentas de forma
  coordenada, por seus proprietários. Preservar links de compatibilidade e arquivos históricos.
- Invalidar caches de caminhos/fontes quando a versão mudar, mantendo proveniência das
  correções. Uma memória antiga não deve sobrepor o contrato atual do ambiente.
- Respeitar autonomia dos ambientes e escopo de acesso. Não propagar conversas privadas,
  dados de cliente ou acesso a bancos por mera conveniência de sincronização.
- A futura interface deve distinguir ambiente verificado de desconhecido/desatualizado.

O documento `docs/architecture/MULTI_ENVIRONMENT_INFRA_AND_IDENTITY.md` foi consultado
como contexto e não foi editado. Sua versão final e eventuais documentos sucessores serão
as dependências de integração; o conteúdo proposto atual não é considerado implementado.

## 4. Manutenção preventiva proposta

1. Inventariar todos os agentes ativos e suas superfícies reais de memória. Medir caracteres
   conforme a semântica de cada runtime, incluindo separadores; registrar ausente, ilegível,
   desabilitado e não aplicável como estados distintos. Não criar memórias para perfis inativos.
2. Adotar, inicialmente, aviso a partir de 80% e criticidade a partir de 90% do orçamento.
   Esses percentuais são proposta, não configuração já aplicada. Não aumentar limites para
   contornar a ausência de curadoria.
3. Validar as escritas gerenciadas no arquivo correto, respeitando bloqueios de concorrência,
   escrita atômica e orçamento. Não alterar a instalação do Hermes sem necessidade demonstrada.
   Escritas externas por shell continuam exigindo detecção de desvio; não se promete impedir
   qualquer edição fora das interfaces gerenciadas.
4. Fazer checagem leve no ciclo do runtime e uma auditoria determinística diária. Reparar o
   agendador existente e confirmar execuções reais. Definir um único executor por ambiente,
   com lock e política de repetição; evitar dois jobs compactando o mesmo arquivo.
5. Gerar proposta de consolidação quando necessário: eliminar redundância, converter detalhes
   operacionais em documentos apropriados e manter referências curtas. Meta inicial: ficar
   abaixo de 70% após consolidação, preservando as informações essenciais.
6. Antes de qualquer substituição, manter snapshot privado recuperável e mostrar a diferença.
   Conteúdo semanticamente reescrito exige revisão; na primeira implantação, aprovação humana.
   Cópias para a KB passam por classificação e redação. Não enviar a memória bruta para o
   espaço coletivo apenas para liberar caracteres.
7. Alertas devem ser deduplicados por ambiente/agente/arquivo/condição. Quando autorizada a
   automação operacional, o incidente cria ou atualiza um item de planejamento/tarefa na
   Software Factory e usa Messages para despacho. Registrar resultado e evidência de recuperação.
8. Retenção Hindsight e limpeza de logs são rotinas separadas da compactação de memória curta.
   Confirmar código, backup, filtros de retenção e restauração antes de habilitar exclusões.

## 5. Adaptadores internos e externos

Definir um contrato comum de resultado, mantendo os eventos nativos de cada runtime:
início de sessão, recuperação de contexto, publicação de fato revisado, arquivo privado,
fila de retenção, recuperação após falha e manutenção de memória curta quando aplicável.

Cada externo realiza e valida somente a própria adequação seguindo a cartilha: Codex,
Claude e Agy/Antigravity. O coordenador define contrato e aceite coletivo; não sobrescreve
configurações privadas dos outros runtimes. Cada agente entrega inventário, backup,
diferença aplicada, versão do contrato e evidências dos testes em sua tarefa autorizada.

Para Hermes, confirmar quais memórias são efetivamente carregadas com o provider Hindsight
ativo e quais hooks rodam em CLI, gateway e cron. Para Codex e Claude, testar os adaptadores
existentes com payloads compatíveis com as versões instaladas. Para Agy, testar Antigravity
separadamente de Gemini CLI; se a superfície não suportar os eventos necessários, projetar
uma ponte explícita e verificável, sem anunciar paridade automática.

Todos os adaptadores devem consumir a configuração do ambiente, respeitar os mesmos metadados
de proveniência e expor estado com data de verificação. Indisponibilidade de Hindsight não
deve bloquear a tarefa: usar fontes canônicas acessíveis, indicar recall indisponível e
preservar uma fila de retenção protegida e idempotente.

Medir separadamente: hook invocado, serviço acessível, recall concluído, retain aceito,
processamento concluído e recuperação posterior do fato. Um HTTP 200 de saúde ou aceite
assíncrono não comprova o ciclo inteiro.

## 6. Integração visual e operacional no ForgeHub

Proposta baseada no reaproveitamento dos módulos existentes:

- **Agentes:** seção de memória por agente/instância; distinguir contrato de perfil e
  memória curta real; permitir inspeção conforme permissões.
- **Hindsight:** ampliar a tela com visão de memória do ambiente, saúde dos adaptadores,
  ocupação/limites, manutenção, fila e versão das fontes. Detalhes técnicos aparecem somente
  onde ajudam a diagnosticar ou decidir.
- **Foundation / Knowledge Base / Docs:** fontes, índices, candidatos e revisão; vincular
  documentos ao projeto/incidente sem manter cópias divergentes.
- **Software Factory:** iniciativa de gestão de memória vinculada a produto, versão,
  projeto, planejamento, tarefas, responsáveis e critérios de validação; execução nos
  módulos existentes de projetos, governança, cockpit e fechamento de versão.
- **Messages:** despacho e retorno de tarefas de manutenção/curadoria, preservando
  referência ao registro de trabalho, autoria e ambiente.
- **Controle de versão:** ligar mudanças de código/configuração/documentação aos commits
  e evidências da entrega. Segredos e arquivos privados não entram no repositório.
- **Crons / Auditor:** exibir execução real, falhas consecutivas e cobertura por agente,
  com links para as ações corretivas.

Aplicar o sistema visual registrado em `DESIGN.md`, permissões existentes, estados de carga,
erro, ausência de dados e dados desatualizados. Esta etapa de planejamento não altera telas
nem cria registros oficiais de tarefa.

## 7. Sequência de implantação e critérios de aceite

| Etapa | Entrega planejada | Critério de aceite |
|---|---|---|
| 0. Recuperação P0 | Preservação e inventário dos dados/comandos perdidos; restauração seletiva planejada. | Cada item tem fonte, diferença e teste; reativação somente após validação. |
| 1. Inventário e preservação | Matriz agente/runtime/ambiente, memórias realmente consumidas, backups e mapa de leitores/escritores. | Arquivos corretos identificados; snapshot e restauração verificados em cópia; mudanças anteriores do checkout preservadas. |
| 2. Configuração e referências | Resolução comum de caminhos; atualização de fontes de contexto e montagens; compatibilidade temporária. | Novo prompt de cada superfície validada cita as raízes atuais; alteração de caminho invalida cache; referências históricas ficam classificadas. |
| 3. Limites e manutenção | Contagem correta, alertas, proposta de consolidação, proteção das escritas e reparo do agendador. | Casos de 80%, 90% e excesso detectados; arquivo preservado quando inválido; concorrência segura; execução diária comprovada. |
| 4. Autoconfiguração | Cada externo aplica a cartilha à própria instância; responsável interno valida Hermes. | Ciclo com dado sintético comprovado; indisponibilidade e repetição não perdem nem duplicam registros. |
| 5. ForgeHub e alertas | Auditoria de coerência, revisão/tarefa/mensagem e notificações por exceção. | Execução normal gera zero alertas; incidente acionável alerta uma vez; permissões e fluxos validados. |
| 6. Integração com ambientes | Após conclusão do plano do Claude, piloto compatível com a arquitetura aprovada. | Contratos conciliados e sem alterações sobrepostas; testes local/VPS aprovados conforme o plano responsável. |

Arquivos candidatos à implementação futura: módulos `agent_profile_files`, `agent`,
`hindsight`, `foundation`, mecanismos de cron/auditoria, `host-bridge/app.py`, telas de
Agentes/Hindsight, configurações de montagem, adaptadores nos runtimes e fontes ativas
da Foundation. Criar módulos auxiliares pequenos para resolução de caminhos e auditoria;
evitar concentrar toda a lógica no arquivo principal do bridge.

Testes previstos: unitários para resolução host/contêiner e contagem Unicode; integração
para limites, permissões, locks e escrita atômica; fixtures dos hooks por runtime;
falhas de Hindsight e reentrega; correção de fato e invalidação de cache; vinculação
Messages/tarefa; isolamento por ambiente; restauração de snapshot. Usar dados sintéticos
para testes de retenção e remover artefatos de teste de forma identificada e controlada.

Rollback por etapa: restaurar somente arquivos modificados por essa etapa a partir dos
snapshots identificados, manter os links de compatibilidade e preservar dados criados
depois do backup. Migrações de banco, se necessárias, serão aditivas; não executar
restauração integral de banco como rollback de uma alteração de configuração.

## 8. Decisões propostas para aprovação antes de implementar

- Reutilizar Messages e Software Factory, acrescentando a gestão de memória às telas
  existentes de Agentes/Hindsight e aos fluxos de revisão.
- Adotar configuração por ambiente e fontes versionadas; manter Hindsight e arquivos
  privados independentes por instalação.
- Começar com limites atuais, avisos 80%/90%, meta de consolidação abaixo de 70% e
  revisão humana das primeiras compactações.
- Validar o mecanismo real do Antigravity e a correspondência entre nomes de agentes,
  runtimes e instâncias antes de atribuir memórias ou alterar identidades.
- Implantar primeiro no local e só depois na VPS, após aceite do piloto e confirmação
  direta de acesso, topologia e saúde, condicionado à sequência final do planejamento do Claude.
- Aguardar o planejamento local/VPS; cada externo corrige sua própria configuração.
- Recuperar dados/comandos com evidência; notificar somente incidentes e decisões que
  exijam atenção; conservar conhecimento útil como memória contínua.

Após aprovação do desenho, registrar o trabalho nos domínios corretos do ForgeHub e
detalhar tarefas de implementação por componente. Nenhuma mudança operacional, publicação
de memória coletiva, mensagem a agentes ou implantação foi executada nesta etapa.

## 9. Dimensionamento e qualidade da memória contínua

Separar três limites: memória curta do runtime, contexto consultado por pergunta e capacidade
física do armazenamento. Relevância é avaliada antes da retenção; tamanho de banco não é
critério suficiente para decidir o que constitui informação inútil.

| Recurso | Proposta inicial de piloto | Regra |
|---|---|---|
| Hermes `memories/MEMORY.md` | Manter 2.200 caracteres; meta de até 1.540 após curadoria. | Aviso em 1.760; crítico em 1.980; contagem conforme o runtime. |
| Hermes `memories/USER.md` | Manter 1.375 caracteres. | Preferências verificadas; mesmos percentuais de ocupação. |
| Memória curta dos externos | Cada proprietário declara e testa o orçamento da superfície real. | Não aplicar limite Hermes a arquivos de instrução Codex/Claude/Agy. |
| Recall Hindsight normal | Até 1.200 tokens; selecionar inicialmente até 4 fatos/fontes relevantes, conforme suporte da API. | Menos resultados ou nenhum quando não houver relevância. |
| Contexto adicional recuperado total | Até 4.000 tokens somando Foundation, KB e Hindsight. | Orçamento compartilhado; instruções obrigatórias nativas têm contrato próprio. |
| Fato candidato à retenção | Um assunto; alvo até 600 caracteres e limite inicial de 1.200. | Dividir assuntos ou referenciar documento completo; não truncar silenciosamente. |
| Publicação por turno | Zero por padrão; até 5 fatos candidatos duráveis na interação comum. | Ingestão documental em lote é outro fluxo, com revisão e deduplicação. |
| Armazenamento Hindsight local | Orçamento inicial de observação de 1 GiB para o banco, condicionado à capacidade do volume. Baseline observado de aproximadamente 389 MiB. | Limite operacional provisório; sem descarte automático ao atingir a quota. |

Os valores adicionais são propostas, não capacidades já implementadas. Validar suporte da
versão instalada e calibrar em 14 dias: duplicação, relevância, correção dos fatos, latência,
volume diário e capacidade incluindo índices, WAL e backups. Alertas de armazenamento
consideram também espaço livre real e previsão de esgotamento; não só a quota proposta.

### Política de admissão e atualização

- Exigir utilidade futura, fonte verificável, autor/ambiente, classificação e escopo de acesso.
- Verificar duplicatas por ID/hash e equivalência de conteúdo antes de reter.
- Uma correção deve identificar o fato substituído; apresentar a versão vigente no recall
  e conservar histórico/proveniência acessível pela auditoria.
- Preferências vigentes, decisões aprovadas, arquitetura e procedimentos permanecem enquanto
  úteis; não expiram por uma regra genérica de 90 dias.
- Logs, andamento e conclusão de tarefas, tentativas e conversas brutas ficam nos sistemas
  de origem. Não converter toda interação em conhecimento permanente.
- Candidatos mantêm sua classificação até revisão. Publicação na KB não implica aprovação
  nem incorporação automática ao conjunto de fatos validados do Hindsight.
- Inventariar o conteúdo existente em modo de relatório antes da curadoria: duplicatas,
  ausência de fonte, fatos superados e material transitório. Tipos `world` e `experience`
  sozinhos não definem relevância nem autorizam exclusão.

## 10. Recuperação de dados e comandos — prioridade P0

A recuperação precede qualquer manutenção que possa eliminar ou substituir conteúdo.
O relato ainda exige determinar precisamente os conjuntos afetados; não presumir que a
perda está limitada a `MEMORY.md` ou que todo comando ausente foi apagado.

1. Identificar jobs, prompts/comandos, scripts, cadastros e memória afetados, com ambiente
   e período. Classificar ausência real, caminho antigo, registro oculto, duplicidade,
   comando incompleto ou falha de execução.
2. Preservar o estado atual e cópias de recuperação **antes** de usar rotas que atualizam
   `.jobs.json.good`. JSON válido pode conter perda de registros; parse não comprova completude.
3. Comparar `jobs.json`, `.jobs.json.good`, snapshots e cópias de curadoria, arquivos no disco,
   catálogo PostgreSQL, histórico Git e versão implantada. Não editar as fontes de comparação.
4. Produzir lista por item: ID, dono, ambiente, fonte/data/hash, diferença e confiança.
   Não reconstruir um comando por adivinhação a partir do nome do job.
5. Restaurar seletivamente os itens aprovados, inicialmente desabilitados. Preservar IDs,
   horários, timezone, parâmetros e estado verificados; não executar automaticamente jobs
   restaurados, especialmente limpeza, envio externo ou alteração de infraestrutura.
6. Reproduzir causas em cópia: texto longo, edição parcial, concorrência, reinício durante
   gravação, JSON válido incompleto e migração de caminhos. Verificar o código implantado:
   o truncamento histórico já está corrigido no checkout consultado.
7. Validar comando completo, cobertura recuperada e teste controlado antes de reativar.
   Listar explicitamente itens irrecuperáveis ou sem fonte confiável.

Fontes candidatas observadas: `cron/.jobs.json.good` de Athos/Atlas;
`/root/.hermes/profiles/athos/state-snapshots/20260611-125028-pre-update/cron/jobs.json`;
cópias `skills/.curator_backups/<data>/cron-jobs.json`, incluindo 2026-09-01. Ainda não
foram certificadas como fonte correta de restauração. O comando `hindsight_prune.py`
não existe no caminho indicado pelo job atual e requer rastreamento específico.

## 11. Notificações por exceção

A orientação atual de Marcelo substitui a regra antiga de notificar toda conclusão.

| Evento | Comportamento proposto |
|---|---|
| Task/cron agendado, iniciado, em progresso ou concluído normalmente | Histórico de execução e resultado; zero alerta, push ou incremento do sino por esse motivo. |
| Resposta/artefato solicitado | Devolver no contexto da solicitação, sem aviso adicional de execução. Outro canal só quando solicitado. |
| Perda/corrupção confirmada ou comando desaparecido | Um alerta imediato com evidência e ação necessária. |
| Falha transitória recuperável | Registrar e repetir conforme política da rotina; não alertar cada tentativa. |
| Falha persistente, bloqueio, prazo relevante ou capacidade crítica | Um alerta acionável por incidente e ambiente. |
| Aprovação humana necessária | Solicitação objetiva vinculada ao registro que precisa de decisão. |
| Recuperação de incidente alertado | Resolver o mesmo incidente no painel, sem nova notificação de sucesso. |

Deduplicar por entidade/causa/ambiente e repetir somente por agravamento, prazo de ação
vencido ou política explícita. Proposta inicial: rotinas críticas alertam na primeira
falha confirmada; recuperáveis após 3 falhas consecutivas ou prazo operacional excedido,
o que ocorrer primeiro. Definir criticidade por rotina antes da ativação.

Revisar os produtores em `backend/app/api/routes/notifications.py`,
`backend/app/core/feedback.py`, scripts, scheduler, bridge e canais externos, além de
sino/toast. Separar histórico de execução da fila de alertas; não apenas esconder sucessos
no frontend. Preservar histórico e impedir reingestão de sucessos antigos como não lidos.
Não marcar `feedback_sent_at` como enviado quando só houve supressão de alerta: devolução
do resultado e notificação precisam de estados coerentes.

## 12. Auditoria de coerência do ForgeHub

Cobrir os fluxos deste contexto, da entrada à persistência e apresentação. O aceite precisa
ter evidência por rotina; testes pontuais não comprovam correção integral da plataforma.

- Banco/schema, migrações, volumes, caminhos e código implantado, conciliados com o Claude.
- Fonte de verdade de cada cadastro e edição sem perda entre API, formulário, banco e disco.
- Identidade/runtime/ambiente e permissões sem colisão de instâncias.
- Messages como comunicação e Software Factory como gestão, com vínculos e estados coerentes.
- Cron cadastrado, comando presente, execução real, retry, locks, backup e recuperação.
- Alertas por exceção em todos os produtores, sem duplicação nem retomada de ruído antigo.
- Memórias efetivamente consumidas, limites, hooks, revisão, proveniência e operação degradada.
- Documentação ativa correspondente ao código; descrições antigas são pistas, não prova de bug.

Entregar matriz `fluxo → fonte de verdade → rotina → evidência → problema → correção → teste`.
Classificar perda de dados como P0, falha operacional como P1 e melhoria de consistência
como P2. Reproduzir o defeito antes de corrigir, testar depois e registrar limitações.

## 13. Coordenação e conclusão desta etapa

Entregas atuais: este plano e a cartilha, ambos dentro de `docs/`. Correções de código,
restauração, mudanças de configuração, publicação coletiva e notificações a agentes
permanecem não executadas.

Antes da implementação: receber o planejamento local/VPS concluído pelo Claude, conciliar
interfaces e arquivos envolvidos, incorporar a revisão de Marcelo e registrar as tarefas
autorizadas na Software Factory. Cada externo executa sua própria adequação. Não alterar
arquivos compartilhados em paralelo sem definição de responsabilidade e integração.
