# Dossiê de validação — <missão>

**Estado:** rascunho · em revisão · aprovado
**Versão do dossiê:** <n> (cada retorno de `aguardando aceite` gera uma versão nova; as anteriores ficam guardadas)
**Gerado em:** <aaaa-mm-dd>

## 1. Identificação

| Campo | Valor |
|---|---|
| Missão | <nome e número> |
| Objetivo | <uma frase> |
| Período | <início> → <fim> (prazo previsto: <data>) |
| Linha(s) de serviço | <…> |
| Cliente | <nenhum (interna) / nome> |
| Patrocinador | Marcelo |
| Orquestrador | <agente> |
| Planejador | <agente> |
| Executores | <agentes> |
| Verificadores | <agentes> |
| Documentador | <agente> |
| Brief | `docs/missions/<slug>/BRIEF.md`, versão <n> e hash <…> |
| Critérios | versão e hash canônico <…> |
| Baseline | id <…>, versão e hash canônico <…>; ids/hash das tarefas incluídas |
| Aprovação da baseline | aprovador autenticado, data, evidência e escopo da aprovação |
| Autoridade | pessoa ou id de AuthorityDelegation, ação, projeto, risco/limites e validade; nunca token/segredo |
| Ambiente autorizado | ambiente por tarefa; destino de publicação quando aplicável |
| Projetos vinculados | ids, produtos/versões e escopo das tarefas consideradas no aceite |
| Independência | ids de executor(es), revisor(es) e terceiro da consolidação; autores/coautores não verificam a própria entrega |

## 2. Critérios de aceite × evidência

| Critério | Tarefas que o cumprem | Evidência | Verificado por | Quando | Estado |
|---|---|---|---|---|---|
| CA-1 <descrição verificável> | #… | <commit/PR/CI, execução remota, arquivo, registro> | <agente> | <data> | comprovado |

## 3. Entregas

| Tarefa | Executor | Verificador | Evidência | Documento |
|---|---|---|---|---|
| #… <título> | <agente> | <agente> | <…> | <arquivo> |

## 4. Documentos obrigatórios

| Documento | Versão aprovada | Aprovado por | Data |
|---|---|---|---|
| BRIEF.md | | Marcelo | |
| <escopo/PRD> | | Marcelo | |
| <plano> | | Marcelo | |
| <demais do pipeline> | | <verificador/documentador> | |

## 5. Críticas e correções

| Crítica | Sobre | Severidade | Esperado × entregue (resumo) | Correção | Resultado | Estado |
|---|---|---|---|---|---|---|
| C-1 | | | | tarefa #… | | aceita |

Críticas que bloqueiam o aceite ainda abertas: **<nenhuma / listar>**

## 6. Mudanças de escopo

| Change request | O que mudou | Aprovado por | Data |
|---|---|---|---|

## 7. Prazo e custo

| Item | Previsto | Realizado | Observação |
|---|---|---|---|
| Prazo | | | |
| Custo (ForgeRouter, horas) | | | runtimes externos: "não medido" quando for o caso |

## 8. Riscos e pendências remanescentes

| Item | Dono | Destino (outra missão, sustentação, descartado) |
|---|---|---|

## 9. Lições

- Funcionou: …
- Não funcionou: …
- Críticas repetidas (viram lição/proposta): …

## 10. Contexto e conformidade (I4/H3)

- Fontes canônicas e versões que entraram no brief: …
- Registro mínimo do contexto recebido por executor, com classificação/consumidores e sem segredos: …
- Teste de não vazamento e revisão independente: …
- Lições promovidas com aprovação e temporário limpo/arquivado conforme retenção: …
- Se houver dado pessoal: avaliação de impacto, base legal por categoria, critério LGPD e prova; se não houver, justificar não aplicável.
- Consolidação verificada por <agente que não é orquestrador, documentador nem autor>.

## 11. Checklist de aceite

- [ ] Baseline/brief/critérios/tarefas conferem com os ids/hashes aprovados
- [ ] Autoridade/delegação e ambiente ainda válidos; autorrevisão recusada
- [ ] Todos os critérios de aceite comprovados, com evidência citada
- [ ] Todos os documentos obrigatórios aprovados
- [ ] Nenhuma tarefa aberta (canceladas só com justificativa aprovada)
- [ ] Consolidação do orquestrador organizada pelo documentador e verificada por terceiro independente de ambos
- [ ] Aceite do cliente no portal por projeto executor vinculado quando houver entrega a cliente, mesmo que o coordenador seja interno
- [ ] Nenhuma crítica que bloqueie o aceite aberta
- [ ] Contexto mínimo, teste de não vazamento e conformidade aplicável comprovados
- [ ] Dossiê completo

**Decisão do Marcelo:** aceito · não aceito (críticas registradas: C-…)
**Data:** <aaaa-mm-dd>
