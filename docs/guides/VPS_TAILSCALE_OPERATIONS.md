# Operação do Tailscale no VPS

## Topologia autorizada

- Controlador local: `NotebookSTI-wsl`
- Alvo remoto: `vmi3547248`
- Transporte administrativo: tailnet privado; conexão direta ou relay DERP são estados saudáveis.
- Publicação de aplicações: Cloudflare, em uma camada separada.

## Operação normal

1. Abra **Operações → VPN** com uma conta administradora.
2. Confirme que as duas pontas estão online e que o IP remoto pertence à faixa Tailscale
   `100.64.0.0/10`.
3. Use **Testar conexão**. O diagnóstico é feito com `tailscale ping` e não depende de ICMP público.
4. Se necessário, use **Reiniciar Tailscale**. O ForgeHub resolve o IP privado imediatamente antes
   da ação e nunca tenta o IP público.
5. Consulte o histórico na própria tela para conferir o resultado auditado.

## Recuperação

Se `vmi3547248` estiver offline, o ForgeHub não pode reiniciá-lo com segurança: o próprio canal
privado necessário para o SSH não existe. Use o console do provedor para recuperar `tailscaled`.
Não reabra SSH público como fallback automático.

Se o host local estiver em `NeedsLogin`, a interface retorna apenas um erro estável. Faça a
autorização diretamente no host; URLs temporárias de login nunca são propagadas ou persistidas.

## Fechamento do ingresso público

Fechar ICMP, SSH, HTTP e HTTPS no IP público é uma etapa de hardening separada desta feature.
Antes dela, valide pelo menos:

- acesso ao console do provedor;
- Tailscale ativo nas duas pontas após reinício;
- teste privado concluído no ForgeHub;
- serviços publicados funcionando pelo Cloudflare;
- nenhuma dependência operacional remanescente do IP público.

Não use esta tela para mudar firewall, Cloudflare, DNS, rotas, ACLs ou políticas do tailnet.

