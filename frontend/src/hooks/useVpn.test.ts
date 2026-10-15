import { describe, expect, it } from "vitest";

import { tagLabel, vpnActionPath, vpnKeys } from "./useVpn";


describe("Remote Access API client contract", () => {
  it("routes actions only through a logical node path", () => {
    expect(vpnActionPath("self")).toBe("/api/v1/vpn/nodes/self/actions");
    expect(vpnActionPath("nKqVMEy38E11CNTRL")).toBe("/api/v1/vpn/nodes/nKqVMEy38E11CNTRL/actions");
    expect(vpnActionPath("../x")).toBe("/api/v1/vpn/nodes/..%2Fx/actions");
  });

  it("keeps status and operation caches independently invalidatable", () => {
    expect(vpnKeys.status).toEqual(["vpn", "status"]);
    expect(vpnKeys.operations).toEqual(["vpn", "operations"]);
  });

  it("strips the tag: prefix for display", () => {
    expect(tagLabel("tag:gatling-users")).toBe("gatling-users");
    expect(tagLabel("plain")).toBe("plain");
  });
});
