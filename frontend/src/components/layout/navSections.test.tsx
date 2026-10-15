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
  it("places Remote Access in Operations as an administrator-only page", () => {
    const entry = remoteAccessEntry();

    expect(entry.labelKey).toBe("nav.remoteAccess");
    expect(entry.module).toBe("vpn");
    expect(entry.adminOnly).toBe(true);
  });

  it("hides administrator-only links from non-admin navigation consumers", () => {
    const entry = remoteAccessEntry();

    expect(isNavEntryVisible(entry, false)).toBe(false);
    expect(isNavEntryVisible(entry, true)).toBe(true);
  });
});

describe("Clients navigation policy", () => {
  it("places Clients in Operations under the clients module", () => {
    const operations = NAV_SECTIONS.find((section) => section.labelKey === "nav.section.operations");
    const entry = operations?.entries.find(
      (candidate) => candidate.type === "link" && candidate.to === "/clients",
    );

    expect(entry).toMatchObject({ labelKey: "nav.clients", module: "clients" });
  });
});
