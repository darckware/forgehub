# Controle de releases do ForgeHub

Este diretório registra a evolução do próprio ForgeHub. Ele é separado de
`Produtos > Releases`, que registra releases de produtos gerenciados, e de
`Controle de Deploy`, que acompanha instalações e containers.

## Estado

**Contrato documental em preparação; não representa uma tela/API já implementada.**
O controle proposto fica em `Controle do Sistema > Releases`, usa armazenamento
próprio e não dispara deploy. A página deve explicar cada versão com contexto, áreas
afetadas e referências verificáveis.

## Política de versão

- Use SemVer `MAJOR.MINOR.PATCH` para versões estáveis do ForgeHub.
- `MAJOR`: incompatibilidade de API, dados ou operação para consumidores existentes.
- `MINOR`: funcionalidade compatível nova.
- `PATCH`: correção compatível.
- Pré-lançamentos podem usar sufixo SemVer, como `-rc.1`; metadados de build não
  substituem a versão estável.
- Não invente nem retroatribua versão a publicação histórica sem tag/evidência. A
  primeira versão cadastrada deve refletir evidência real; até lá, mudanças ficam em
  **Não publicado**.
- Uma release publicada registra um snapshot das notas, responsável, data e fontes.
  Correção de release publicada exige nova versão SemVer; o histórico anterior não é
  editado nem apagado.
- Publicar notas é registro de versão; não executa deploy, merge, push ou aprovação de
  produção.

## Categorias obrigatórias das notas

- **Correções** — defeitos resolvidos, causa observável e comportamento corrigido.
- **Modificações** — mudança em fluxo, regra, interface, integração ou operação que
  já existia.
- **Implementações** — capacidade nova que passou a existir.

Para cada item registre: contexto/motivo, descrição do resultado, áreas afetadas e
referências (Task/issue, PR, commit ou decisão). Se uma categoria não tiver itens,
registre `Nenhuma nesta versão` no fechamento, evitando que vazio seja confundido
com esquecimento.

## Fluxo de atualização

1. Durante o desenvolvimento, acrescente cada mudança em `CHANGELOG.md` sob
   **Não publicado**, incluindo contexto e links verificáveis.
2. Não misture trabalho não integrado, proposta, experimento ou rollback com mudança
   já entregue; identifique explicitamente o estado.
3. Antes de publicar, escolha a próxima versão SemVer com base no impacto, confirme
   mudanças e referências, preencha as três categorias e registre a data real.
4. A tela permite revisar o rascunho e publicar o registro. Isso não substitui os
   gates de deploy, aprovação ou release operacional.
5. Após publicação, preserve snapshot e auditoria. Ajustes posteriores entram como
   nova versão de correção.
6. Atualize este changelog junto com a mudança de comportamento e vincule tarefas,
   commits e decisão para manter a contextualização do projeto.

## Arquivos

- [`CHANGELOG.md`](CHANGELOG.md) — histórico humano de versões e mudanças.
- [`../superpowers/specs/2026-11-14-forgehub-release-control-design.md`](../superpowers/specs/2026-11-14-forgehub-release-control-design.md)
  — escopo funcional da tela e do backend propostos.
- [`../business_rules/README.md`](../business_rules/README.md) — catálogo de regras
  atuais e lacunas do ForgeHub.
