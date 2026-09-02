# Messages e Telegram — operação e recuperação

**Estado:** implementado e verificado em 2026-08-23  
**Escopo:** ForgeHub Messages MCP, feedback de conclusão pelo Telegram e gateways Hermes por perfil

## Contrato de comunicação

O `forgehub-messages` é o canal canônico de comunicação entre agentes. Ele usa o mesmo domínio
`company.agent_demands`, a mesma tela Messages e o mesmo ciclo de dispatch do ForgeHub; não é uma
fila paralela.

Na tela de composição, `De (agente)` é obrigatório e define o agente remetente. `Para` aceita outro
agente ou pode permanecer em branco, caso em que o backend grava o próprio remetente como
`target_agent_id`. O tipo é obrigatório e possui somente duas opções:

- `Task`: trabalho executável; exige remetente e destinatário. Quando `Para` está vazio, o remetente
  executa a própria Task. Sem `scheduled_at`, o backend agenda a execução para o instante atual;
- `Incubation`: trabalho estacionado sob responsabilidade de um agente até ser promovido ou
  descartado. Não carrega vínculo de Task em `origin_id`.

Chamadores externos que enviem uma `Task` sem `target_agent_id`, mas com `from_agent_id` válido,
recebem a mesma semântica da tela: o destino passa a ser o próprio remetente. Uma Task sem remetente
continua inválida para execução e é reconciliada como incubação somente quando houver um agente dono.

Uma Task endereçada e pronta para execução não espera o próximo ciclo periódico. Depois que a
transação da mensagem é confirmada, o backend aciona um gatilho em memória que acorda imediatamente
o único worker de dispatch. O worker relê a Task do PostgreSQL e aplica os limites existentes
(concorrência global e no máximo um run por agente) antes de chamar o host bridge. O sweep de 30
segundos permanece apenas como contingência para escrita direta no banco, reinício do processo,
agendamento futuro ou eventual perda do sinal. Em produção, a validação `#17910` criou o agent run
em 124 ms após a criação da mensagem.

O retorno externo pelo Telegram é **opt-in pelo contexto textual da mensagem**:

- `channel="telegram"` ou `channel_ref` registram metadados de transporte, mas não autorizam o
  envio externo sozinhos;
- o assunto ou corpo precisa pedir explicitamente uma resposta, aviso ou retorno pelo Telegram;
- frases negativas, como “não responda no Telegram” ou “sem retorno pelo Telegram”, impedem o
  envio externo;
- todo resultado terminal continua gerando notificação no ForgeHub, mesmo quando o Telegram não
  foi solicitado.

Quando o retorno é solicitado, `channel_ref` aceita um `chat_id` concreto ou um alias do agente/bot
destinatário. Para Atlas, por exemplo, `Atlas`, `atlas`, `HermesAtlas2bot`,
`@HermesAtlas2bot` e o valor legado `telegram` resolvem para o `TELEGRAM_HOME_CHANNEL` do perfil.
O nome do bot nunca é enviado cru como `sendMessage.chat_id`.

## Configuração canônica do MCP

Cada perfil Hermes ativo deve declarar uma única entrada:

```yaml
mcp_servers:
  forgehub-messages:
    command: uv
    args:
      - run
      - /root/project/forgehub/host-bridge/forgehub_messages_mcp.py
    env:
      FORGEHUB_API_URL: http://localhost:8000
      FORGEHUB_ENV_FILE: /root/project/forgehub/.env
      FORGEHUB_AGENT_SLUG: <profile_slug>
```

`args` deve ser uma lista YAML, não uma string contendo JSON. O script PEP 723 fixa
`mcp[cli]>=1.2.0,<2`: a API FastMCP utilizada não existe no MCP 2.x.

Perfis sincronizados normalmente deixam `Agent.home_path` vazio. A leitura do Telegram deve usar
o caminho efetivo do runtime; para Hermes, o fallback é `/root/.hermes/profiles/<profile_slug>`.

## Credenciais de serviço dos agentes

O catálogo MCP unificado expõe `issue_agent_credential`, `list_agent_credentials` e
`revoke_agent_credential`. A emissão devolve um token com prefixo `agt_` uma única vez; o banco
persiste somente o SHA-256 do token. A listagem nunca recupera o segredo e mostra apenas metadados
ativos. A revogação preenche `revoked_at`, removendo imediatamente a credencial das listagens e da
autenticação válida. Expiração é opcional e armazenada com timezone.

