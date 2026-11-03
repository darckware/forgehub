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

## Lacuna de modelo

produto sem campo de dono no modelo; tratar em B.1/Fase S (products.owner). Por decisão de Porthus em 03/11, o dono consta na descrição do produto e no campo `owner` do projeto.

## Ensaio no ambiente de teste

Em 03/11/2026, API `http://127.0.0.1:8002`: produto `4afaa63f-f272-453e-ae5e-f7d954b9e0da`, versão `070b3387-995f-432b-a239-5399e75d05d4`, projeto `2a28d318-e9b7-4aa3-b912-61c0f45793b5`. Primeira execução criou os três; segunda reutilizou os mesmos IDs. A API confirmou um de cada e o projeto vinculado à versão.

## Roteiro de produção — aguardar aprovação de Marcelo

Executar a partir da raiz do repositório, somente após aprovação. Verificar novamente o inventário e que não existem nomes iguais ou incompatíveis. Usar a URL real da API de produção em `FORGEHUB_URL`, sem barra final; não guardar o token em arquivo, histórico, mensagem ou comando. O script exige Python com `httpx` (por exemplo, `backend/.venv/bin/python`).

1. Autenticação: (a) Marcelo entra na tela e copia o token da sessão para a variável `FORGEHUB_TOKEN` de forma privada no shell; a aplicação guarda o token em `localStorage` sob `forgehub-auth`, em `state.token`. Ou (b) Marcelo cria os três registros pela tela com os valores abaixo e, autenticado da mesma forma, usa o script para conferência. Não executar o comando real na opção (b) se o dry-run indicar qualquer `created`.
2. Primeiro, simular sem escrever:

   ```bash
   backend/.venv/bin/python scripts/register_foundation_product.py --base-url "$FORGEHUB_URL" --token-env FORGEHUB_TOKEN --dry-run
   ```

3. Se a simulação e a aprovação estiverem corretas, executar:

   ```bash
   backend/.venv/bin/python scripts/register_foundation_product.py --base-url "$FORGEHUB_URL" --token-env FORGEHUB_TOKEN
   ```

4. Conferir na tela ou API uma ocorrência de cada, IDs e vínculos: produto **Ecossistema Foundation**, sem cliente, descrição `Foundation, agentes Hermes e infraestrutura comum do ecossistema; casa da missão e do plano integrado. Dono: Marcelo.`; versão `2026.11` em `planned`; projeto comum **Plano integrado**, tipo `creation`, owner `Marcelo`, sem cliente, vinculado à versão e com descrição `Projeto comum do Plano Integrado do ecossistema (docs/plano-integrado)`. `solution_type` é opcional e fica vazio. Na opção (b), exigir `reused` nos três; repetir o comando e confirmar os mesmos IDs. Registrar os IDs reais e o ambiente após o cadastro.
5. Rollback, enquanto ainda não houver tarefas: excluir primeiro o projeto e depois o produto pela tela. Não executar automaticamente. Ao terminar, remover a variável de token da sessão com `unset FORGEHUB_TOKEN`.
