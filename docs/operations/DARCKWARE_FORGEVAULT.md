# Credencial Darckware do backend ForgeHub

O backend usa a identidade `service:forgehub-production`, no ambiente Production do projeto
Darckware. Ela tem concessão direta somente ao segredo `DARCKWARE_AGENT_TOKEN_FORGEHUB`.

O segredo de serviço dessa identidade fica criptografado pelo `systemd-creds` em
`/root/.config/forgevault/forgehub-production-token`. Antes de iniciar o Compose, o script
`scripts/compose-vault.py` usa essa identidade para revelar o segredo no ForgeVault e confere a
identidade, o recurso e o formato da resposta. O valor fica em `/run/forgehub-secrets/` (tmpfs,
arquivo modo 0600) e é montado como segredo somente leitura em
`/run/secrets/darckware_agent_token` no container. Ele não deve ser copiado para `.env`.

`forgehub-vault-credential.service` busca a credencial e recria somente `forgehub-backend` no boot,
depois do Docker. `scripts/build.sh` e `scripts/deploy.sh` também passam pelo carregador do Vault.
Para validar a integração, confira a saúde do container e faça uma leitura autenticada de baixo
impacto pela integração Darckware; nunca imprima o conteúdo do arquivo de segredo.

Se a credencial upstream do Darckware for rotacionada, atualize a versão do segredo no ForgeVault e
execute `systemctl restart forgehub-vault-credential.service`. A chamada de leitura autenticada deve
ser confirmada antes de retirar qualquer versão ou acesso de recuperação.
