# Finalização das pendências de entrega

**Autorização:** solicitação do usuário em 2026-09-14 para finalizar as pendências identificadas.
**Referências:** docs/PENDENCIAS.md; docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md; .worktrees/messages-dispatch-recovery/docs/MESSAGES_DISPATCH_RECOVERY.md.

## Sequência e critérios

- [ ] Validar e integrar recuperação de mensagens preservando alterações locais. Executar testes de autenticação, contingência, backlog, feedback, guardas de execução e resolvedor do bridge. Consultar estados atuais antes de recuperar; não repetir tarefas concluídas nem executar #22121.
- [ ] Validar terminal e caminhos documentais; registrar commits específicos. Conciliar commit conhecido de origin/develop; consultar e publicar remoto com autenticação disponível.
- [ ] Integrar feature/nexo-installer-monitoring e documentação não commitada. Executar testes de builds, pacotes, ingestão, reconciliação e instalação; lint; testes/build frontend.
- [ ] Implementar relatórios persistidos, geração mensal idempotente e sob demanda, revisão e acesso restrito conforme seção 7. Documentos HTML exportáveis com escape e conteúdo derivado dos registros; ausência de dados de horas explícita, sem inventar saldos.
- [ ] Implementar API de leitura com credencial vinculada a um cliente, somente relatórios revisados, isolamento com 404 e testes de acesso cruzado; integrar área autenticada existente Darckware conforme seção 8.
- [ ] Validar builds reais Nexo Linux/Windows e Headscale em ambiente dedicado. Instalação real Windows depende de estação Windows acessível.
- [ ] Conferir migrations no ambiente-alvo, aplicar após validação e implantar revisão identificada; reiniciar bridge e verificar saúde, APIs e recuperação autorizada.
- [ ] Atualizar registros com comandos, resultados, commits e impedimentos comprovados. Não confundir teste sintético com validação de produção.

## Limites observados

GitHub HTTPS sem credencial utilizável (`could not read Username`). Docker requer execução fora do sandbox. Projetos irmãos Darckware e Nexo existem, fora das raízes de escrita do sandbox.
