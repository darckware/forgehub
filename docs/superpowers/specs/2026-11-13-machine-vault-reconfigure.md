# Machine login reconfiguration

Marcelo requested reconfiguration of every legacy machine using `aegis`, including machines whose SSH transport currently reports Ready. The machine login and the agent allowed to operate it are separate identities.

## Contract

- Every supported enabled server/workstation exposes Configure/Reconfigure access, regardless of SSH readiness. It opens the same preparation owner.
- The final machine account is `darckware`, with a unique generated password and a dedicated SSH key stored in ForgeVault. Agent permissions remain unchanged.
- Show legacy logins as requiring reconfiguration. SSH connectivity remains visible separately; a responding legacy login does not demonstrate migration.
- Reconfiguration accepts an operator-supplied bootstrap credential, or the password already stored for this same machine when its registered login is `darckware`. Never accept an arbitrary secret reference from the browser.
- Existing `darckware` may bootstrap itself but must never be disabled. The backend enforces this as well as the UI.
- Store new credentials in ForgeVault before executing, but promote active references and machine login only after exact identity/key verification. Preserve the previous active registration on failure.
- Copy mode stages the candidate credentials. Applying the script and explicit key validation are required before activation. Reloading the screen retains pending validation.
- Do not mutate all machine records to `darckware` without verifying their remote login. Migration proceeds per machine through the audited operator workflow, including offline machines later.
- No production permission/account changes, merge, push, or deployment are part of implementation acceptance.

## UX

Reuse MachinesCard, PrepareDialog/SidePanel, native Select, secret Input and existing operational badges. Preserve the navy theme and density documented in DESIGN.md. Labels and errors exist in pt-BR/en/es. Pending, failure and success remain explicit; secret values never appear in feedback.

## Acceptance

Component tests cover Ready legacy servers opening preparation, existing darckware without self-lock, machine-only stored credentials and staged copy validation. Backend tests cover credential isolation, failed promotion, exact identity and copy staging. Supervisor runs the relevant isolated checks and inspects the changed flow at 390px/1440px. Live migration is separate and requires operator credentials and deployment approval.
