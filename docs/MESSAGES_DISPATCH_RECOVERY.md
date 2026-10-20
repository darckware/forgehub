# Messages: recuperação de disparos

## Diagnóstico

O bridge usava um caminho fixo inexistente para o Codex. Uma falha de
disparo causava rollback da sessão; o processamento seguinte acessava
objetos ORM expirados e falhava com `MissingGreenlet`, interrompendo a fila.

## Correções no código

- Cada disparo exige um diretório de trabalho absoluto e explícito. Tasks
  usam `Project.working_directory_path`; canais usam seu próprio diretório ou,
  quando vinculados a um Project, o diretório deste Project. Configuração
  ausente retorna erro e nunca usa `/root` ou outro diretório adivinhado.
- Resolver Codex por `FORGEHUB_CODEX_BIN`, quando configurado, ou por `PATH`.
- Manter identificadores imutáveis entre itens e recarregar cada mensagem.
- Registrar falhas de início com erro sanitizado e contador de tentativas.
- Aguardar 60 e 300 segundos antes das próximas tentativas; encerrar com
  falha e notificação na terceira tentativa. O campo `scheduled_at` passa
  a indicar a próxima tentativa, não o agendamento original.
- Repetir automaticamente apenas falhas de conexão que comprovadamente
  ocorrem antes da aceitação pelo bridge (`ConnectError`, `ConnectTimeout` e
  `PoolTimeout`). Timeout de resposta, status HTTP e falha local após a
  resposta são ambíguos: a mensagem fica `failed`, conserva o `agent_run_id`
  conhecido e exige reconciliação antes de outra autorização.
- Reprocessar uma falha autorizada limpa o marcador de feedback da tentativa
  anterior. Assim, uma nova falha produz exatamente uma nova resposta ligada
  à mensagem original; um resultado ambíguo não pode ser reprocessado até a
  reconciliação do run conhecido.
- Isolar os testes de agendamento usando datas sintéticas anteriores às
  mensagens reais e substituir o disparo externo por simulação.

## Evidências de validação

Na validação geral anterior: frontend com 119 testes aprovados e build
concluído; backend com 536 aprovados e uma falha no teste de login, que
não fornecia reCAPTCHA. O teste foi ajustado com verificação simulada,
sem alterar a proteção de produção.

Na execução posterior: 18 testes de autenticação, contingência e backlog
aprovados; 3 testes do resolvedor aprovados; Ruff e `git diff --check`
sem erros. A regressão também verifica que uma segunda consulta antes
do prazo de retry não dispara novamente a mensagem.

Na rodada de recuperação final, as regressões de host-bridge (`8 passed`)
confirmaram a validação/resolução do executável. As regressões de rotas e do
scheduler cobrem propagação de diretório por Task e Workspace, configuração
ausente, retry limitado de conexão, timeout após possível aceitação, falha
depois da resposta do bridge e feedback após reprocessamento.

## Incidente durante os testes

Um teste preexistente consultava a fila real sem isolamento temporal.
Durante a validação ele alterou a tentativa de #23157 e disparou #23160.
O isolamento foi corrigido. #23160 foi observada como concluída; não deve
ser executada novamente. Isso não comprova a recuperação das demais.

## Pendente no ambiente ativo

- Integrar os arquivos revisados preservando as mudanças locais existentes.
- Atualizar o backend e reiniciar o bridge de forma controlada.
- Confirmar a resolução do Codex no ambiente do serviço.
- Consultar os estados atuais de #23157, #23158 e #23159 antes de recuperar
  as mensagens aprovadas; não alterar #22121, em decisão pendente.
- Confirmar execução e feedback, sem duplicar mensagens concluídas.

O serviço ativo aponta para `/root/project/forgehub/host-bridge`; apenas
alterar o worktree de correção não atualiza esse serviço.

## Fora desta alteração

Criação do vault e rotação coordenada de credenciais compartilhadas;
alterações Nexo; mudanças no cadastro canônico de clientes Darckware.
