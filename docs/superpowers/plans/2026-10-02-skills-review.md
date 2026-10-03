# Revisão de skills dos agentes Hermes — Proposta para aprovação

**Data:** 2026-10-02
**Fonte:** telemetria do curator do Hermes (`hermes -p <perfil> curator usage --json`), 10 perfis ativos (prometheus está estacionado e fica fora).
**Pedido (Marcelo):** "analisar cada agente e criar e adicionar skills para cada um, de acordo com suas funções. Atualizar e rever todas as skills e remover as sem uso e obsoletas."

## Diagnóstico

| Perfil | Ativas | Usadas | Criadas por agente e sem uso | Bundled sem uso |
|---|---|---|---|---|
| athos | 77 | 32 | 20 (+7 paradas há mais de 60 dias) | 16 |
| aegis | 47 | 3 | 18 | 17 |
| atlas | 83 | 2 | 15 | 57 |
| daedalus | 42 | 1 | 15 | 17 |
| hephaestus | 84 | 1 | 17 | 57 |
| kairos | 35 | 7 | 14 | 0 |
| lara | 30 | 0 | 16 | 0 |
| mnemosyne | 83 | 1 | 16 | 57 |
| scriba | 82 | 3 | 15 | 55 |
| themis | 83 | 1 | 16 | 57 |

- Só o Athos usa skills de forma consistente. Os outros têm dezenas de skills genéricas (Apple, games, música, vídeo, Minecraft, Pokémon) sem relação com a função, e quase nenhuma skill da própria função.
- **Risco:** `godmode` (jailbreak de LLM) e `obliteratus` (remove as recusas de segurança de modelos) estão em 9 perfis, sem uso.
- Skills de fluxo de código (`github-*`, `github-issue-to-pr`, `plan`, `writing-plans`, `subagent-driven-development`) contrariam a regra nova: agentes Hermes não codificam.
- `kanban-codex-lane` é obsoleta (Kanboard descontinuado em 2026-07-28).

## Como será feito

- **Arquivar** (`hermes -p <perfil> curator archive <skill>`): move para `.archive/`, recuperável com `curator restore`. Nada é apagado.
- **Desligar bundled** (`hermes -p <perfil> skills opt-out <skill>`): as genéricas do Hermes deixam de carregar naquele perfil e voltam com `opt-in`.
- **Snapshot antes** de cada perfil, em `athos/state-snapshots/skills-review-2026-10-02/`, com README.
- **Fixar** (`curator pin`) as skills novas da função, para o curator não as transformar sozinho.
- Lara: só arquivamento das skills de código e de pesquisa sem uso. A configuração de atendimento dela não é tocada.

## A. Arquivar em todos os perfis onde existirem (sem uso, obsoletas ou de risco)

`godmode`, `obliteratus`, `kanban-codex-lane`, `spotify`, `linear`, `merge-reconciler`, `collective-wisdom-install`, `session-librarian`, `hermes-s6-container-supervision`, `debugging-hermes-tui-commands`, `webhook-subscriptions`, `github-issue-to-pr`, `github-auth`, `github-code-review`, `github-issues`, `github-pr-workflow`, `github-repo-management`, `github-push`, `plan`, `writing-plans`, `subagent-driven-development`, `research-paper-writing`, `nano-pdf`.

Exceções: no **athos**, `writing-plans` e `subagent-driven-development` têm uso antigo (3 e 2), mas também são fluxo de código, então arquivam igual. O `native-mcp` é **mantido** onde foi usado (aegis, athos, atlas, daedalus, scriba).

## B. Arquivar por perfil (criadas por agente, sem uso)

