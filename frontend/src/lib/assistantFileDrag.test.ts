import { describe, expect, it } from "vitest";
import { ASSISTANT_FILE_DRAG_MIME, getAssistantFileDragData } from "@/lib/assistantFileDrag";

function dragData(values: Record<string, string>) {
  return { getData: (type: string) => values[type] ?? "" };
}

describe("getAssistantFileDragData", () => {
  it("parses a Foundation document payload", () => {
    const payload = { source: "foundation-docs", path: "docs/MANUAL.md", name: "MANUAL.md" };

    expect(
      getAssistantFileDragData(dragData({ [ASSISTANT_FILE_DRAG_MIME]: JSON.stringify(payload) }))
    ).toEqual(payload);
  });

  it("parses a Docs area payload", () => {
    const payload = { source: "docs", areaId: "area-1", path: "notes/plan.md", name: "plan.md" };

    expect(
      getAssistantFileDragData(dragData({ [ASSISTANT_FILE_DRAG_MIME]: JSON.stringify(payload) }))
    ).toEqual(payload);
  });

  it("parses a Knowledge Base note payload", () => {
    const payload = { source: "vault", path: "athos/README.md", name: "README.md" };

    expect(
      getAssistantFileDragData(dragData({ [ASSISTANT_FILE_DRAG_MIME]: JSON.stringify(payload) }))
    ).toEqual(payload);
  });

  it("parses a host folder reference", () => {
    const payload = {
      source: "host-folder",
      path: "/root/.hermes/foundation/docs",
      name: "docs",
    };

    expect(
      getAssistantFileDragData(dragData({ [ASSISTANT_FILE_DRAG_MIME]: JSON.stringify(payload) }))
    ).toEqual(payload);
  });

  it("rejects malformed or unknown payloads", () => {
    expect(getAssistantFileDragData(dragData({ [ASSISTANT_FILE_DRAG_MIME]: "not-json" }))).toBeNull();
    expect(
      getAssistantFileDragData(
        dragData({
          [ASSISTANT_FILE_DRAG_MIME]: JSON.stringify({ source: "unknown", path: "file.md", name: "file.md" }),
        })
      )
    ).toBeNull();
  });
});
