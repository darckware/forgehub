import { describe, expect, it } from "vitest";
import { describeClientOpsError } from "./useClientOps";

const t = (key: string, options?: Record<string, unknown>) =>
  key === "errors.no_client" ? "sem cliente" : key === "errors.darckware_rejected" ? `recusou: ${options?.reason}` : `[${key}]`;

describe("describeClientOpsError", () => {
  it("translates a coded detail and fills its params", () => {
    const err = { status: 422, body: { detail: { code: "darckware_rejected", message: "x", params: { reason: "Destinatário não vinculado" } } } };
    expect(describeClientOpsError(err, t)).toBe("recusou: Destinatário não vinculado");
    expect(describeClientOpsError({ status: 422, body: { detail: { code: "no_client", message: "x" } } }, t)).toBe("sem cliente");
  });

  it("falls back to a plain detail, then to the status, never to the technical message", () => {
    expect(describeClientOpsError({ status: 400, body: { detail: "Senha atual incorreta" } }, t)).toBe("Senha atual incorreta");
    expect(describeClientOpsError({ status: 502, body: {} }, t)).toBe("[errors.server]");
    expect(describeClientOpsError(new Error("Request to /api/v1/x failed with status 404"), t)).toBe("[errors.generic]");
  });
});
