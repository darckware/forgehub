import { describe, expect, it } from "vitest";

import { NAV_SECTIONS, isNavEntryVisible, type NavLinkEntry } from "./navSections";


function vpnEntry(): NavLinkEntry {
  const operations = NAV_SECTIONS.find((section) => section.labelKey === "nav.section.operations");
  const entry = operations?.entries.find(
    (candidate) => candidate.type === "link" && candidate.to === "/vpn",
  );
  if (!entry || entry.type !== "link") throw new Error("VPN entry missing");
  return entry;
}


describe("VPN navigation policy", () => {
  it("places VPN in Operations as an administrator-only page", () => {
    const entry = vpnEntry();

    expect(entry.labelKey).toBe("nav.vpn");
    expect(entry.module).toBe("vpn");
    expect(entry.adminOnly).toBe(true);
  });

  it("hides administrator-only links from non-admin navigation consumers", () => {
    const entry = vpnEntry();

    expect(isNavEntryVisible(entry, false)).toBe(false);
    expect(isNavEntryVisible(entry, true)).toBe(true);
  });
});
