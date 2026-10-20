# Organograma Empresarial de Agentes

## Modelo organizacional

```text
ForgeHub Development Organization
└── Athos — Executive Orchestration
    ├── Atlas — Product & Planning
    │   └── Nomos — Business Rules & State Design
    ├── Daedalus — Engineering
    │   ├── Archimedes — Architecture & Integration Design
    │   ├── Datalus — Data Engineering
    │   ├── Hermes UX — Product Design & UX
    │   ├── Koios — AI & Retrieval Engineering
    │   └── Forge — Implementation & Maintenance
    ├── Mnemosyne — Knowledge & Context
    │   └── Mnemon — Runtime Memory
    ├── Scriba — Documentation
    ├── Themis — Governance & Compliance
    │   └── Prometheus — Integration Governance
    ├── Hephaestus — Platform & Operations
    │   ├── Hermod — FinOps & Model Operations
    │   ├── Iris — Release & Feature Management
    │   ├── Soteria — Reliability & Disaster Recovery
    │   └── Talos — Workflow Automation
    └── Aegis — Security & Assurance
        ├── Argus — Code Quality
        ├── Chronos — Regression & Performance
        └── Oracle — Acceptance & Evidence
```

Os oito Agents Tier A são a estrutura principal atual: Athos e sete responsáveis departamentais. Isso é uma baseline, não um teto. Agents Tier B ocupam setores especialistas. Os `SubAgent` cadastrados sob cada Agent são workers internos e não alteram o organograma de responsabilidade.

## Responsabilidade por departamento

| Departamento | Responsável | Entrega e autoridade |
|---|---|---|
| Executive Orchestration | Athos | portfólio, priorização, composição da equipe, classificação ForgeRouter, gates e decisão de escalonamento |
| Product & Planning | Atlas | discovery, requisitos, backlog, decomposição, dependências e planejamento da linha de produção |
| Engineering | Daedalus | arquitetura executável, design técnico, implementação, integração e testes de engenharia |
| Knowledge & Context | Mnemosyne | pacotes de contexto, handoffs, memória governada e resolução de conflito de contexto |
| Documentation | Scriba | APR, PRD, SPEC, ADR, runbooks, índices e notas de release |
| Governance & Compliance | Themis | privacidade, retenção, auditoria, políticas e risco de integrações externas |
| Platform & Operations | Hephaestus | CI/CD, ambientes, deploy, observabilidade, custos, flags, backup e rollback |
| Security & Assurance | Aegis | segurança, qualidade independente, regressão e aceite baseado em evidências |

## Grupos, funções e skills

- Departamento define responsabilidade empresarial.
- Setor define especialidade operacional.
- Agent define o responsável auditável.
- SubAgent define um worker limitado.
- Skill define o que o executor está autorizado e preparado para fazer.
- RuntimeProfile define CLI e classe ForgeRouter.
- ProjectMembership autoriza participação no projeto.
- TaskAssignment define responsabilidade concreta.

Uma função só está operacionalmente completa quando possui pelo menos uma Skill versionada e aprovada. O organograma sinaliza ausência de cobertura. Tasks devem declarar skills requeridas; descrição, departamento ou tier não concedem capacidade automaticamente.

## Regras de funcionamento

1. Athos nunca substitui o responsável departamental na execução; coordena e cobra evidência.
2. Um projeto não recebe todos os Agents automaticamente. Athos monta a equipe mínima conforme pipeline, riscos e tipo de desenvolvimento.
3. Todo Planning Item possui um departamento responsável; Tasks podem envolver setores diferentes.
4. Produção e revisão usam Agents distintos quando o gate exigir independência.
5. Cada execução usa a API key ForgeRouter do Agent executor.
6. Tier B é convocado por necessidade; ausência de convocação não remove sua responsabilidade técnica quando o setor é exigido.
7. SubAgent não aprova acima da autoridade de seu Agent responsável.
8. Athos é o operador padrão do ForgeHub: conduz planejamento e libera execução somente dentro da delegação do usuário e das Policies vigentes.
9. Athos não assume automaticamente a implementação atribuída a outro Agent e não aprova o próprio trabalho.

