import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { BulkActionError, bulkActionText, demandRuleText, settleEach } from "./demandRuleError";

const texts: Record<string, string> = {
  "demands:ruleErrors.RECONCILIATION_REQUIRED": "Reconcilie antes",
  "demands:ruleErrors.bulkSummary": "{{done}} ok, {{refused}} recusadas:",
};
const t = ((key: string, values?: Record<string, unknown>) => {
  const text = texts[key] ?? key;
  return text.replace(/\{\{(\w+)\}\}/g, (_, name) => String(values?.[name]));
}) as unknown as TFunction;
const refused = (code: string | null, number: number, message = "backend words") => Object.assign(new Error("409"), {
  body: { detail: code ? { code, message, number } : message },
});

describe("demandRuleError", () => {
  it("translates a known code and falls back to the backend's words", () => {
    expect(demandRuleText(refused("RECONCILIATION_REQUIRED", 7), t)).toBe("Reconcilie antes");
    expect(demandRuleText(refused("SOMETHING_NEW", 7, "New rule"), t)).toBe("New rule");
    expect(demandRuleText(refused(null, 7, "plain detail"), t)).toBe("plain detail");
  });

  it("tries every id and reports the refusals grouped by reason", async () => {
    const run = (id: string) => (id === "ok" ? Promise.resolve() : Promise.reject(refused("RECONCILIATION_REQUIRED", Number(id))));
    const error = await settleEach(["ok", "1", "2"], run).catch((e) => e);
    expect(error).toBeInstanceOf(BulkActionError);
    expect(error.done).toBe(1);
    expect(bulkActionText(error, t)).toBe("1 ok, 2 recusadas:\n#1, #2: Reconcilie antes");
    await expect(settleEach(["ok"], run)).resolves.toBe(1);
  });
});
