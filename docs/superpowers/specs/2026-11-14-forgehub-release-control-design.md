# Controle de releases do ForgeHub

**Aprovado por Marcelo em 14/11/2026.** Ordem solicitada: finalizar os ajustes
anteriores de acesso remoto/Messages e revisar Auditor antes de implementar esta tela.

## Intenção

Criar uma tela durável para entender como o ForgeHub evoluiu. O projeto está ficando
complexo; agentes e pessoas precisam saber o que mudou, por que mudou, quais áreas
foram afetadas e qual evidência sustenta cada item.

## Abordagens consideradas

1. **Usar Produtos > Releases** — reaproveita componentes/API existentes, mas os
   registros são obrigatoriamente vinculados a `ProductVersion`; mistura o ForgeHub
   com os produtos que ele gerencia. Descartada para este objetivo.
2. **Somente manter um CHANGELOG Markdown** — simples e útil para Git, porém sem
   consulta, filtros, estados ou edição estruturada na aplicação. Mantido como
   formato de documentação auxiliar, não como única interface.
3. **Cadastro próprio de releases em Controle do Sistema** — acrescenta persistência,
   API e tela para o próprio ForgeHub, com ligação às notas e fontes. Escolhida por
   atender à necessidade de contexto e histórico dentro do app.

## Escopo

- Adicionar `Releases` ao grupo existente **Controle do Sistema** na sidebar. O
  registro atual de Produtos permanece no domínio de produtos; Controle de Deploy
  permanece no acompanhamento de instalações/containers.
- Tela de listagem e detalhe com contexto da versão, estado, data/responsável,
  mudanças separadas em Correções, Modificações e Implementações, áreas afetadas e
  referências a Tasks, PRs, commits/tags e decisões.
- Persistir releases do próprio ForgeHub em entidade/endpoints próprios. Não adaptar
  o endpoint `/products/releases` para armazenar release do ForgeHub.
- Histórico em ordem cronológica, busca/filtro por versão, estado, categoria e área,
  estados de carregamento/vazio/erro e validação acessível dos formulários.
- SemVer para a versão; validar formato antes de salvar/publicar.
- Rascunho pode ser editado; publicação congela o snapshot das notas. Correção de
  release publicada exige nova versão SemVer; não há revisão in-place na v1.
- Publicar no controle significa publicar o registro de notas e versão. Não faz
  deploy, merge, push ou aprovação de produção.
- Permitir incluir `Nenhuma nesta versão` nas categorias vazias quando publicar.
- Campos de contexto são necessários: motivo/objetivo e áreas afetadas; itens de
  mudança incluem descrição e referências verificáveis.
- Cada mutação registra ator e timestamp em trilha auditável.

## Fora de escopo

- Deploy, rollback, aprovação de produção ou publicação automática de imagem.
- Inferir versões passadas a partir de `frontend/package.json` (hoje `0.1.0`) ou
  atribuir release histórica sem tag/evidência.
- Alterar o fluxo de ProductVersion/Release já existente.
- Gerar notas automaticamente por IA; a primeira entrega registra conteúdo revisado
  por pessoa.

## Decisões de implementação

- API e tabela próprias para ForgeHub releases, com version string única, estado,
  contexto, áreas afetadas, notas tipadas, referências, autor, timestamps e evidência
  de publicação.
- Todas as rotas da v1 exigem usuário administrador, alinhadas ao padrão atual das
  rotas `/api/v1/system-control`. Mudanças são auditadas no backend; a sidebar oculta
  a tela de acordo com a permissão `system_control`, mas não substitui a autorização
  do endpoint. Revisão futura pode separar leitura de escrita com decisão explícita.
- Snapshot publicado fica imutável; correção após publicação cria versão seguinte.
- Referências são registros tipados com título e URL/caminho verificável (`http(s)` ou
  rota interna do ForgeHub); a v1 não depende de foreign keys a tarefas/PRs. Commits e
  tags devem apontar para repositório e revisão identificáveis, nunca apenas texto
  descritivo.
- Tela seguirá o shell, tokens, componentes e padrões de tabelas/formulários já usados
  no ForgeHub. UI deve suportar viewport de 390px e 1440px.
- Deve haver teste de contrato para validação SemVer/transições, autorização por
  papel, snapshot imutável e ordenação/filtros; teste de interface para criar rascunho,
  publicar, estados vazio/erro e leitura no mobile.

## Critérios de aceite

1. `Controle do Sistema > Releases` mostra versões persistidas do ForgeHub sem misturar
   releases de produtos.
2. Usuário autorizado consegue criar rascunho com contexto e itens categorizados,
   revisar e publicar; usuário sem permissão recebe recusa do backend.
3. Release publicada mostra versão, data, contexto, áreas, categorias e fontes, sem
   permitir edição destrutiva do snapshot.
4. Rascunhos, publicados e versões sem itens possuem estados visuais explicativos;
   falhas de rede e validação mantêm o conteúdo digitado e explicam como corrigir.
5. CHANGELOG e regra DEL-017 apontam para a tela e descrevem o limite entre registro
   de release e deploy.

## Pontos deixados ao implementador

- Escolher a estrutura relacional normalizada ou JSON validado para notas/referências,
  mantendo integridade, ordenação e migração reversível conforme padrões do repo.
- Preferir os componentes mantidos existentes para combobox, diálogo, toast e
  formulário; sem dependência nova sem necessidade demonstrada.
- A versão inicial da tela começa vazia, sem criar uma release fictícia.
