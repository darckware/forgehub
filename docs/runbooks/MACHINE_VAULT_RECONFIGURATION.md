# Regularizing machine logins in ForgeVault

The machine inventory's Login is an operating-system account, not an agent assignment. The machine account is `darckware`. Agent authorization remains exclusively in Remote Access → Agents. Do not remove agent permissions to migrate a machine login.

## Before deployment

Implementation is prepared in the task worktree. Do not treat this runbook as evidence that production machines were changed. Obtain Marcelo's approval of the reviewed diff before merge/deploy; apply its schema migration with the release. Preserve an operator recovery path.

## Every legacy machine

1. In Machines, search the legacy login (for example `aegis`) to enumerate affected records across servers and workstations. Include offline/disabled machines in the migration inventory; they are not silently completed. Names, address, old login and pending status are metadata; never export passwords or private keys.
2. Confirm the target machine by both its registered address and hostname. For example, srv-app02 should be independently confirmed as 172.15.2.3.
3. Choose Configure/Reconfigure access even if the current SSH transport is Ready. The panel uses the same workflow for servers and workstations. Set the machine's Linux/Windows operating system first if missing.
4. Use an operator-controlled administrator bootstrap credential. If the machine account darckware already exists, it may configure itself with its own credential; disabling that account is forbidden. A stored password may only be used for the same machine when its registered login is already darckware. No arbitrary secret ID is accepted from the browser.
5. ForgeHub stages a newly generated password and a dedicated SSH key in ForgeVault. The password is unique per machine. Current active login, port and credential references remain in place until verification succeeds. No agent receives the private key.
6. SSH mode applies the machine configuration and verifies the exact darckware identity with the candidate key. Only successful verification activates the registration. Keep the old administrator enabled during migration unless its removal is separately authorized and its recovery implications reviewed.
7. Copy mode requires the operator to apply the script and then choose Validate access. Closing/reloading does not activate the candidate. Recover pending instructions retrieves the same staged script rather than creating another password/key. After an uncertain execution, validate the current state first; do not blindly rerun provisioning.
8. On failure, preserve the pending record and inspect the execution/error. Do not edit remote_user to darckware manually, delete pending state or force a Ready label to bypass verification.
9. Record each machine's verification/audit execution and confirm its login and dedicated credential metadata. Keep unresolved/offline machines on the migration list. Historical executions under aegis remain historical evidence and must not be rewritten.

## Acceptance with agents

After operator preparation, dispatch an authorized ForgeHub Messages task to the selected agent. Confirm `hostname` and `id -un`/`whoami` through ForgeHub and retain the maintenance execution ID. The operating-system user must be darckware; the audit actor remains the actual agent. Test refusals/pausing separately in a controlled environment. Component tests and simulated bridge calls do not establish real agent access.
