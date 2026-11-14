import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, ApiError } from "@/lib/api";
import type { ServiceRule } from "./useServiceRules";
import { useServiceRulesViewModel } from "./useServiceRulesViewModel";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ApiError: actual.ApiError, apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } };
});

function rule(agent: ServiceRule["agent"], channel: ServiceRule["channel"], content: string, hash: string): ServiceRule {
  return {
    agent, channel, file_name: `ATENDIMENTO_${channel.toUpperCase()}.md`,
    file_path: `/root/.hermes/profiles/${agent}/ATENDIMENTO_${channel.toUpperCase()}.md`,
    content, content_hash: hash, chars: content.length, max_chars: 20,
    updated_at: "2026-11-14T10:00:00Z", updated_by: "marcelo", file_state: "in_sync",
  };
}

let rules: ServiceRule[];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  rules = [rule("maia", "whatsapp", "Seja breve.", "h1"), rule("lara", "site", "Olá.", "h2")];
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.put).mockReset();
  vi.mocked(apiClient.get).mockImplementation(async (path: string) =>
    path.endsWith("/history") ? [] : rules,
  );
});

async function ready() {
  const hook = renderHook(() => useServiceRulesViewModel(), { wrapper });
  await waitFor(() => expect(hook.result.current.status).toBe("idle"));
  return hook;
}

describe("useServiceRulesViewModel", () => {
  it("is not dirty until edited and saves with the stored hash", async () => {
    const { result } = await ready();
    expect(result.current.selectedKey).toBe("maia:whatsapp");
    expect(result.current.text).toBe("Seja breve.");
    expect(result.current.dirty).toBe(false);
    expect(result.current.canSave).toBe(false);

    act(() => result.current.change("Seja breve e gentil."));
    expect(result.current.dirty).toBe(true);
    expect(result.current.chars).toBe(20);
    expect(result.current.canSave).toBe(true);

    const savedRule = { ...rules[0], content: "Seja breve e gentil.", content_hash: "h3" };
    vi.mocked(apiClient.put).mockResolvedValue(savedRule);
    rules = [savedRule, rules[1]];
    await act(() => result.current.save());
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/personal/service-rules/maia/whatsapp", {
      content: "Seja breve e gentil.", expected_hash: "h1",
    });
    expect(result.current.saved).toBe(true);
    expect(result.current.dirty).toBe(false);
    expect(result.current.text).toBe("Seja breve e gentil.");
  });

  it("blocks saving over the limit or when empty", async () => {
    const { result } = await ready();
    act(() => result.current.change("x".repeat(21)));
    expect(result.current.overLimit).toBe(true);
    expect(result.current.canSave).toBe(false);
    act(() => result.current.change("   "));
    expect(result.current.empty).toBe(true);
    expect(result.current.canSave).toBe(false);
    await act(() => result.current.save());
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("turns a stale hash into a conflict and reload brings the stored version back", async () => {
    const { result } = await ready();
    act(() => result.current.change("Minha versão."));
    vi.mocked(apiClient.put).mockRejectedValue(
      new ApiError("conflict", 409, { detail: { code: "SERVICE_RULE_CHANGED" } }),
    );
    await act(() => result.current.save());
    expect(result.current.status).toBe("conflict");
    expect(result.current.text).toBe("Minha versão.");
    expect(result.current.canSave).toBe(false);

    rules = [{ ...rules[0], content: "Versão de outra pessoa.", content_hash: "h9" }, rules[1]];
    await act(() => result.current.reload());
    await waitFor(() => expect(result.current.text).toBe("Versão de outra pessoa."));
    expect(result.current.status).toBe("idle");
    expect(result.current.dirty).toBe(false);
  });

  it("shows other save errors without entering conflict", async () => {
    const { result } = await ready();
    act(() => result.current.change("Outro texto."));
    vi.mocked(apiClient.put).mockRejectedValue(new ApiError("bad", 422, { detail: "Texto acima do limite." }));
    await act(() => result.current.save());
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("Texto acima do limite.");
  });

  it("asks before switching pair with unsaved changes", async () => {
    const { result } = await ready();
    act(() => result.current.change("Rascunho."));
    act(() => result.current.select("lara:site"));
    expect(result.current.pendingKey).toBe("lara:site");
    expect(result.current.selectedKey).toBe("maia:whatsapp");
    act(() => result.current.cancelSwitch());
    expect(result.current.pendingKey).toBeNull();
    expect(result.current.text).toBe("Rascunho.");

    act(() => result.current.select("lara:site"));
    act(() => result.current.confirmSwitch());
    expect(result.current.selectedKey).toBe("lara:site");
    expect(result.current.text).toBe("Olá.");
    expect(result.current.dirty).toBe(false);
  });

  it("switches directly when nothing was typed", async () => {
    const { result } = await ready();
    act(() => result.current.select("lara:site"));
    expect(result.current.pendingKey).toBeNull();
    expect(result.current.selectedKey).toBe("lara:site");
  });
});
