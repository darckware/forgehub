import { describe, expect, it } from "vitest";
import { filterDocumentTree } from "@/components/DocumentBrowser";
import type { DocTreeNode } from "@/components/DocTree";

const tree: DocTreeNode[] = [
  {
    name: "agents",
    path: "agents",
    type: "dir",
    children: [
      { name: "AEGIS.md", path: "agents/AEGIS.md", type: "file" },
      { name: "ATHOS.md", path: "agents/ATHOS.md", type: "file" },
    ],
  },
  { name: "README.md", path: "README.md", type: "file" },
];

describe("filterDocumentTree", () => {
  it("keeps ancestor directories around matching files", () => {
    expect(filterDocumentTree(tree, "aegis")).toEqual([
      {
        name: "agents",
        path: "agents",
        type: "dir",
        children: [{ name: "AEGIS.md", path: "agents/AEGIS.md", type: "file" }],
      },
    ]);
  });

  it("matches full paths case-insensitively", () => {
    expect(filterDocumentTree(tree, "AGENTS/ATHOS")).toEqual([
      {
        name: "agents",
        path: "agents",
        type: "dir",
        children: [{ name: "ATHOS.md", path: "agents/ATHOS.md", type: "file" }],
      },
    ]);
  });

  it("returns the original tree for an empty query", () => {
    expect(filterDocumentTree(tree, "  ")).toBe(tree);
  });
});
