# M0.1 — inventário da produção

Leitura em 03/11/2026, no banco `forgehub`, schema `company`, contêiner `forgehub_postgres`. Nenhuma escrita foi feita na produção. Os resultados são um retrato do momento e devem ser reconferidos antes do cadastro aprovado.

## Produtos e versões

`Cliente` indica se `darckware_client_id` está preenchido; não significa que um cliente foi criado.

| Produto | Versão | Status | Cliente |
|---|---|---|---|
| CoreTI | 1.0.0 | published | não |
| Darckware | 1.0.0 | published | não |
| Duplica | 1.0.0 | published | não |
| Factory E2E App 285afd61 | 1.0.0 | planned | não |
| ForgeHub | 1.0.0 | published | não |
| ForgeRouter | 1.0.0 | published | não |
| ForgeVault | 1.0.0 | published | não |
| Hindsight | 1.0.0 | published | não |
| Moodle Casa da Inovação | 1.0.0 | published | não |
| Projeto Teste Factory | 0.1.0 | planned | não |
| SAEDAS — Saúde nas Escolas | 1.0.0 | published | não |

## Projetos

| Projeto | Tipo | Produto | Versão | Owner |
|---|---|---|---|---|
| API Core Factory | creation | Projeto Teste Factory | 0.1.0 | — |
| Core Service 285afd61 | creation | Factory E2E App 285afd61 | 1.0.0 | — |
| CoreTI Platform | maintenance | CoreTI | 1.0.0 | maia |
| Darckware Platform | maintenance | Darckware | 1.0.0 | marcelo |
| Duplica Reprografia | maintenance | Duplica | 1.0.0 | marcelo |
| ForgeHub Control Plane | maintenance | ForgeHub | 1.0.0 | athos |
| ForgeRouter Gateway | maintenance | ForgeRouter | 1.0.0 | athos |
| ForgeVault Security | maintenance | ForgeVault | 1.0.0 | aegis |
| Hindsight Memory | maintenance | Hindsight | 1.0.0 | mnemosyne |
| Moodle Casa da Inovação | maintenance | Moodle Casa da Inovação | 1.0.0 | marcelo |
| Portal Web Factory | creation | Projeto Teste Factory | 0.1.0 | — |
| SAEDAS Platform | maintenance | SAEDAS — Saúde nas Escolas | 1.0.0 | athos |

As buscas em nomes de produtos e projetos por `ILIKE '%foundation%'` e `ILIKE '%plano%'` não retornaram linhas. Portanto não havia produto **Ecossistema Foundation**, projeto **Plano integrado**, nem nomes semelhantes por esses critérios.

A nota “Cadastro já existente” em [12-primeira-onda.md](12-primeira-onda.md) registra nove produtos cadastrados em 02/11 e mantidos por decisão de Marcelo em 03/11, cada um com versão `1.0.0` publicada e projeto de manutenção. Eles não foram alterados nem duplicados.

## Impedimento para o cadastro e roteiro de produção

A decisão exige owner Marcelo no produto e no projeto. O modelo `Product`, o esquema `ProductCreate`, a rota `POST /products` e a tabela de produção `company.products` não possuem campo de owner. O projeto possui `owner`. A API não consegue registrar nem conferir a titularidade exigida do produto; um campo extra no corpo não resolve isso. É necessário disponibilizar e testar essa capacidade antes do ensaio idempotente e do roteiro executável para aprovação. Não existe ainda comando seguro de cadastro nem IDs do ensaio a registrar aqui. A produção continua somente leitura.
