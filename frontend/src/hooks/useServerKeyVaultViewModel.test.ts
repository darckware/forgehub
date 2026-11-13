import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Server } from "@/hooks/useServers";

const storeMutate = vi.fn();
const fillMutate = vi.fn();

vi.mock("@/hooks/useServers", () => ({
  useStoreServerKey: () => ({ mutate: storeMutate }),
  useClearServerKey: () => ({ mutate: vi.fn() }),
  useFillServerPublicKey: () => ({ mutate: fillMutate }),
}));

import { useServerKeyVaultViewModel } from "./useServerKeyVaultViewModel";

const server = {
  id: "srv-1",
  name: "pc-02",
  private_key_stored: false,
  ssh_key_path: null,
  duplicate_key_with: ["pc-01"],
} as unknown as Server;

describe("useServerKeyVaultViewModel", () => {
  beforeEach(() => {
    storeMutate.mockReset();
    fillMutate.mockReset();
  });

  it("sends the optional public key and shows a 409 SSH_KEY_IN_USE message as is", () => {
    storeMutate.mockImplementation((...args: unknown[]) => {
      const opts = args[1] as { onError: (e: Error) => void };
      opts.onError(
        new ApiError("Request failed with status 409", 409, {
          detail: { code: "SSH_KEY_IN_USE", message: "Esta chave já é da máquina pc-01." },
        }),
      );
    });
    const { result } = renderHook(() => useServerKeyVaultViewModel(server));
    expect(result.current.duplicateKeyWith).toEqual(["pc-01"]);
    act(() => {
      result.current.setPastedKey("-----BEGIN OPENSSH PRIVATE KEY-----\nx\n-----END OPENSSH PRIVATE KEY-----");
      result.current.setPastedPublicKey(" ssh-ed25519 AAAA test ");
    });
    act(() => result.current.storePasted());
    expect(storeMutate.mock.calls[0][0]).toMatchObject({ id: "srv-1", public_key: "ssh-ed25519 AAAA test" });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("Esta chave já é da máquina pc-01.");
  });

  it("sends null when no public key was pasted", () => {
    const { result } = renderHook(() => useServerKeyVaultViewModel(server));
    act(() => result.current.setPastedKey("-----BEGIN OPENSSH PRIVATE KEY-----"));
    act(() => result.current.storePasted());
    expect(storeMutate.mock.calls[0][0].public_key).toBeNull();
  });

  it("flags an unknown public half and fills it, showing a 409 as is", () => {
    fillMutate.mockImplementation((...args: unknown[]) => {
      const opts = args[1] as { onError: (e: Error) => void };
      opts.onError(
        new ApiError("Request failed with status 409", 409, {
          detail: { code: "SSH_KEY_IN_USE", message: "Esta chave já é da máquina pc-01." },
        }),
      );
    });
    const unknown = { ...server, key_public_unknown: true } as Server;
    const { result } = renderHook(() => useServerKeyVaultViewModel(unknown));
    expect(result.current.publicKeyUnknown).toBe(true);
    act(() => result.current.fillPublicKey());
    expect(fillMutate.mock.calls[0][0]).toBe("srv-1");
    expect(result.current.error).toBe("Esta chave já é da máquina pc-01.");
  });
});
