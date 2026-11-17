# Remote Access Host Editing Plan

> **For agentic workers:** Use this plan after the current queue and remote-access corrections. Keep the checkpoint in the master plan current.

## Goal

In Acesso Remoto, identify the record as a host, allow its name to be edited, and make save failures diagnosable and correct. Preserve credentials and access configuration during a name-only edit.

## Evidence so far

- The screenshot is rendered by the shared `ServerForm` (`frontend/src/pages/servers/ServerForm.tsx`), opened from the Remote Access machine card.
- The current label is `servers.form.name` (“Nome do servidor” in pt-BR).
- The form submits `PUT /api/v1/servers/{id}` through `useUpdateServer()` and collapses every rejection into the generic `form.saveFailed` message.
- The backend update route accepts `name`, but the actual rejection shown in the screenshot is not yet known. Do not assume the cause before reproducing it.

## Files to inspect

- `frontend/src/pages/servers/ServerForm.tsx`
- `frontend/src/hooks/useServers.ts`
- `frontend/src/pages/remote-access/MachinesCard.test.tsx` and server-form tests
- `frontend/src/i18n/locales/{pt-BR,en,es}/remoteAccess.json`
- `backend/app/api/routes/server.py` and `backend/app/api/schemas/server.py`
- Focused server API tests in `backend/app/tests/`

## Acceptance checklist

- [x] The edit form label reads “Nome do host” in Portuguese and equivalent “Host name” / “Nombre del host” in English and Spanish.
- [x] A host name can be changed and saved through the Remote Access edit panel; the panel closes and the refreshed list shows the new name.
- [x] Reproduce the reported failure against an isolated test fixture, capture the actual HTTP status/detail, and fix that cause rather than masking it.
- [x] If a save is still rejected, show a useful, safe error that identifies the reason without exposing secrets or internal stack traces.
- [x] A name-only edit preserves SSH login, address, key/passphrase, group memberships, host classification, client association, and verified-access state.
- [x] A duplicate or invalid name remains rejected with a useful message, and the panel keeps the user's unsaved input.
- [x] Focused frontend and isolated backend tests pass; locale catalogs pass; `git diff --check` is clean.
- [ ] Check 390 px and 1440 px layouts if an allowed preview/browser path is available; record unavailable checks honestly.

## Constraints

- Do not use production rows to reproduce a save.
- Do not clear or rewrite SSH credentials as a side effect of renaming.
- No commit, push, merge, or deploy without Marcelo's explicit approval of the exact content.
