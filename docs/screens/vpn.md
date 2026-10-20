# Controle VPN

## Objetivo

A rota administrativa `/vpn` mostra e controla a conexão privada Tailscale entre
`NotebookSTI-wsl` e `vmi3547248`. Ela é um plano operacional independente do Cloudflare.

## O que a tela mostra

- estado, IP Tailscale, daemon, atividade e tráfego de cada ponta;
- caminho observado (`direct`, `DERP`, `idle` ou `unavailable`) e latência do último teste;
- postura local restrita: DNS, rotas aceitas, exit node e Tailscale SSH;
- histórico auditável das últimas 25 ações explícitas.

## Ações disponíveis

| Alvo | Ações |
|---|---|
| Host local | Conectar, desconectar, reiniciar o daemon e testar a conexão |
| VPS remoto | Reiniciar o daemon e testar a conexão |

Não existe desconexão remota. O reinício do VPS só usa o IP privado resolvido do estado vivo do
Tailscale e fica indisponível quando o peer está offline. Nesse caso, a recuperação deve usar o
console do provedor.

Desconexões e reinícios usam o diálogo de confirmação do ForgeHub. Testes são não disruptivos e
começam imediatamente. Enquanto uma ação está em andamento, os controles do mesmo nó ficam
bloqueados. O backend aplica a mesma allow-list e registra ator, alvo, ação, resultado e horário.

## Limites de segurança

A tela não altera UFW/firewall, portas públicas, Cloudflare Tunnel/Zero Trust, DNS, ACLs, rotas,
MagicDNS, exit nodes, Serve, Funnel ou Tailscale SSH. Ela nunca mostra chaves, caminhos de chaves,
URLs de autenticação, comandos ou saída bruta de processos.

O teste usa `tailscale ping`, não ICMP público. Assim, fechar ICMP, SSH, HTTP e HTTPS no IP público
do VPS não muda o contrato desta tela.

