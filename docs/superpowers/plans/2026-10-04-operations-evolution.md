# Evolução da Operação 24x7 — execução

Referência: `docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md`, seções 7–8. O backup externo continua fora desta etapa, por decisão do Marcelo em 2026-10-04.

1. Persistir métricas de execução e mudanças versionadas (`operations_changes`), com migração no schema `company`.
2. Sincronizar resultado, duração, evidência e custo disponível de cada Task com o run da rotina. Custo não observado permanece `NULL`; não estimar valores.
3. Implementar retrospectiva determinística diária/semanal: analisar falhas, ausências, evidência e excesso de "nada a fazer"; gerar propostas com deduplicação.
4. Aplicar A0/A1 dentro dos limites da especificação, guardar estado anterior e janela de avaliação de sete dias. A2 aguarda resposta explícita do Marcelo pelo fluxo de perguntas.
5. Avaliar a métrica ao fim da janela, manter se melhorou ou neutro, desfazer A0/A1 se piorou. Registrar motivo e aprendizado para o relatório semanal.
6. Expor API de evolução/tendência e botão de desfazer; verificar backend/frontend, publicar apenas serviços ForgeHub.

Critérios de aceite: nenhuma mudança A2 se aplica sem resposta afirmativa; toda aplicação tem rollback e registro; reexecução da retrospectiva não duplica propostas; custo ausente não vira zero; os testes cobrem falha → proposta → aplicação → avaliação → reversão.
