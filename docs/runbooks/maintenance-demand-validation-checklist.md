# Checklist de validação de demandas de manutenção

Use este roteiro para acompanhar uma demanda da triagem até a conclusão ou correção. Registre o número da demanda e cada mudança de fila; assim fica claro onde o processo parou e qual é o próximo passo.

## Regras de encaminhamento

| Situação que exige ação humana | Destino em Pessoal | Verificação |
|---|---|---|
| Autorização de uma tarefa | Aprovações | A demanda aparece uma vez em Aprovações. |
| Correção ou reconciliação de uma tarefa | Decisões | O link de Mensagens abre o mesmo número em Decisões. |
| Pergunta bloqueante | Respostas | O link abre a pergunta correspondente, identificada pelo mesmo `questionId`. |
| Decisão de incubação | Incubações | A incubação permanece na fila e no fluxo próprios. |

Tarefas em processamento, perguntas e aprovações pendentes não devem aparecer como decisões de correção. Incubações não devem ser duplicadas nas filas de tarefas. Os totais das filas devem corresponder aos itens listados para os mesmos filtros.

## Registro da execução

Preencha uma ficha por demanda. Não inclua senhas, chaves ou outros segredos na evidência.

| Campo | Registro |
|---|---|
| Data/hora e responsável pela validação | |
| Ambiente (teste isolado ou produção, somente leitura) | |
| Número, assunto e origem da demanda | |
| Estado e etiqueta vistos em Mensagens | |
| Decisão pendente e destino esperado | |
| Fila/tela aberta e destino observado | |
| A demanda e o total da fila conferem? | |
| Evidência revisada / divergência encontrada | |
| Ação autorizada e executada | |
| Estado e histórico após a ação | |
| Resultado: aprovado, corrigir ou bloqueado | |
| Próxima etapa, responsável e evidência pendente | |

## Execução e correção

- [ ] **Identificar:** anote número, assunto, origem e estado atual. Distinga uma incubação de uma execução de tarefa.
- [ ] **Ler o motivo:** confira a etiqueta e a evidência do agente. Para correção, registre o que foi entregue, o que ficou pendente e qual critério não foi atendido.
- [ ] **Abrir o destino:** use o link de Mensagens. Para `Precisa de correção` ou `Reconciliação pendente`, confirme Decisões, o mesmo número e o mesmo assunto.
- [ ] **Conferir exclusividade:** confirme que a demanda de correção não aparece em Aprovações ou Incubações e que o total exibido corresponde à lista com os mesmos filtros.
- [ ] **Validar a ação permitida:** abra os detalhes, revise evidências e ações disponíveis. Não converta falha automaticamente em reenvio ou aprovação.
- [ ] **Revisar a confirmação:** antes de confirmar, confira alvo, escopo e efeito descritos no diálogo. Se cancelar, confirme que estado, histórico e despacho permaneceram iguais.
- [ ] **Executar em fixture isolada:** para teste de confirmação, use somente demanda de teste no ambiente isolado. Confirme apenas a ação permitida e registre a resposta do backend.
- [ ] **Verificar o resultado:** atualize a lista e confira estado, histórico, contagem e destino. Registre cada transição; se a execução parar, deixe a etapa seguinte marcada como pendente.
- [ ] **Encerrar ou encaminhar:** marque como aprovado quando todos os critérios e evidências estiverem presentes; caso contrário, deixe explícitos o item que precisa de correção, o responsável e a próxima verificação.

## Conferências de separação das filas

- [ ] Autorização de tarefa abre Aprovações.
- [ ] Correção/reconciliação abre Decisões.
- [ ] Pergunta bloqueante abre Respostas e a pergunta certa.
- [ ] Incubação abre Incubações; links antigos de decisão continuam na fila de incubação.
- [ ] Aprovações e perguntas bloqueantes não são contadas como decisões de tarefa.
- [ ] Uma demanda não aparece em duas filas de trabalho; contagens e linhas usam os mesmos filtros.

## Evidência de teste

Para homologar uma alteração de fluxo, use fixtures isoladas e registre:

- [ ] ID e número da fixture de cada tipo (autorização, correção, reconciliação, pergunta e incubação).
- [ ] URL/destino esperado e observado, incluindo o número ou `questionId`.
- [ ] Fila, total e presença/ausência da linha antes e depois.
- [ ] Resultado do cancelamento sem mutação e da confirmação somente na fixture.
- [ ] Comandos de verificação e resultado, além de limitações de navegador ou ambiente.

Não use demandas reais para testar ações de confirmação ou despacho. Uma validação somente de leitura em produção pode registrar divergências, mas qualquer ação real exige a autorização operacional já estabelecida para aquela demanda.
