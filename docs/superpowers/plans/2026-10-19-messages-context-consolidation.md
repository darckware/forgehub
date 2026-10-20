# Messages — consolidação por projeto e área

**Estado:** análise concluída; desenho aprovado por Marcelo nesta conversa; implementação em andamento.

**Objetivo:** substituir o contexto espalhado em falhas e incubações antigas por resumos rastreáveis em Incubação, sem reexecutar trabalho nem apagar o histórico.

## Diagnóstico e desenho aprovado

A triagem anterior deixou 34 registros: 22 falhas e 12 incubações. Todos estão sem `project_id`; os três projetos cadastrados não correspondem aos assuntos. Usar áreas operacionais nesses casos, sem criar projetos fictícios. Quando existir projeto vinculado, usar o projeto real.

Consolidação inicial em cinco áreas:

| Área | Responsável | Registros |
| --- | --- | --- |
| Operação dos agentes | Athos | #26382, #28816, #28818, #28990, #29060, #29061, #29065, #29078, #29079, #29082, #29084, #29088, #29109, #29126, #37595 |
| Infraestrutura | Hephaestus | #27024, #27027, #28860 |
| Backup | Hephaestus | #26996, #28817, #28856, #29074, #29075, #29128 |
| Segurança | Aegis | #28288, #28833, #28842, #28846, #29067, #29068, #29069, #29070, #29086 |
| Maia / WhatsApp | Maia | #37588 |

Cada resumo informa objetivo, situação comprovada, entregas parciais, pendências, dependências, próximos passos e os registros originais. Execuções incertas mantêm o run e a indicação de reconciliação pendente; consolidar não equivale a resolver ou tentar novamente.

## Dados e regras

- Adicionar `context_area` para classificar mensagens sem projeto e `consolidated_into_id` para ligar origens ao resumo.
- Criar o resumo em Incubação, com dono e prazo de decisão, sem agendamento ou chamada ao runner.
- Arquivar as origens na mesma transação, preservando texto, erro, tentativas, run e anexos.
- Registrar a operação na auditoria; repetição sobre as mesmas origens não cria outro resumo.
- Recusar origens ativas, já arquivadas sem vínculo de consolidação ou de contextos incompatíveis.
- Impedir reprocessamento de origens consolidadas e apagar um resumo enquanto ele tiver origens vinculadas. A consulta do histórico continua permitida.
- Incubações arquivadas não amadurecem novamente.
- O endpoint de consolidação é administrativo. A consolidação inicial usa os mesmos serviços e uma seleção explícita dos 34 registros, sem incluir tarefas criadas depois da triagem.

## Ajustes na tela Messages

- Filtro por projeto/área, aplicado às listas, contagens e demais visões.
- Acesso aos resumos pela navegação existente, preservando o ciclo de Incubação.
- Detalhe com contexto e registros de origem; origens arquivadas oferecem acesso ao resumo.
- Links diretos por mensagem permitem abrir as referências do texto sem procurar manualmente em pastas.
- Controles e textos seguem o tema, os componentes e os idiomas existentes; sem redesenho geral da tela.

## Etapas e critérios de aceite

- [ ] Criar regressões da consolidação: atomicidade, idempotência, preservação de erro/run e recusa de execução ativa/contexto misturado.
- [ ] Adicionar migração e serviço de consolidação, endpoint autenticado e guardas de execução/exclusão/maturação.
- [ ] Implementar filtro contextual, detalhe e navegação por vínculo; testar o comportamento em React.
- [ ] Executar testes backend afetados, testes frontend, build, linter e verificação visual em navegador.
- [ ] Aplicar a consolidação dos 34 registros em cinco resumos; conferir origens arquivadas, auditoria, ausência de execução automática e preservação das sugestões pessoais.
- [ ] Registrar os números dos novos resumos e o resultado real da publicação/validação.

**Aceite final:** cinco resumos em Incubação; os 34 registros anteriores arquivados e vinculados; consulta por área/projeto em Messages; resultados incertos preservados; nenhum trabalho reexecutado pela consolidação.
