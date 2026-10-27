# Validação da consolidação — 27/10/2026

Escopo: revisão documental autorizada por Marcelo após a revisão de prontidão de 26/10; incorporar
correções e detalhar a Onda 1, sem executar/cadastrar suas tarefas nem alterar sistemas em produção.

## Correções rastreáveis

| Achado de 26/10 | Correção | Evidência documental |
|---|---|---|
| Identidade de executor/revisor duplicada | Aramis implementa, Porthus revisa; ids distintos, também em done/deployed | 04/07/12 e matriz |
| P.6 espera uma onda futura | G.11a mínima na Onda 2, G.11b completa na Onda 3 | 01/07/08 |
| V-a sem pré-requisito de isolamento | T.2+T.3 precedem roteiro mutante/browser | 01/07/10/12 e DAG |
| Primeira missão/ambiente contraditórios | C.0+C.1 real em produção após abertura; ensaios no teste; plano integrado projeto comum | 01/04/07/09/10 |
| Backup presumido como pronto | Prova por destino crítico e restauração; sem equivaler SQL local a offsite | 01/08/09/12 |

Também aplicados: fonte única de estados e modelo, legacy spec sinalizada, preservação de membros/
permissões/revisões, baseline ids/hash, DONE só relato, verificadores tipados, Q.0 e contrato MCP
antes do código; matriz de armazenamento separada da precedência. Migração do tipo missão explicitada
porque o modelo atual admite apenas creation/maintenance.

## Decisões

O 09 registra a aprovação recebida para consolidar e as premissas adotadas pelo redator. Não atribui
a Marcelo aceite individual que não ocorreu. Windows D-4 exige alvo/recursos antes da T.4b e não
bloqueia os testes Linux. Nenhuma compra, identidade, credencial, contato comercial ou delegação foi
criada. Os 27 ids da matriz são locais; nenhum é número de ProjectTask.

## Verificação automatizada

Executado `python3 scripts/validate-integrated-plan.py`: 27 itens, DAG sem ciclo, responsáveis/revisores distintos, pré-requisitos T.2+T.3, abertura antes de C.0 e guards antes do despacho, sincronização 07↔matriz, links relativos e estrutura das tabelas válidos. Não rodar pytest/build de aplicações para
alterações exclusivamente documentais.

## Revisão cruzada 0.14

Ainda não concluída nesta versão inicial. Serão registrados os pareceres reais de Porthus (técnico)
e Athos (governança), incluindo os modelos e a matriz detalhada. Uma proposta escrita ou uma chamada
de revisão enfileirada não conta como aprovação nem como implementação.
