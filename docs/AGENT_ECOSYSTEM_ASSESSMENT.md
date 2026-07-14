# Agent Ecosystem Assessment

## Estrutura recomendada

O ecossistema deve operar como uma empresa, com participação seletiva por projeto:

1. **Athos — Orquestrador:** recebe o objetivo, classifica a demanda, cria o plano, monta a equipe e controla gates e loops.
2. **Sete responsáveis Tier A:** Daedalus (engenharia), Atlas (demanda e decomposição), Mnemosyne (contexto e handoff), Scriba (documentação), Themis (privacidade e conformidade), Hephaestus (operações) e Aegis (segurança).
3. **Especialistas Tier B:** entram somente quando tipo, fase, risco ou tecnologia da tarefa exigir.
4. **SubAgents/workers:** executam um escopo estreito sob responsabilidade de um Agent.

## Avaliação de necessidade

| Agent/grupo | Necessidade | Regra de acionamento |
|---|---|---|
| Athos | permanente | todo Product/Project e toda mudança de escopo |
| Atlas | permanente no planejamento | discovery, backlog, dependências e formação da linha de produção |
| Daedalus | permanente na execução | implementação, correções, testes e handoff de engenharia |
| Mnemosyne | permanente em trabalhos longos | passagem entre fases/agentes, compactação e conflitos de contexto |
| Scriba | permanente nos gates documentais | APR/PRD/SPEC/ADR/runbook/release notes |
| Themis | condicional por risco, mas responsável permanente | dados pessoais, retenção, auditoria ou exigência regulatória |
| Hephaestus | permanente da integração ao deploy | CI/CD, infraestrutura, observabilidade, backup e rollback |
| Aegis | permanente nos gates de segurança | auth, secrets, dependências, hardening e incidentes |
| Architecture: Archimedes, Datalus, Hermes UX, Koios, Nomos | sob demanda | respectivamente arquitetura, dados, UX, RAG/IA e regras/estados complexos |
| Engineering: Forge | sob demanda | refatoração mecânica, scripts, manutenção e mudanças repetitivas |
| Operations: Hermod, Iris, Soteria, Talos | sob demanda | custo/modelos, feature flags, DR e automação operacional |
| Quality: Argus, Chronos, Oracle | por gate de qualidade | qualidade estática, regressão/performance e aceite/evidências |
| Integration Governance: Prometheus | sob demanda | plugin, MCP, skill ou integração de terceiros |
| AI Runtime: Mnemon | sob demanda | memória de sessão, recuperação, compressão e expiração |

## Sobreposições que precisam permanecer separadas

- **Athos × Atlas:** Athos decide e orquestra; Atlas decompõe demanda e dependências.
- **Mnemosyne × Mnemon:** Mnemosyne governa handoff/context pack; Mnemon implementa memória de runtime.
- **Daedalus × Forge:** Daedalus responde pela entrega; Forge executa trabalho mecânico delimitado.
- **Hephaestus × Talos:** Hephaestus responde pela operação; Talos automatiza workflows e evidências.
- **Argus × Chronos × Oracle:** revisão de qualidade, validação contínua e aceite final são gates diferentes.

## Regra função–skill

Todo Agent precisa possuir ao menos uma Skill versionada e aprovada que cubra sua função. A Task declara `required_skills`; o sistema só pode considerar elegível um Agent com grants compatíveis. Descrição, cargo, tier ou grupo não substituem Skill. Skills críticas ou de terceiros continuam sujeitas aos gates de governança e revisão de segurança.

Conclusão: os 23 Agents cadastrados são justificáveis, mas somente os oito Tier A formam a estrutura principal atual. Manter todos os 23 ativos em toda execução aumentaria custo, conflito e latência; os 15 Tier B devem ser convocados pelo pipeline conforme necessidade. Novas áreas, como Comercial e Redes Sociais, devem nascer como demandas/skills e setores sob demanda, sendo promovidas a departamentos Tier A apenas quando métricas de volume, risco e coordenação justificarem.
