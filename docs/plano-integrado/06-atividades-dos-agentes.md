# Atividades dos Agentes


Hoje: estado ao vivo dos agentes Hermes pela telemetria, agentes externos só enquanto há um despacho
rodando, alertas, timeline e replay. Rotinas e cartas ficam só em `/operations`.

Alvo:
1. **Todos os agentes sempre no quadro**, os 13 das cartas, Hermes e externos. Um externo parado
   aparece "ocioso", nunca some. Para cada agente:
   - estado (executando, pensando, aguardando, ocioso, degradado);
   - canal Telegram e gateway;
   - próxima rotina e última execução;
   - fila no Messages;
   - orçamento do dia usado (execuções e custo).
2. **Rotinas na timeline:** cada ocorrência é um bloco na faixa do agente, com cor por desfecho
   (agendada, rodando, concluída, falhou, perdida, pulada por orçamento). Uma ocorrência perdida gera
   alerta. A grade mostra também as próximas 24 h.
3. **Ligação com o trabalho:** cada execução mostra a origem (rotina, ProjectTask com projeto e fase,
   missão, ticket, execução remota) e leva até ela com um clique.
4. **Saúde por agente:** taxa de `DONE` na primeira tentativa (7 dias), falhas, reprocessos, rotinas
   perdidas e dúvidas sem resposta. É o que a Evolução já mede, agora visível por agente.
5. **Alertas novos:** rotina perdida, agente sem rotina ligada há mais de N dias quando a carta prevê
   rotina, tarefa de projeto parada além do prazo, execução remota com falha.

Princípio mantido: o ForgeHub não lê o banco de nenhum runtime. Tudo vem do que já é dele (Messages,
rotinas, cartas, execuções remotas) e da telemetria que os runtimes enviam.

---
[← Índice](README.md)