Nunca copie um token emitido para documentação, logs, mensagens ou Foundation. Entregue-o somente
ao armazenamento protegido do runtime consumidor e revogue-o quando deixar de ser necessário.

## Portas dos gateways

Cada webhook habilitado possui uma porta exclusiva, conforme a Foundation:

| Perfil | Webhook | Bind |
|---|---:|---|
| Athos | 8647 | `0.0.0.0` |
| Atlas | 8648 | `0.0.0.0` |
| Mnemosyne | 8657 | `0.0.0.0` |
| Scriba | 8661 | `0.0.0.0` |
| Themis | 8662 | `0.0.0.0` |
| Aegis | 8663 | `0.0.0.0` |
| Daedalus | 8664 | `0.0.0.0` |
| Hephaestus | 8665 | `0.0.0.0` |

Kairos não possui webhook declarado. Nunca replique `8647` para todos os perfis: o resultado é uma
corrida de inicialização na qual um gateway ocupa a porta e os demais entram em reconexão contínua.

O API server do Hermes também exige uma porta exclusiva quando habilitado. Ele só deve ser ativado
se o perfil tiver um `API_SERVER_KEY` utilizável e deve permanecer em loopback:

| Perfil com chave | API server |
|---|---:|
| Athos | `127.0.0.1:8747` |
| Aegis | `127.0.0.1:8763` |
| Daedalus | `127.0.0.1:8764` |
| Hephaestus | `127.0.0.1:8765` |

Atlas, Kairos, Mnemosyne, Scriba e Themis não possuem atualmente `API_SERVER_KEY`; por isso o
`platforms.api_server.enabled` desses perfis fica explicitamente `false`. Não gere uma chave nova
durante recuperação sem também coordenar a rotação com todos os consumidores.

## Diagnóstico

1. Confirme os serviços:

   ```bash
   systemctl is-active hermes-gateway-{athos,atlas,mnemosyne,scriba,themis,aegis,daedalus,hephaestus,kairos}.service
   ```

2. Confirme listeners e proprietários:

   ```bash
   ss -ltnp
   ```

3. Procure erros recentes sem imprimir arquivos `.env`:

   ```bash
   journalctl -u hermes-gateway-atlas.service --since "15 min ago" --no-pager
   journalctl -u forgehub-chat-bridge.service --since "15 min ago" --no-pager
   ```

4. Um retorno Telegram bem-sucedido produz `POST /v1/messages/send ... 200 OK` no bridge. `502`
   com destino equivalente a `telegram:telegram` indica `channel_ref` não resolvido.

5. Uma demanda terminal com `feedback_sent_at IS NULL` ainda deve feedback. Linhas antigas com
   metadados Telegram, mas sem solicitação textual, devem ser concluídas apenas com notificação
   interna; não devem ser reenviadas indefinidamente.

## Recuperação e rollback

- Faça backup de cada `config.yaml` antes da edição e registre SHA-256.
- Valide o YAML antes de substituir o arquivo original.
- Pare todos os gateways afetados antes de trocar portas compartilhadas; depois inicie e valide
  todos, evitando outra corrida pela porta antiga.
- Mensagens técnicas de validação devem ser **arquivadas**, nunca excluídas.
- Não copie tokens, chaves, secrets de webhook ou conteúdo privado para logs ou documentação.
- Um teste externo real só deve ser executado quando o próprio contexto solicitar retorno pelo
  Telegram. Para validação sem envio externo, use testes unitários e inspeção de resolução.

Critério de conclusão: backend ForgeHub saudável, gateways ativos, listeners exclusivos, MCP vivo,
nenhum novo erro de bind/MCP/Telegram e nenhuma demanda terminal com feedback pendente.

## Implementação relacionada

- `backend/app/api/routes/demand.py` — resolução de aliases e home channel.
- `backend/app/core/agent_telegram.py` — caminho efetivo do perfil e leitura segura do `.env`.
- `backend/app/core/feedback.py` — opt-in textual e entrega terminal idempotente.
- `host-bridge/forgehub_messages_mcp.py` — ferramentas MCP e dependência compatível.

A política coletiva correspondente está em
`/root/.hermes/foundation/policies/hermes-gateway-operations.md`; o contrato coletivo de Messages
está em `/root/.hermes/foundation/docs/FORGEHUB_MCP_MESSAGES.md`.
