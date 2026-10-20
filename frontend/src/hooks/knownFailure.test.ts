import { describe, expect, it } from "vitest";
import { detectKnownFailure } from "@/hooks/useHostExecutions";

describe("detectKnownFailure", () => {
  it("recognizes a changed SSH host key", () => {
    expect(detectKnownFailure("@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@")?.kind).toBe("host_key_changed");
    expect(detectKnownFailure("Host key verification failed.")?.kind).toBe("host_key_changed");
  });

  it("recognizes a Tailscale owned by a Windows user, in tray or server mode", () => {
    expect(detectKnownFailure("401 Unauthorized: Tailscale already in use by PC\\maria, pid 8404")).toEqual(
      { kind: "tailscale_not_unattended", owner: "PC\\maria" });
    const serverMode = detectKnownFailure('Got error: 401 Unauthorized: Tailscale running in server mode ("PC\\\\maria"); connection from "PC\\\\darckware" not allowed');
    expect(serverMode?.kind).toBe("tailscale_not_unattended");
    expect(serverMode?.owner).toBe("PC\\\\maria");
    expect(detectKnownFailure("ok")).toBeNull();
  });
});
