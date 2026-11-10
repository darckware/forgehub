# Terminal release verification

Source commit: `be4677f`; first OOM hotfix: `0343e23` / develop `5cec84d`.

- Frontend: 108 files / 502 tests passed with one worker.
- Selected session/notes/workspace UI: 10 tests passed.
- Bridge terminal suite: 9 tests passed, including multiple attached clients.
- Locales pt-BR/en/es matched; TypeScript and Vite build passed.
- The first build used an insufficient 1536 MB Node heap and aborted. The
  sequential 2560 MB build passed. Existing tmux sessions survived.
- Browser fixtures at 1440/390 px: names, connection labels, named destructive
  confirmation, Escape/focus restoration and no destructive requests passed.
  Screenshots use local synthetic UI data; they are not production data.
- Independent read-only reviews found no blocking issue in the scoped changes.
- Premium static audit: 50 findings outside the altered session-list files;
  none in those changed files. The general audit is not green.
- First frontend rollout rolled back because an authenticated route was used
  incorrectly as a health check. The corrected rollout verified exact HTML,
  protected-route HTTP 401 and healthy unchanged backend.
- Actual deployed image, artifact checksums, backend preservation and rollback
  are recorded in the adjacent release JSON files.
- Existing scope OOMPolicy=continue and unchanged tmux server/pane PIDs were
  verified. A separate tmux socket confirmed the policy for a new scope. No
  actual host OOM was induced.

The large Mission/Messages implementation is NOT deployed by this release.
Its WIP recovery snapshot is `c9cc7f4`, on the remote checkpoint branch.
