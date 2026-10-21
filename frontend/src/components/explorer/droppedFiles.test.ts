import { describe, expect, it } from "vitest";
import {
  summarizeUpload,
  uploadBlock,
  withoutHeavyDirs,
  UPLOAD_MAX_FILE_BYTES,
  UPLOAD_MAX_FILES,
  type PendingUpload,
} from "./droppedFiles";

function upload(relativePath: string, size = 10): PendingUpload {
  const file = new File(["x"], relativePath.split("/").pop()!);
  Object.defineProperty(file, "size", { value: size });
  return { file, relativePath };
}

describe("upload review", () => {
  it("counts files, nested folders and bytes", () => {
    const summary = summarizeUpload([upload("site/a.txt", 5), upload("site/css/b.css", 7), upload("c.txt", 1)]);
    expect(summary).toMatchObject({ files: 3, folders: 2, bytes: 13, heavyDirs: [], oversized: [] });
  });

  it("groups generated folders under their outermost heavy dir and can drop them", () => {
    const uploads = [
      upload("app/main.py"),
      upload("app/node_modules/x/index.js"),
      upload("app/node_modules/x/node_modules/y.js"),
      upload("app/__pycache__/main.pyc"),
    ];
    const summary = summarizeUpload(uploads);
    expect(summary.heavyDirs.map((d) => [d.path, d.files])).toEqual([
      ["app/node_modules", 2],
      ["app/__pycache__", 1],
    ]);
    expect(withoutHeavyDirs(uploads).map((u) => u.relativePath)).toEqual(["app/main.py"]);
  });

  it("leaves oversized files out instead of blocking the batch", () => {
    const summary = summarizeUpload([upload("big.iso", UPLOAD_MAX_FILE_BYTES + 1), upload("ok.txt")]);
    expect(summary.oversized.map((u) => u.relativePath)).toEqual(["big.iso"]);
    expect(uploadBlock(summary)).toBeNull();
    expect(uploadBlock(summarizeUpload([upload("big.iso", UPLOAD_MAX_FILE_BYTES + 1)]))).toBe("empty");
  });

  it("blocks a batch over the file limit", () => {
    const many = Array.from({ length: UPLOAD_MAX_FILES + 1 }, (_, i) => upload(`f/${i}.txt`));
    expect(uploadBlock(summarizeUpload(many))).toBe("tooManyFiles");
    expect(uploadBlock(summarizeUpload(many.slice(1)))).toBeNull();
  });
});