| Perfil | Skills |
|---|---|
| athos | `aegis-security-report-short`, `agy`, `condex`, `hephaestus-observability-minimum`, `skill-spec-template-ptbr`, `hermes-config-repair` (duplicada pela skill `hermes-ecosystem-repair` do operador; manter só no hephaestus) |
| aegis | `Linux Server Analysis` e `SSH Connection` **mantidas** (úteis à varredura de segurança) |
| hephaestus | `hermes-config-repair` **mantida** (é a gêmea Hermes da skill do operador) |
| lara | `prompt-injection-defense` e `security-operational` **mantidas** (proteção de um agente que conversa com o público); `blogwatcher`, `ocr-and-documents` arquivadas |
| kairos | `blogwatcher` **mantida** (monitoramento de mercado); `ocr-and-documents` arquivada |

## C. Desligar bundled fora da função

**Em todos os perfis:** `apple-notes`, `apple-reminders`, `findmy`, `imessage`, `songsee`, `songwriting-and-ai-music`, `manim-video`, `ascii-video`, `p5js`, `gif-search`, `youtube-content`, `baoyu-infographic`, `popular-web-designs`, `product-price-monitor`, `airtable`, `box`, `notion`, `teams-meeting-pipeline`, `opencode`, `codex`, `claude-code`, `inspecting-hermes-desktop-dom`, `node-inspect-debugger`, `python-debugpy`, `dogfood`, `spike`, `test-driven-development`, `simplify-code`, `requesting-code-review`, `codebase-inspection`. Hub: `minecraft-modpack-server`, `pokemon-player`, `pixel-art`, `baoyu-comic`, `baoyu-article-illustrator`, `dspy`.

**Mantidas** onde fazem sentido: `hermes-agent`, `hermes-agent-skill-authoring`, `systematic-debugging` (diagnóstico, não código), `grounded-citations`, `pdf`, `docx`, `xlsx`, `powerpoint`, `google-workspace`, `email-inbox-triage`, `meeting-action-items`, `document-to-action-items`, `weekly-review-planning`, `architecture-diagram`, `design-md`, `llm-wiki`, `obsidian`, `maps`, `arxiv`, `competitor-news-monitor` (kairos), `humanizer` (kairos, lara), `rss-feeds` e `reddit-reading` (kairos), `ideation` (kairos, athos), `sdlc-review` (daedalus).

## D. Criar: skills da função (fixadas)

Cada skill nova segue o formato SKILL.md do Hermes, usa as ferramentas MCP do `forgehub` e termina com evidência e, quando couber, um item de Incubação.

| Agente | Skills novas |
|---|---|
| **Todos** | `forgehub-routine-execution`: como executar uma rotina (ler a carta, evidência, Incubação para melhoria, perguntar ao Marcelo, regra de código) |
| athos | `ops-morning-briefing`, `ops-routine-triage`, `ops-retrospective` (propostas A0/A1/A2 com métrica-alvo e reversão) |
| hephaestus | `infra-health-sweep` (containers, restart policy, disco, cache Docker, systemd), `offsite-backup-verification` (restic: snapshot, idade, check, restauração de amostra) |
| aegis | `security-daily-sweep` (allow-list de portas, permissões de segredos, credenciais só locais no ForgeVault, SSH/logins), `incident-triage` |
| atlas | `planning-hygiene` (tarefas paradas, dependências bloqueadas, itens sem dono via MCP `forgehub`) |
| daedalus | `repo-hygiene-diagnosis`, `code-task-specification` (Task para Aramis/Dartan/Porthus com critério de aceite e evidência) |
| mnemosyne | `hindsight-quality-review` |
| scriba | `docs-drift-check` (commits do dia × CLAUDE.md/Foundation/KB) |
| themis | `lgpd-data-review`, `dependency-license-check` |
| kairos | `market-intelligence-digest` |
| lara | `internal-pipeline-review` (sem contato com clientes) |

## Resultado esperado

Cada perfil fica com algo entre 15 e 30 skills, todas ligadas à função. O que sai pode ser restaurado com um comando, e o que entra fica fixado. Uma semana depois, a retrospectiva do Athos compara o uso das skills novas com o que existia antes.
