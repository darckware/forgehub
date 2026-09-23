import { describe, expect, it } from "vitest";
import {
  baseName,
  copyName,
  fileKind,
  formatSize,
  isTextLike,
  isValidName,
  joinPath,
  parentPath,
  pathSegments,
  type ExplorerEntry,
} from "./useFileExplorer";
import { sortEntries } from "./useFileExplorerViewModel";
import { topLevelNames } from "@/components/explorer/droppedFiles";

const entry = (name: string, type: "file" | "dir", extra: Partial<ExplorerEntry> = {}): ExplorerEntry => ({
  name,
  path: `/x/${name}`,
  type,
  size: type === "dir" ? null : 1,
  modified: 0,
  is_symlink: false,
  ...extra,
});

describe("explorer path helpers", () => {
  it("joins and splits POSIX paths", () => {
    expect(joinPath("/", "etc")).toBe("/etc");
    expect(joinPath("/root/", "a/b.txt")).toBe("/root/a/b.txt");
    expect(parentPath("/root/project")).toBe("/root");
    expect(parentPath("/root")).toBe("/");
    expect(parentPath("/")).toBeNull();
    expect(baseName("/root/project/")).toBe("project");
    expect(pathSegments("/root/project").map((s) => s.path)).toEqual(["/", "/root", "/root/project"]);
  });

  it("names copies like Windows Explorer", () => {
    expect(copyName("a.txt", new Set(["a.txt"]), false)).toBe("a - Copy.txt");
    expect(copyName("a.txt", new Set(["a.txt", "a - Copy.txt"]), false)).toBe("a - Copy (2).txt");
    expect(copyName("my.folder", new Set(), true)).toBe("my.folder - Copy");
  });

  it("validates typed names", () => {
    expect(isValidName("ok.txt")).toBe(true);
    expect(isValidName("  ")).toBe(false);
    expect(isValidName("..")).toBe(false);
    expect(isValidName("a/b")).toBe(false);
  });

  it("classifies and formats files", () => {
    expect(isTextLike("Dockerfile")).toBe(true);
    expect(isTextLike(".bashrc")).toBe(true);
    expect(isTextLike("photo.png")).toBe(false);
    expect(fileKind({ name: "a.zip", type: "file" })).toBe("archive");
    expect(fileKind({ name: "a", type: "dir" })).toBe("folder");
    expect(formatSize(null)).toBe("");
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(1536)).toBe("1.5 KB");
  });
});

describe("sortEntries", () => {
  it("keeps folders first in both directions and sorts names naturally", () => {
    const items = [entry("file10.txt", "file"), entry("zeta", "dir"), entry("file2.txt", "file"), entry("alpha", "dir")];
    expect(sortEntries(items, "name", true).map((e) => e.name)).toEqual(["alpha", "zeta", "file2.txt", "file10.txt"]);
    expect(sortEntries(items, "name", false).map((e) => e.name)).toEqual(["zeta", "alpha", "file10.txt", "file2.txt"]);
  });

  it("sorts by size", () => {
    const items = [entry("big", "file", { size: 10 }), entry("small", "file", { size: 1 })];
    expect(sortEntries(items, "size", true).map((e) => e.name)).toEqual(["small", "big"]);
  });
});

describe("topLevelNames", () => {
  it("collapses a folder upload to its root folder name", () => {
    const file = new File(["x"], "x");
    expect(
      topLevelNames([
        { file, relativePath: "site/css/app.css" },
        { file, relativePath: "site/index.html" },
        { file, relativePath: "notes.txt" },
      ])
    ).toEqual(["site", "notes.txt"]);
  });
});
