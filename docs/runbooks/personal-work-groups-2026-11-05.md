# Tarefas dos agentes: grupos e diagnóstico de aprovação Moodle

## Resultado da investigação

Consultas somente de leitura em 05/11/2026 mostraram:

| Registros | Autorização Moodle | Resultado registrado |
|---|---|---|
| #42087–#42089 | Mesmo instante de autorização, lote | Três operações `finished/completed` |
| #42090–#42091 | Mesmo instante de autorização, lote | Duas operações `finished/completed` |
| #42028 e #42029 | Autorização registrada, sem claim confirmado | Execução bloqueada e arquivada; resposta da Maia interpretou `pending` local como ausência de aprovação |
| #42095 | `finished/completed` | Acompanhamento `failed` porque o relatório final não seguiu o formato exigido |

As propostas locais dos lotes concluídos também permaneciam `pending`. Logo esse estado não determina autorização ou conclusão de uma operação via Messages. Nos dois registros bloqueados havia tentativas locais anteriores à autorização: 10:16:48Z e 10:17:53Z, enquanto as autorizações foram registradas perto de 12:39Z. O erro histórico “Claim já tentado” aparece nas respostas; esse bloqueio local não está mais no código atual consultado. Não foi comprovada perda de autorização pelo endpoint de lote atual.

Nenhuma proposta foi reaprovada, nenhum claim foi consumido e nenhuma operação Moodle foi repetida durante o diagnóstico ou os testes desta demanda. Não se verificou o estado administrativo atual dos alunos no Moodle; `completed` aqui descreve o protocolo e os retornos registrados, não uma nova auditoria do cadastro.

## Entrega preparada

- Aprovações Moodle em subaba própria, sem aprovação genérica da mesma mensagem.
- Incubações com Transformar em tarefa, Adiar e Descartar; promoção mantém a identidade do registro.
- Tarefas com ação visível de arquivar, lote de selecionadas e restauração sem executar.
- Contagens e paginação por classificação persistida, compatibilidade com o endpoint legado sem filtro de grupo.
- Perguntas e revisões de conclusão identificadas separadamente, sem zero falso quando a fonte falha.
- Histórico recente da operação Moodle separado de falhas de acompanhamento.
- Propostas indisponíveis não mascaradas como ausência de pendências.
- MCP: consulta `moodle_get_approval_status` para ler o estado oficial sem claim nem escrita; propostas locais identificam explicitamente a fonte local e o fluxo Messages.

## Validação

- Backend: 40 testes nos domínios de gestão/decisão e aprovação Moodle, em PostgreSQL de testes protegido pelo guard do projeto. Inclui lote com item alterado recusado integralmente, aprovação válida de dois itens e recusa de reenvio do lote.
- Frontend: suíte completa com 460 testes; regressões focadas de navegação, aprovação em lote, promoção, erros de fonte e arquivamento com seleção também executadas.
- MCP: 148 testes aprovados, zero falhas, um teste condicionado a harness externo ignorado; transporte HTTP/stdio incluído.
- Build frontend concluído. Inspeção Chrome com dados fictícios locais: grupos, arquivamento confirmado, fila vazia após arquivar, resultado Moodle separado do relatório e viewport de 390 px sem overflow da página.
- Auditoria estática premium: 51 ocorrências, as mesmas 51 do checkout base; nenhuma ocorrência nova. O passivo anterior permanece fora deste escopo.
- Revisão independente encontrou link de promoção preso à fila e contagens zero em erro; ambos corrigidos com reprodução e regressão. Metadados da consulta MCP foram corrigidos para anunciar leitura.

## Publicação e passivo

Implementação preparada nas branches `feat/personal-work-groups` (ForgeHub) e `fix/authoritative-approval-status` (Moodle). Publicação e sincronização da skill instalada não foram executadas. Implantar backend compatível antes do frontend. A nova ferramenta exige atualização do MCP e skill canônica; ativação do perfil deve seguir o procedimento operacional do Hermes, sem reinício implícito do gateway compartilhado.

As tarefas antigas continuam intactas: o conjunto autorizado para arquivamento ainda precisa ser identificado. Arquivar uma tarefa não responde nem cancela uma pergunta bloqueante. Evitar reativar propostas antigas ou corrigir estados por SQL; consultar evidências e estado Moodle antes de qualquer novo pedido autorizado.

## Atualização: publicação autorizada e concluída em 05/11/2026

Marcelo autorizou deploy, commit e push após revisar a entrega. A seção anterior registra o estado antes dessa autorização.

- ForgeHub: implementação `4f32e20` integrada por fast-forward em `develop` e enviada ao GitHub. Deploy pelo `scripts/deploy.sh`, com metadados de versão/commit e recriação dos containers backend/frontend. Backend saudável, `/health` HTTP 200 e frontend HTTP 200; o backend informa commit `4f32e20`.
- Moodle: correção integrada às alterações posteriores sem removê-las, commit `164e001` em `main`, enviado ao GitHub. A suíte da versão combinada teve 151 aprovações, nenhuma falha e um teste condicionado a harness ignorado.
- Maia: backup em `/root/backups/moodle/approval-status-164e001/`; skill técnica sincronizada com a fonte canônica. Somente o MCP Moodle da Maia foi temporariamente desabilitado e reabilitado pelo reconciliador nativo, com aceitação no config guard e invalidação apenas do cache de schemas Moodle desse perfil. Logs confirmam remoção e reconexão; catálogo atualizado com 40 ferramentas, incluindo `moodle_get_approval_status`.
- A configuração final da Maia é idêntica ao backup original. O gateway manteve PID `2930096`, estado `running`, e Telegram/WhatsApp da Maia conectados. Nenhum reinício compartilhado foi executado.
- Validação pós-deploy somente de leitura: tarefas e incubações consultadas pelo código publicado, com 14 e 4 itens precisando de atenção respectivamente no instante da consulta. Arquivos efetivamente servidos pelo frontend contêm os três grupos, promoção e arquivamento. Essas contagens são um retrato do momento e podem mudar.
- Imagens anteriores preservadas como `forgehub-backend:rollback-personal-groups-20261105` e `forgehub-frontend:rollback-personal-groups-20261105`; IDs registrados em `/root/backups/forgehub/personal-groups-20261105/images.json`.
- Alterações locais de outro trabalho em `ops/` e seu runbook foram preservadas e não incluídas nos commits desta entrega. Nenhuma operação Moodle foi repetida e nenhum registro antigo foi arquivado neste deploy.
