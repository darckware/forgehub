# Idiomas em todas as telas — plano de implementação

**Objetivo:** oferecer a interface inteira do ForgeHub em `pt-BR`, `en` e `es`, com troca previsível e preferência persistida por usuário.

**Base do plano:** solicitação de 2026-10-04, captura da tela de Configurações, `UX-CONTRACT.md` e arquitetura existente em `frontend/src/i18n/index.ts`. O plano não pressupõe que escolher o idioma padrão do sistema altere a sessão atual.

## Diagnóstico confirmado no código

- Os três códigos já são aceitos pelo frontend, pelo modelo `User.ui_language` e pela validação da API. O fallback do i18next é `pt-BR`.
- Há 41 namespaces e cerca de 4,38 mil folhas de tradução em `pt-BR` e `en`; `es` possui apenas 12 namespaces e cerca de 1,17 mil folhas. O namespace `settings`, exibido na captura, não existe em espanhol. A ausência de chave aciona o fallback português e produz telas com idiomas misturados.
- Na tela capturada, `default_ui_language` configura o idioma **inicial de novos usuários**. A interface da sessão vem de `User.ui_language`, alterável em **Conta → Idioma**. Portanto, o padrão em português e a sessão em inglês podem coexistir sem erro de persistência. A redação e a posição dos controles tornam isso pouco evidente.
- A tela de Configurações e o menu lateral já usam `useTranslation`; o inglês da captura corresponde ao idioma efetivo da conta, e não demonstra, por si só, que as chaves dessas duas telas estejam ausentes em português.
- Entre 94 arquivos de página `.tsx` (sem testes), 20 não usam `useTranslation` diretamente. É uma lista de triagem, pois componentes filhos podem traduzir o conteúdo; precisa de revisão visual e de código. Inclui Login, System Control, Servers, Skills, ForgeRouter, Database e outras telas.
- O idioma do chat de IA é uma configuração separada e hoje oferece seis opções (`pt-BR`, `en`, `es`, `fr`, `de`, `it`). O pedido de três idiomas precisa ser aplicado de modo explícito à interface e, para consistência do produto, também às opções novas do chat, com tratamento dos valores legados.
- Não foi encontrada sincronização do atributo `document.documentElement.lang` quando o idioma muda.

## Contrato de comportamento

1. Os únicos idiomas selecionáveis para a interface são `pt-BR`, `en` e `es`. O fallback para preferência ausente/inválida é `pt-BR`, sem mostrar chaves de tradução ao usuário.
2. **Idioma da minha interface** pertence à conta; a alteração salva `User.ui_language`, atualiza a tela imediatamente após sucesso e continua válida após recarga, novo login e outro navegador. Ao falhar, mantém o idioma anterior e mostra erro traduzido.
3. **Idioma padrão para novos usuários** pertence à administração; não muda contas existentes. A tela deve explicar isso junto ao controle e oferecer um atalho claro para o idioma pessoal.
4. **Idioma das respostas do chat** continua independente do idioma da interface. Novas escolhas ficam limitadas a `pt-BR`, `en` e `es`. Antes de restringir a validação da API, localizar configurações `fr/de/it` já salvas e definir migração explícita para `pt-BR`, comunicada na interface; evitar uma opção selecionada inválida ou perda silenciosa.
5. Tradução cobre texto de produto em todas as rotas: navegação, títulos, formulários, validações, confirmações, estados de carregamento/vazio/erro, notificações, tooltips, `aria-label`, paginação e títulos do documento. Dados cadastrados por usuários, código, logs e saídas dos agentes preservam o texto original.
6. Datas, números e horas usam a localidade ativa; o fuso configurado continua sendo aplicado aos instantes. `html.lang` acompanha a escolha e o layout aceita textos mais longos sem corte em desktop e celular.

## Etapas de execução

### 1. Inventário e testes de base

- [ ] Criar um inventário das rotas de `frontend/src/App.tsx` e dos componentes compartilhados. Para cada rota, registrar textos fixos, namespace, estados, datas/números, título e responsável pela correção. Usar a lista de 20 páginas sem `useTranslation` como ponto de partida, sem tratá-la como diagnóstico completo.
- [ ] Criar `frontend/scripts/check-locales.mjs` para comparar namespaces, chaves folha, tipos, placeholders/interpolações e plurais nos três idiomas. Adicionar `npm run i18n:check` no `frontend/package.json`; o comando deve falhar com namespace/chave específicos.
- [ ] Registrar testes que reproduzam as lacunas atuais: mudança de idioma pessoal e padrão administrativo em `frontend/src/components/layout/UserSettingsMenu.test.tsx` e novo `frontend/src/pages/settings/index.test.tsx`; paridade de catálogos em teste do script.
- [ ] Critério: inventário completo e falhas de cobertura reproduzíveis antes da tradução em massa.

