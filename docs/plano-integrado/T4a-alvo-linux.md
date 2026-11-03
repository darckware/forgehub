# T.4a — inventário antes do provisionamento

- Execução em máquina: `backend/app/api/routes/host_execution.py` cria a execução; `backend/app/core/host_exec_runner.py` chama o bridge em `/v1/servers/exec`.
- O stub `backend/app/tests/fixtures/integration_stub.py`, no ramo `servers/`, responde “nothing ran” para alvos fictícios e 403 para alvos reais.
- As rotas `/api/v1/host-executions/agent...` exigem delegação `AuthorityDelegation` com `remote_access.execute` e `max_risk` suficiente, script da biblioteca, `message_number` de Task com permissão registrada em `agent_maintenance_request` e máquina com login do ForgeHub.
- O seed `backend/app/scripts/seed_test_database.py` contém quatro máquinas fictícias.
- Capacidade antes do provisionamento: `free -m`: 11960 MiB total, 8808 usados, 961 livres, 3151 disponíveis, swap 0. `docker stats --no-stream`: alvo de teste inexistente; backend de teste 146 MiB/512 MiB, Postgres de teste 45,42 MiB/512 MiB, stub 38,98 MiB/128 MiB e gateway 1,754 MiB/64 MiB.

## Desenho e rollback

O serviço `forgehub_test_linux_target` usa SSH na rede interna de teste, com endereço `172.25.0.14`, alias `linux-target.test`, usuário `darckware` e chave exclusiva de teste ignorada pelo Git. O gateway expõe apenas `127.0.0.1:2222`. O stub monta a chave privada somente para leitura e só executa quando todos os alvos coincidem com o nome configurado; outros nomes fictícios são simulados e endereços reais são recusados. Não há dados ou credenciais de cliente.

Para reverter, remova o serviço e o encaminhamento de porta do gateway e retire a execução SSH do stub; o stub volta a responder “nothing ran” para alvos fictícios. Preserve o banco e seu volume.
