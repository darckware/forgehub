import { describe, expect, it } from "vitest";

import { vpnActionPath, vpnKeys } from "./useVpn";


describe("VPN API client contract", () => {
  it("routes actions only through a logical node path", () => {
    expect(vpnActionPath("local")).toBe("/api/v1/vpn/nodes/local/actions");
    expect(vpnActionPath("remote")).toBe("/api/v1/vpn/nodes/remote/actions");
  });

  it("keeps status and operation caches independently invalidatable", () => {
    expect(vpnKeys.status).toEqual(["vpn", "status"]);
    expect(vpnKeys.operations).toEqual(["vpn", "operations"]);
  });
});
