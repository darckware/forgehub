# Histórico de versões do ForgeHub

Este arquivo registra o **próprio ForgeHub**. Cada item deve explicar contexto e
impacto e apontar evidências. O registro não declara que uma versão foi implantada;
para isso, consulte a evidência operacional de deploy.

## Não publicado

### Correções

- **Messages — preparada, aguardando integração/publicação.** A criação de diagnóstico
  arquivava automaticamente a tarefa original que falhou. O commit `3d88492`, branch
  `fix/messages-failure-preservation`, preserva falha, causa, run e evidências e mantém
  um único diagnóstico vinculado. Revisão independente sem achados; homologação do
  supervisor: 61 testes aprovados no banco isolado. Essa correção ainda não está
  integrada ao commit-base deste catálogo nem publicada em produção.
- **Acesso remoto e Auditor — preparados, aguardando integração/publicação.** O commit
  `5426991`, branch `feat/remote-session-exception-enforcement`, fecha revalidação de
  credenciais/grants, escopo da Task, ordem de locks e rastreio da autorização no
  backend colaborativo. Auditor passou a conferir integridade histórica dos vínculos
  e evidência real das rotinas. Dois HIGH encontrados em revisões independentes foram
  corrigidos e revistos; supervisor: 275 testes backend/SQL e 171 testes de operações
  aprovados, 19 testes da proteção de banco aprovados. API colaborativa permanece
  desligada; esse código não é requisito da exceção direta já publicada na Foundation.

### Modificações

- **Contexto:** agentes precisavam distinguir comportamento vigente, lacunas e planos
  antes de alterar o ForgeHub. **Mudança:** criado catálogo de regras de negócio com
  fontes e níveis de implementação. [Catálogo](../business_rules/README.md).
- **Contexto:** a documentação anterior não tinha um histórico central de releases do
  próprio ForgeHub. **Mudança:** registrada a política SemVer e o desenho da tela; a
  tela/API ainda não está implementada. [Proposta](../superpowers/specs/2026-11-14-forgehub-release-control-design.md).

### Implementações

- Nenhuma registrada.

## Releases publicadas

> Adicione versões somente quando houver tag/commit e evidência de publicação. Não
> preencha o passado por estimativa. Use o modelo abaixo para cada nova versão.

<!--
## [X.Y.Z] — AAAA-MM-DD

**Estado:** publicada  
**Commit/tag:** `...`  
**Contexto da release:** problema, objetivo ou decisão que explica este conjunto.
**Áreas afetadas:** módulos, regras ou jornadas impactadas.

### Correções
- [Contexto] comportamento corrigido; [Task/PR/commit](link).

### Modificações
- [Contexto] fluxo/regra existente alterado e efeito para usuário/agente; [ref](link).

### Implementações
- [Contexto] capacidade nova disponível e limites relevantes; [ref](link).

### Migração/compatibilidade
- Migrações, alterações incompatíveis, configuração ou `Nenhuma`.

### Publicação
- Aprovador, data e evidência/link operacional do deploy.
-->
