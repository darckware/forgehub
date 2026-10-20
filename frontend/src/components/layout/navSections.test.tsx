import { describe, expect, it } from "vitest";

import { NAV_SECTIONS, isNavEntryVisible, type NavLinkEntry } from "./navSections";


function remoteAccessEntry(): NavLinkEntry {
  const operations = NAV_SECTIONS.find((section) => section.labelKey === "nav.section.operations");
  const entry = operations?.entries.find(
    (candidate) => candidate.type === "link" && candidate.to === "/remote-access",
  );
  if (!entry || entry.type !== "link") throw new Error("Remote Access entry missing");
  return entry;
}


describe("Remote Access navigation policy", () => {
  // Servers and Remote Access became one screen (2026-10-17): one entry,
  // gated on the "servers" module, open to non-admins who have it.
  it("places Remote Access in Operations on the servers module", () => {
    const entry = remoteAccessEntry();

    expect(entry.labelKey).toBe("nav.remoteAccess");
    expect(entry.module).toBe("servers");
    expect(entry.adminOnly).toBeFalsy();
    expect(isNavEntryVisible(entry, false)).toBe(true);
  });

  it("no longer links the old /servers page", () => {
    const links = NAV_SECTIONS.flatMap((section) => section.entries)
      .filter((candidate) => candidate.type === "link")
      .map((candidate) => candidate.to);

    expect(links).not.toContain("/servers");
  });
});

describe("Clients navigation policy", () => {
  // The Nexo /clients screen was removed (2026-10-17); Darckware clients live
  // under the "Clientes" section at /client-accounts.
  it("no longer links the retired Nexo /clients screen", () => {
    const links = NAV_SECTIONS.flatMap((section) => section.entries)
      .filter((candidate) => candidate.type === "link")
      .map((candidate) => candidate.to);

    expect(links).not.toContain("/clients");
    expect(links).toContain("/client-accounts");
  });
});
