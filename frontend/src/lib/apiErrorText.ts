/**
 * The backend's own words for a failed request, shown as is: a string
 * `detail`, or the `message` of a `{code, message}` detail (e.g. 409
 * SSH_KEY_IN_USE naming the machine that already has a key). Falls back to the
 * error's own message.
 *
 * Its own module, and duck-typed on `body` rather than `instanceof ApiError`,
 * so tests that mock `@/lib/api` keep working with the components using it.
 */
export function apiErrorText(error: unknown): string {
  const body = (error as { body?: unknown } | null | undefined)?.body;
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return error instanceof Error ? error.message : String(error);
}
