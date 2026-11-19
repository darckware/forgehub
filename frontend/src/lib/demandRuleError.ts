import type { TFunction } from "i18next";
import { apiErrorText } from "@/lib/apiErrorText";

/**
 * Messages' business-rule refusals in the operator's language (2026-11-19,
 * Marcelo: "Preciso que envie mensagem de erro ou crítica, de proteção da
 * regra de negócio das telas"). The backend answers a refused delete/archive
 * with a 409 `{code, message, number}`; a known code is translated
 * (`demands:ruleErrors.<CODE>`), anything else shows the backend's own words.
 */
export function demandRuleCode(error: unknown): string | null {
  const detail = ((error as { body?: { detail?: unknown } } | null | undefined)?.body)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const code = (detail as { code?: unknown }).code;
    if (typeof code === "string" && code) return code;
  }
  return null;
}

export function demandRuleText(error: unknown, t: TFunction): string {
  const code = demandRuleCode(error);
  if (code) {
    const key = `demands:ruleErrors.${code}`;
    const text = t(key);
    if (text && text !== key && text !== `ruleErrors.${code}`) return text;
  }
  return apiErrorText(error);
}

/** One refused item of a bulk action, with the message number when known. */
export interface BulkRefusal { id: string; number: number | null; error: unknown }

/** Thrown by the bulk delete/archive hooks when at least one item was refused;
 * the others were still processed, so the caller reports both counts. */
export class BulkActionError extends Error {
  done: number;
  refusals: BulkRefusal[];
  constructor(done: number, refusals: BulkRefusal[]) {
    super(`${refusals.length} item(s) refused`);
    this.name = "BulkActionError";
    this.done = done;
    this.refusals = refusals;
  }
}

/** Text for a bulk result: how many went through, then each refusal's reason
 * (grouped, so 30 identical refusals don't become 30 lines). */
export function bulkActionText(error: unknown, t: TFunction): string {
  if (!(error instanceof BulkActionError)) return demandRuleText(error, t);
  const byReason = new Map<string, number[]>();
  for (const refusal of error.refusals) {
    const reason = demandRuleText(refusal.error, t);
    const numbers = byReason.get(reason) ?? [];
    if (refusal.number !== null) numbers.push(refusal.number);
    byReason.set(reason, numbers);
  }
  const lines = [...byReason].map(([reason, numbers]) =>
    numbers.length ? `${numbers.map((n) => `#${n}`).join(", ")}: ${reason}` : reason);
  return [t("demands:ruleErrors.bulkSummary", { done: error.done, refused: error.refusals.length }), ...lines].join("\n");
}

/** Runs one request per id, never stopping at the first refusal. */
export async function settleEach(ids: string[], run: (id: string) => Promise<unknown>,
  numberOf: (id: string) => number | null = () => null): Promise<number> {
  const results = await Promise.allSettled(ids.map(run));
  const refusals: BulkRefusal[] = [];
  results.forEach((result, index) => {
    if (result.status === "rejected") {
      const id = ids[index];
      const fromBody = (result.reason as { body?: { detail?: { number?: unknown } } })?.body?.detail?.number;
      refusals.push({ id, number: typeof fromBody === "number" ? fromBody : numberOf(id), error: result.reason });
    }
  });
  const done = ids.length - refusals.length;
  if (refusals.length) throw new BulkActionError(done, refusals);
  return done;
}
