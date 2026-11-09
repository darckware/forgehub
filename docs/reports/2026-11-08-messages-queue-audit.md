# Messages: filas, coerência e reconciliação automática

Análise solicitada por Marcelo em 08/11/2026, antes das demais pendências do ForgeHub.
Snapshot: **08/11/2026 21:50 -03 (09/11 00:50 UTC)**. Consultas de produção em transações
somente de leitura. Nenhuma mensagem foi consumida, arquivada, promovida ou despachada.
O pedido adicional inclui eliminar tarefas obsoletas e avisos sem ação, como feedback ao
próprio agente. As regras de automação abaixo são propostas, não funcionalidades entregues.

## Situação verificada

157 mensagens não arquivadas:

| Pasta segundo os predicados atuais da interface | Quantidade | Observação |
|---|---:|---|
| Entrada | 3 | #42233, #42234, #42235 |
| Saída | 1 | #42255 |
| Em execução | 7 | Seis tentativas encerradas com falha e uma espera de nova tentativa (#42232) |
| Incubação | 6 | Três maduras aguardando decisão e três ainda na janela de maturação |
| Finalizadas | 140 | Inclui diagnósticos e avisos informativos, além de trabalho entregue |

**Execuções efetivamente ativas: zero.** O agendador tem cinco vagas livres. Os seis run IDs
das tentativas visíveis como falha têm estado terminal `completed` no armazenamento do runner;
o Messages as classificou como falha por relatório ausente ou `PARTIAL`. Isso não comprova
conclusão do trabalho nem autoriza repeti-lo.

Há cinco mensagens ainda sem despacho: as três da Entrada, #42232 e #42255. Nenhuma delas
tem vínculo `origin_id` com ProjectTask. Aliás, nenhuma das 157 mensagens visíveis tem esse
vínculo. Portanto, não há um ProjectTask aceito que possa reconciliar essas entregas por ID.

## Entradas e nova tentativa: trabalho já entregue

| Mensagem | Diagnóstico | Tratamento indicado |
|---|---|---|
| #42232 | Configuração de acesso e fechamento por evento entregues no commit 4b6ef28; aguarda Porthus até 09/11 23:05 -03 | Vincular a entrega verificada, encerrar a necessidade de execução e cancelar o agendamento antigo |
| #42233 | Transferência de arquivos entregue e publicada em 4b6ef28 | Reconciliar com a entrega; não despachar novamente |
| #42234 | Segredos restritos entregues em ForgeVault 21dfa9e, com sete chaves ativas protegidas | Reconciliar o escopo efetivamente entregue e preservar os limites documentados sobre administradores e alertas |
| #42235 | Retenção de 90 dias entregue e publicada em 4b6ef28 | Reconciliar com código, testes e configuração de produção |
| #42255 | Correção de backup ainda necessária; não executada | Revalidar disponibilidade do executor e a condição do provedor antes de liberar qualquer efeito |

As quatro primeiras ficaram com `fixed_agent=true` em Porthus, embora a continuação tenha
sido autorizada e realizada por Aramis nesta sessão. O agendador desconhece a entrega externa.
Apagar a espera de cota sem antes reconciliar a entrega pode fazer trabalho já publicado rodar
novamente. As evidências da publicação estão em
[remote-access-continuation](../implementation/2026-11-08-remote-access-continuation.md).

## Cota: indisponibilidade registrada e disponibilidade observada divergem

| Executor | Bloqueio persistido até (-03) | Fonte |
|---|---|---|
| Aramis / Codex | 11/11 06:45 | Erro real do run #42185, em 06/11 |
| Dartan / agy | 11/11 09:54:57 | Erro real do run #42180, em 06/11 |
| Porthus / Claude | 09/11 23:00 | Run #42232 |

O registro do Codex está em conflito com observação posterior: sua sessão nativa está
executando trabalho e a telemetria de 08/11 21:52 -03 informa 55% de uso da janela curta e
47% da semanal, sem limite atingido. Isso demonstra saldo nesta sessão; não se deve inferir
disponibilidade de Porthus ou Dartan, ou de outra conta/modelo, a partir dela.

`record_usage_limit` cria ou prolonga a indisponibilidade; `unavailable_agents` confia na data.
Não há reconciliação automática dessa informação com sucesso posterior na sessão nativa.
`can_switch` também impede substituição quando há agente fixo, aprovação, execução de tarefa,
contexto de missão ou diagnóstico associado. Essas proteções têm função e não devem ser removidas
em bloco para fazer a fila andar.

## As seis tentativas encerradas

| Mensagem | Evidência e coerência | Tratamento indicado |
|---|---|---|
| #42198 | Proposta Moodle `finished/completed`; saída contém `STATUS: DONE` com nota de evidência | Reavaliar com o parser atual e o registro da proposta; encerrar sem repetir a operação |
| #42199 | Mesmo caso: proposta persistida como concluída e relatório DONE | Mesma reconciliação, preservando a tentativa original |
| #42209 | Proposta aprovada foi executada, mas o relatório pede matrícula complementar | Separar o que foi aprovado/executado do complemento pendente; não recriar cadastro |
| #42211 | Relatório pede informação de curso para continuar | Classificar como aguardando informação, sem retry automático da escrita |
| #42215 | Relatório interpretou `E M` como identificação de aluno; correção dessa interpretação foi entregue depois | Reavaliar a mensagem original e as respostas posteriores; não repetir cadastro por causa da falha antiga |
| #42252 | Diagnóstico produziu evidências de backup bloqueado, mas não terminou com STATUS válido | Reconciliar a atividade diagnóstica e vinculá-la à continuação #42255; não confundir diagnóstico concluído com backup corrigido |

O parser atual já tolera as notas de evidência que causaram as falhas históricas de #42198 e
#42199. O finalizador, porém, retorna imediatamente para uma falha terminal conhecida; publicar
a correção do parser não reavalia esses registros. Para #42209, `MoodleApproval.outcome=completed`
comprova a proposta aprovada, não todas as ações adicionais descritas no relatório.

## As seis incubações

| Mensagem | Situação | Tratamento indicado |
|---|---|---|
| #41881 | Backup externo ainda pendente, agora também tratado por #42247/#42255 | Unificar acompanhamento por vínculo explícito; manter o problema aberto em um único lugar |
| #41882 | Hardening ECO-047; há implementação/documentação local e cópia do verificador diferente da instalada | Revalidar o escopo e a execução real antes de encerrar; não criar outro pacote de correção do mesmo achado |
| #41884 | Incidente antigo de auditoria/métricas/briefings, sem comprovação completa atual | Conferir separadamente cada critério e encerrar somente os que tiverem prova |
| #42164 | Correção descrita como autorizada, mas armazenada como incubação; maturação em 09/11 08:13 -03 | Validar a autorização registrada e promover para uma ação concreta; investigar entrega do briefing sem reenviá-lo |
| #42179 | Escopo correspondente entregue pela #42228; ECO-060 integrado e evidências permanentes presentes | Reconciliar com #42228 e encerrar a incubação já atendida após conferir os critérios |
| #42219 | Melhorias futuras do Moodle; corpo exige terminar #42218 e nova ordem de Marcelo | Manter aguardando autorização; maturação não autoriza implementar |

O diagnóstico #42167 não substitui #42164: ele declara expressamente que a entrega Telegram
de #42151/#42157 ficou fora de seu escopo. Semelhança de assunto não comprova duplicação.

Hoje a maturação somente marca `decision_pending`, limpa `agent_processed_at` e emite aviso.
Ela não garante uma decisão do dono. Os três itens maduros continuam pendentes de decisão.

## Coerência: mensagens para o próprio agente

139 das 157 mensagens são dirigidas ao próprio remetente. Isso não torna todas inúteis:
uma rotina, uma operação Moodle autorizada ou uma tarefa de implementação realmente executada
podem ter legitimamente o mesmo solicitante e executor.

Há, contudo, **sete avisos de falha para o próprio agente**, sem nova ação executável:
**#42188, #42200, #42201, #42210, #42212, #42216 e #42254**. São retornos informativos já
marcados `completed`, com `reply_to_id` e sem diretório de execução. O conteúdo apenas manda
consultar a tarefa original. Eles devem ser eventos/notificações anexados à origem, e podem
sair da fila ativa com motivo e vínculo, sem afetar o desfecho da tarefa original.

O caminho `feedback.deliver_feedback` cria esses retornos quando não pode abrir diagnóstico,
inclusive quando remetente e destinatário são iguais. O reconhecimento pelo inbox pode
arquivá-los depois, mas depende de o agente consultar a caixa. Assim, um aviso sem trabalho
fica armazenado como Task e contado entre as finalizadas até esse reconhecimento.

Também há **96 diagnósticos** na lista, dos quais 90 são para o próprio agente (89 concluídos
e um falho). Diagnóstico pode ser trabalho útil, mas a quantidade revela acompanhamento
fragmentado. Concluir a checagem não resolve automaticamente sua origem, e novas continuações
criadas só com referência no texto voltam a gerar novas checagens. Convém consolidar a mesma
cadeia de tratamento, sem apagar suas tentativas ou atribuir conclusão à origem por inferência.

Outro problema de coerência está em #42255: a execução exige descobrir um reset do Google
Drive que os próprios registros dizem não ter sido informado. Falta uma condição verificável
de retomada. Corrigir a disponibilidade do Codex não resolve esse segundo bloqueio. O fluxo
precisa registrar a evidência disponível de recuperação do serviço, sem inventar horário e
sem repetir upload ou backup já realizado.

## Regras recomendadas para o tratamento automático

1. **Reconciliar antes de despachar.** Verificar entrega vinculada por tarefa, mensagem de
   continuação, aprovação/proposta, commit e versão publicada. Se o escopo exato foi atendido,
   retirar da fila com `atendida por outra execução`, registrar executor real e provas e
   invalidar o agendamento antigo. Preservar falhas anteriores; nunca inventar um run.
2. **Separar trabalho, tentativa e comunicação.** Estados de negócio como aguardando informação,
   autorização, serviço externo e entrega verificada precisam ser distintos de processo rodando
   ou encerrado. “Em execução” deve indicar claramente quais processos estão ativos.
3. **Eliminar ruído na origem.** Retorno ao mesmo agente vira evento/notificação na tarefa;
   não cria outra Task. Uma tarefa para si continua possível quando houver ação executável.
4. **Conferir coerência ao criar.** Exigir objetivo acionável, responsável compatível, contexto,
   diretório quando executável, critério de conclusão e vínculo à origem. Uma correção pronta
   para executar não deve cair silenciosamente na incubação; ideia sem autorização não vira Task.
5. **Deduplicar com provas e vínculos.** Mesmo título, mesmo agente ou texto parecido só gera
   candidato. Cancelar/arquivar automaticamente apenas correspondências verificadas; dúvidas
   viram pendência de decisão, com a justificativa visível.
6. **Revalidar cota por identidade e contexto.** Evidência positiva mais recente do mesmo
   runtime/conta/modelo pode superar bloqueio antigo com auditoria. Não sondar em loop nem
   liberar todos os executores porque um deles respondeu.
7. **Incubação precisa de desfecho.** Ao vencer, avaliar pelo dono: atendida, obsoleta,
   consolidada, promovida se já autorizada, ou aguardando decisão explícita. Não agendar
   recursivamente mensagens para o próprio agente apenas para lembrá-lo da anterior.
8. **Aplicação idempotente e segura.** Revalidar versão do registro e run sob lock; nunca
   encerrar execução ativa/incerta por idade ou por 404. Não reenviar WhatsApp/Telegram,
   aceitar ProjectTask sem revisão nem reexecutar operações Moodle durante a reconciliação.

Recomenda-se começar com uma simulação explicando cada ação; depois automatizar os casos
com prova determinística. Avaliação semântica pode sugerir obsolescência e reformulação,
mas não deve apagar evidências nem liberar escrita em sistemas por conta própria.

## Fontes e limites

### Tela Pessoal → Tarefas dos agentes (imagem enviada por Marcelo)

`demand_management.work_state_sql` classifica por campos e precedência fixa, sem análise
semântica: arquivada; falha incerta; falha; execução; concluída; rejeitada; pergunta;
aprovação; incubação vencida; incubação; fila. Uma falha tem precedência sobre uma pergunta,
portanto um relatório `PARTIAL` por falta de informação continua aparecendo como “Falha”.

“Precisam de atenção” inclui aprovação, pergunta, rejeição, incerteza, falha e incubação;
isso não significa “precisa de decisão do Marcelo”. O grupo de tarefas exclui propostas
Moodle vinculadas, que têm aba própria. Os três itens da imagem correspondem a #42252,
#42215 e #42211. Os outros três relatos falhos (#42198/#42199/#42209) têm vínculo de proposta
e são tratados no fluxo Moodle. As quatro entregas paradas de Acesso Remoto são classificadas
como fila, portanto ficam fora do filtro de atenção apesar de precisarem de reconciliação.

`failure_category` usa trechos do erro, com fallback `configuration`; não avalia o pedido
original, a entrega, a falta de informação ou a continuação por outro agente. Esse rótulo
pode atribuir “configuration” a um trabalho parcial ou relatório ausente. O contexto da
tabela usa o nome do projeto ou o `context_area` bruto; por isso aparece um identificador
`instructor:<uuid>:open` onde deveria haver uma identificação compreensível de origem.
O prazo apresentado na tabela é `matures_at`, que pertence à incubação e fica vazio em Task.

A ação principal por linha é arquivar/restaurar; análise contextual e recomendação de
encaminhamento não existem nessa tela. Abrir os detalhes expõe comandos individuais,
histórico e resultado, deixando ao operador a tarefa de reconstruir o contexto. Esse é o
problema operacional a corrigir antes de ampliar o volume de trabalho.

- Banco de produção: `company.agent_demands`, `agents`, `agent_availability`,
  `moodle_message_approvals` e eventos de auditoria dos itens analisados, somente leitura.
- Estado persistido dos seis run IDs no host; não foi chamado cancelamento, despacho ou inbox.
- Telemetria nativa recente do Codex, somente campos de limite e horário.
- Código: `core/agent_availability.py`, `agent_failover.py`, `demand_workflow.py`,
  `demand_failure_check.py`, `feedback.py`, `completion_report.py`,
  `api/routes/demand.py` e os predicados em `frontend/src/hooks/useDemands.ts`.
- Evidências da entrega de Acesso Remoto e integração ECO-060; existência do diretório
  permanente das evidências Moodle. Não foram reexecutadas operações de clientes.

Não foi revalidada cota nativa de Claude/agy, nem o estado atual dos alunos/cursos no Moodle,
nem provocado novo envio para testar a quota do Google Drive. As propostas de encerramento
devem conservar esses limites; a análise não é uma limpeza já aplicada.
