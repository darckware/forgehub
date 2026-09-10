# Pacotes e monitoramento do Nexo Remote Agent

Este runbook orienta administradores a produzir os binários do agente, baixar um pacote de instalação
por estação e acompanhar sua confirmação. A operação é interna ao ForgeHub; não cadastra clientes no
Darckware e não altera o ForgeRouter.

## Pré-requisitos e configuração

- O host bridge deve alcançar o código Nexo em `NEXO_SOURCE_PATH` (padrão
  `/root/project/nexo`).
- O host bridge grava artefatos persistentes em `NEXO_ARTIFACT_ROOT` (padrão
  `/root/forgehub-data/nexo-agent-artifacts`).
- O backend monta esse diretório como somente leitura em `/nexo-artifacts` e usa esse caminho em
  `NEXO_ARTIFACT_ROOT`.
- `NEXO_INGESTION_URL` deve ser uma URL HTTPS válida para `/api/v1/agent-reports`; usuário/senha na
  própria URL são recusados.
- As migrations do schema `company`, incluindo `5a8c1e7d9f20`, devem estar aplicadas.
- O operador precisa estar autenticado como administrador.

O banco guarda apenas uma chave relativa controlada pelo servidor para cada artefato. O host bridge
e o backend resolvem essa chave sob suas respectivas raízes; caminhos enviados pelo browser não são
aceitos.

## Atualizar o catálogo de builds

1. Abra **Operações → Agentes Nexo** (`/nexo-agents`).
2. Use **Atualizar builds**. O ForgeHub lê a revisão atual e solicita apenas os artefatos ausentes de
   Linux e Windows.
3. Aguarde o estado `ready` de cada plataforma. Confirme versão, revisão, tamanho e prefixo do
   SHA-256 antes de gerar pacotes.

Uma build `ready` é reutilizada por todas as estações compatíveis e não é sobrescrita. Uma linha
`failed` pode ser refeita pelo mesmo comando; verifique primeiro o diagnóstico redigido, acesso ao
repositório, compilador, espaço e permissões da raiz de artefatos. Uma reivindicação `building`
abandonada é recuperada após o lease interno.

## Gerar e instalar um pacote

1. Na página `/nexo-agents` filtre cliente/estação ou abra a página do cliente.
2. Confirme a build indicada automaticamente. Em `/nexo-agents`, a tela usa a build `ready` da
   revisão de origem atual e da mesma plataforma. Na página do cliente, ela prefere essa mesma build
   e, se não existir, usa outra build `ready` da plataforma como fallback visível.
3. Acione **Gerar e baixar pacote** e confirme a rotação da credencial.
4. Guarde o ZIP como segredo e transfira-o por canal autorizado.
5. Linux: extraia o ZIP e execute `install.sh` como `root`.
6. Windows: extraia o ZIP e execute `install.ps1` em PowerShell elevado; o host deve possuir
   `nssm.exe` disponível.
7. Volte à área Nexo e acompanhe o estado e o histórico.

Entradas fixas:

| Plataforma | Conteúdo |
|---|---|
| Linux | `nexo-remote-agent`, `agent.yaml`, `install.sh`, `manifest.json`, `README.txt` |
| Windows | `nexo-remote-agent.exe`, `agent.yaml`, `install.ps1`, `manifest.json`, `README.txt` |

O `manifest.json` registra estação, plataforma, versão, revisão Git e checksum do binário, mas não o
token. Compare seu `binary_sha256` com o SHA-256 do binário extraído quando houver suspeita de
corrupção.

## Consequência da credencial de uso único

Cada geração substitui imediatamente o hash do token da estação. O token em claro só existe no
`agent.yaml` dentro do ZIP retornado; não aparece em JSON, eventos ou logs. Portanto:

- um pacote anterior deixa de autenticar assim que um novo é gerado;
- download interrompido ou pacote perdido exige **gerar outro pacote**, não repetir o anterior;
- nunca cole `agent.yaml`, token ou conteúdo do ZIP em tickets, logs ou commits;
- o ZIP temporário é removido ao final ou em falha da resposta; apenas os binários compartilhados
  permanecem no armazenamento.

## Estados e recuperação

| Estado | Significado | Ação do operador |
|---|---|---|
| `package_ready` | A credencial foi rotacionada, mas a entrega não terminou. | Gere outro pacote; não reutilize o download interrompido. |
| `downloaded` | A resposta do ZIP terminou; instalação ainda não foi comprovada. | Instale/inicie o serviço e aguarde o relatório autenticado. |
| `online` | Chegou relatório válido da geração atual com a versão esperada. | Nenhuma; acompanhe o heartbeat. |
| `outdated` | Chegou relatório válido, mas a versão difere da build esperada. | Confirme a build correta e gere/instale um novo pacote. |

Em build `failed`, corrija o host bridge ou a origem e atualize o catálogo. Se já existir outra build
`ready`, ela continua disponível. Em `downloaded` sem relatório, valide serviço, rede, URL HTTPS e
relógio da estação antes de girar novamente o token.

O modelo reserva o estado `error`, mas o fluxo de produção atual não o persiste: uma falha de
empacotamento devolve erro HTTP e preserva a instalação anterior, se houver. Corrija a causa indicada
e tente gerar novamente. A persistência auditável de `error`/`last_error` permanece pendente e não
deve ser presumida na operação.

## Verificação técnica reproduzível

Carregue as variáveis do `.env` raiz sem exibi-las:

```bash
cd backend
set -a
source /root/project/forgehub/.env
set +a
POSTGRES_HOST=127.0.0.1 .venv/bin/python -m alembic current
POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest \
  app/tests/test_nexo_installation_models.py \
  app/tests/test_nexo_host_builds.py \
  app/tests/test_nexo_build_routes.py \
  app/tests/test_nexo_package_routes.py \
  app/tests/test_nexo_report_reconciliation.py \
  app/tests/test_nexo_installation_routes.py \
  app/tests/test_agent_report_ingestion.py \
  app/tests/test_workstation_routes.py -q
.venv/bin/ruff check app
```

```bash
cd frontend
npm test -- --run src/pages/nexo-agents/index.test.tsx \
  src/pages/clients/index.test.tsx \
  src/components/layout/navSections.test.tsx \
  src/lib/api.test.ts
npm run build
```

Os testes usam estações/tokens sintéticos e limpeza explícita, mas os cinco testes focados são fluxos
independentes: não foi executado um E2E único ligando a build, o token emitido pelo pacote e o primeiro
relatório. Essa verificação integrada permanece pendente. Uma validação de implantação também deve
executar uma build Linux/Windows no host bridge real, gerar pacotes para estações de teste dedicadas,
verificar os checksums, enviar relatório autenticado e remover os registros de teste. Não use uma
estação ou token de produção para smoke test.

## Fronteira de dados do cliente

Darckware será a fonte canônica do cliente. ForgeHub deve associar projetos, serviços,
desenvolvimento, estações e instalações a uma referência externa estável e única; uma projeção local
de nome/dados de exibição, se necessária, deve ser sincronizada e somente leitura. Até a migração e a
reconciliação idempotente serem implementadas, não presuma equivalência entre cadastros e não crie
integração direta entre bancos.