## Críticas e melhorias aplicadas

### Problemas anteriores

- `layer` era usado simultaneamente como tecnologia, grupo e hierarquia. Isso tornava impossível saber quem respondia por quem.
- Os 23 Agents apareciam no mesmo nível, escondendo a estrutura real de oito responsáveis principais.
- Função era texto livre sem visibilidade da cobertura por Skills.
- A key ForgeRouter era configurada por projeto, reduzindo identidade, cota e auditoria individual.
- Qualidade aparecia como grupo técnico sem um responsável Tier A explícito.

### Decisões adotadas

- `department`, `sector` e `reports_to_profile_slug` agora representam a estrutura empresarial separadamente de `layer`.
- Athos é a raiz; os sete demais Tier A lideram departamentos; Tier B ocupa setores.
- Qualidade foi colocada em Security & Assurance, sob Aegis, para manter independência da produção de Daedalus. É uma escolha pragmática; se o volume crescer, recomenda-se criar uma liderança Tier A própria para Quality Engineering.
- Skills aprovadas são exibidas por Agent e agentes sem cobertura são sinalizados.
- Credenciais ForgeRouter são individuais, criptografadas e write-only.

## Pontos que ainda exigem governança

1. A estrutura organizacional deve virar documento canônico no Hermes Foundation; o ForgeHub atualmente mantém a projeção operacional sincronizada por `profile_slug`.
2. Mudança de departamento, setor ou reporte deve passar por revisão de Athos e atualização do documento canônico.
3. Deve ser definida uma matriz mínima de Skills por função, incluindo versões e riscos esperados.
4. O sistema deve impedir futuramente membership ativa de Agent principal sem key e sem Skill aprovada.
5. Métricas devem medir fila, custo, retrabalho e taxa de aprovação por departamento/setor antes de criar novos Agents.

## Crescimento futuro: Growth & Market

Comercial e Redes Sociais são necessidades legítimas, mas não devem entrar imediatamente no pipeline técnico de todos os projetos. A evolução recomendada é gradual:

### Estágio 0 — responsabilidade coordenada

Athos registra demandas comerciais e de comunicação como Planning Items próprios, ligados ao Product. A execução pode continuar humana, com templates e policies, sem criar Agents permanentes.

### Estágio 1 — setores especialistas Tier B

Quando houver demanda recorrente, criar o departamento virtual **Growth & Market** com setores:

- Commercial Strategy & Sales: proposta de valor, qualificação, ofertas, CRM e feedback do mercado;
- Social Media & Content Distribution: calendário editorial, adaptação por canal, publicação e métricas;
- Brand & Product Marketing: posicionamento, campanhas, lançamentos e consistência de marca;
- Customer Success & Partnerships: onboarding, retenção, suporte estratégico e parcerias.

Esses Agents devem usar artifacts próprios — market brief, campaign plan, content package, sales proposal e performance report — sem editar diretamente PRD/SPEC aprovados. Feedback de mercado retorna ao Product por Demand/Change Request.

### Estágio 2 — liderança Tier A

Promover um responsável de Growth & Market a Tier A somente quando pelo menos dois sinais persistirem: fila recorrente, múltiplos canais/produtos, necessidade de aprovação de marca, volume comercial mensurável, conflitos de prioridade ou risco reputacional. Nesse momento, a baseline passa naturalmente de 7 para 8 responsáveis departamentais, sem alterar o papel de Athos.

### Controles necessários

- Social Media sempre exige aprovação humana antes de publicação externa.
- Comercial não promete prazo, feature ou preço sem consultar Product/Planning e Governance.
- Conteúdo não expõe segredo, dado pessoal ou informação de projeto não liberada.
- Métricas de crescimento não substituem critérios de qualidade do produto.
- Agents de Growth usam skills específicas e keys individuais, seguindo o mesmo modelo de governança dos Agents técnicos.