### 2. Seleção, persistência e semântica dos três controles

- [ ] Centralizar os códigos e nomes de idioma em `frontend/src/i18n/index.ts` (ou módulo pequeno ao lado) e eliminar listas locais divergentes em `frontend/src/pages/settings/index.tsx` e `frontend/src/components/layout/UserSettingsMenu.tsx`.
- [ ] Ajustar `frontend/src/hooks/useAuth.ts` e o estado da conta para garantir troca após salvar, sincronização entre recarga/login e rollback visível em erro. Atualizar `html.lang` em toda mudança de idioma, inclusive no primeiro carregamento e no login.
- [ ] Reescrever a seção Idioma de Configurações e o modal Conta nos três catálogos `settings.json`/`common.json`: diferenciar “Meu idioma”, “Padrão para novos usuários” e “Respostas do chat”; colocar o caminho de alteração pessoal onde o usuário espera encontrá-lo.
- [ ] Alinhar opções de chat em frontend/backend (`frontend/src/pages/settings/index.tsx`, `backend/app/core/config.py`, `backend/app/api/routes/system_control.py`) com migração verificável de `fr/de/it` salvos. Cobrir novo usuário, usuário existente, valor legado e erro de salvamento em testes frontend e backend.
- [ ] Critério: escolher português na conta muda menu e Configurações para português; alterar só o padrão administrativo não muda a conta atual.

### 3. Cobertura de traduções por área funcional

- [ ] Completar os 29 namespaces ausentes em espanhol e as chaves parciais dos 12 existentes; corrigir a divergência pequena em `forgerouter` entre português e inglês. Revisar traduções por contexto, sem copiar texto português para preencher espanhol.
- [ ] Migrar textos fixos das telas e componentes do inventário para `t(...)`, criando namespaces por domínio conforme o padrão atual. Ordem sugerida: (a) Login, shell, Configurações e System Control; (b) Workspace, chat e agentes; (c) operações, Auditor, Crons, deploy e servidores; (d) clientes, projetos, planejamento e demais ferramentas.
- [ ] Localizar mensagens de erro vindas da API por códigos estáveis no cliente quando forem mensagens de produto. Preservar detalhes técnicos e mensagens livres da API como dados, sem traduzi-los automaticamente.
- [ ] Critério por lote: rota e seus diálogos completos nos três idiomas, sem fallback visível ou texto fixo de produto; build e testes da área passando antes do lote seguinte.

### 4. Formatação, acessibilidade e proteção contra regressão

- [ ] Criar ou consolidar utilitários de formatação com `Intl` vinculados ao idioma ativo; substituir formatos fixos nos locais apontados pelo inventário. Testar datas, números e fuso nos três idiomas.
- [ ] Cobrir `html.lang`, nomes acessíveis, foco dos controles e expansão de texto. Inspecionar as rotas em 390 px e desktop, nos temas em uso, conforme `DESIGN.md` e `UX-CONTRACT.md`.
- [ ] Rodar `npm run i18n:check`, `npm test` e `npm run build` no frontend, além de `pytest` para a migração/validação do chat. Fazer smoke no navegador com uma conta por idioma, recarga, login novo, troca de idioma e telas de erro/vazio.
- [ ] Integrar `i18n:check` à verificação contínua para impedir novos namespaces/chaves incompletos. Atualizar `UX-CONTRACT.md` com o contrato final dos três controles e a política de fallback.

## Critério final de aceite

- Todas as rotas navegáveis de `App.tsx` e seus diálogos aparecem integralmente em `pt-BR`, `en` e `es`; não há chaves literais nem mistura involuntária de idiomas na interface.
- A conta mantém o idioma escolhido após recarga e login; o padrão administrativo afeta só contas criadas depois da alteração; as respostas do chat seguem sua configuração própria.
- Os catálogos têm paridade validada automaticamente e os testes/build passam.
- O usuário pode distinguir claramente os três controles de idioma na tela, inclusive no celular.

## Ordem de entrega recomendada

Entregar a etapa 2 junto com o primeiro lote da etapa 3 para resolver a confusão mostrada na captura. Depois liberar cada área funcional com seu catálogo espanhol completo e verificações próprias. Publicar a cobertura geral somente após o inventário inteiro e o smoke dos três idiomas.
