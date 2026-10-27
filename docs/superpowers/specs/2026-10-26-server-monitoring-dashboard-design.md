# Monitoramento do servidor e do ecossistema no dashboard

Estado: proposta para revisão. A remoção do CLI ForgeRouter Global e o encaixe dos cards já foram solicitados diretamente; os novos monitores abaixo ainda não foram implementados.

## Objetivo

Mostrar o que está consumindo recursos, quais conexões existem, de onde vêm os acessos, se o Tailscale está ativo e quais hosts estão online. O painel deve aproveitar a tela sem alturas fixas e sem células vazias entre cards.

## Abordagem proposta

Reutilizar o dashboard, o coletor da host-bridge e as APIs já existentes de VPN, Docker e backups. Cards compactos mostram o resumo e levam aos detalhes. Uma segunda central de monitoramento duplicaria as páginas de Acesso Remoto e Controle do Sistema; colocar todas as tabelas completas na página inicial prejudicaria a leitura. A recomendação é resumo no dashboard e detalhes por bloco.

Primeira entrega com dados ao vivo, sem novo armazenamento histórico de IPs ou processos. O prazo de histórico permanece uma decisão pendente; não impede a coleta ao vivo.

## Componentes

| Card | Informações e detalhe |
|---|---|
| Memória e processos | RAM usada/disponível, cache e swap; processos e containers que mais consomem memória; PID, serviço, usuário e consumo. CPU e atividade de disco ajudam a explicar quem está processando. Argumentos de comandos não são exibidos. |
| Disco | Ocupação por filesystem, inodes, maiores diretórios autorizados, volumes/imagens/cache/logs Docker. Separar espaço ocupado de leitura/gravação atual e mostrar processos que estão gravando. |
| Rede e conexões | Download/upload por segundo, interfaces, conexões TCP/UDP, IP e porta locais/remotos, estado e processo/container quando identificável. Tráfego por IP não será inventado a partir de simples contagem de conexões. |
| Acessos | Sessões SSH ativas, origens e tentativas recentes que as fontes disponíveis permitam consultar. Acessos ao ForgeHub e aos serviços aparecem apenas quando houver registros verificáveis. IP Tailscale, conexão de rede e login humano são conceitos distintos. |
| Tailscale e hosts | Estado do daemon/login, servidor local, hosts remotos online/offline, nome, IP, SO, última vez visto e caminho direto/relay. Reutilizar `useVpnStatus` e `/api/v1/vpn/status`, com a mesma permissão de administrador. Online não significa serviço saudável nem tráfego ativo. |
| Serviços do ecossistema | Containers e serviços importantes: ForgeHub, Hermes, ForgeRouter, ForgeVault, Hindsight e aplicações implantadas. Separar processo em execução, healthcheck e endpoint disponível. Não considerar saudável um serviço sem evidência. |
| Backups e alertas | Último resultado por alvo, snapshot confirmado, falhas de backup, disco alto, coleta desatualizada e serviço indisponível. Um sucesso de outro projeto não esconde falha do sistema. |

## Coleta e autorização

- Resumos básicos usam o contrato atual de `system-stats`; novos detalhes de processos, conexões, hosts e acessos são exclusivos do administrador. Não ampliar o acesso do token de bridge para rotas administrativas.
- Tailscale, containers e backups reutilizam fontes existentes. Novos coletores do host leem `/proc`, sockets, serviços e metadados de disco; não executam comandos arbitrários enviados pelo navegador.
- Atualizações leves a cada 5–15 segundos, com timeout, cache curto e pausa quando a aba estiver oculta. Scans de diretórios e Docker são separados, limitados e atualizados em minutos; não executar varredura completa do disco a cada atualização.
- Raízes propostas para detalhamento de diretórios: `/root/project`, `/root/db`, `/root/backup`, `/root/.hermes`, `/root/.cache` e `/var/log`. Mostrar tamanho agregado dessas áreas, sem conteúdo dos arquivos, sem seguir links simbólicos nem atravessar outros filesystems. Docker usa sua API de ocupação. Áreas fora da lista aparecem como espaço não detalhado, sem atribuição inventada; ampliar a lista exige configuração administrativa explícita.
- Taxas usam duas amostras e tempo monotônico. A primeira amostra e contadores reiniciados aparecem como indisponíveis até haver medida válida.
- Mostrar horário da coleta, indisponibilidade, erros e truncamento. Fonte indisponível não vira zero, lista vazia ou status online.
- Não coletar conteúdo de arquivos, pacotes, senhas, tokens ou argumentos completos dos processos. IP de visitante atrás de proxy só pode ser atribuído usando a configuração confiável desse proxy; não confiar cegamente em cabeçalhos recebidos.

## Organização da tela

Cards independentes, com altura de conteúdo e uma coluna no celular. Em telas maiores, encaixe em colunas, espaçamento uniforme e leitura previsível. Listas de hosts/processos têm resumo e acesso ao detalhe para impedir um único card de dominar a tela. Valores atualizam sem remontar a página inteira. Manter tema, fontes, componentes e idiomas existentes.

## Aceite

1. CLI ForgeRouter Global ausente, sem alterar configurações de ferramentas.
2. Tailscale ativo e hosts online correspondem à fonte; falha de coleta não é apresentada como offline.
3. Administrador identifica os maiores consumidores e conexões por IP; usuário comum não recebe detalhes restritos.
4. Espaço ocupado, I/O, tráfego acumulado e velocidade atual têm rótulos distintos.
5. Página utilizável a 390 px e em desktop, sem rolagem horizontal nem alturas artificiais nos cards.
6. Validar valores conhecidos, reset de contadores, permissão, erros, fonte lenta, lista vazia e dados desatualizados.

Esta proposta não autoriza reiniciar serviços, encerrar processos, bloquear IPs ou implementar retenção histórica. Essas ações não fazem parte do monitoramento solicitado.
