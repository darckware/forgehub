import { apiClient } from "@/lib/api";

export const ASSISTANT_FILE_DRAG_MIME = "application/x-forgehub-assistant-file";

export type AssistantFileDragPayload =
  | { source: "foundation-docs"; path: string; name: string }
  | { source: "vault"; path: string; name: string }
  | { source: "docs"; areaId: string; path: string; name: string }
  | { source: "host-folder"; path: string; name: string };

export function setAssistantFileDragData(
  dataTransfer: DataTransfer,
  payload: AssistantFileDragPayload
): void {
  dataTransfer.setData(ASSISTANT_FILE_DRAG_MIME, JSON.stringify(payload));
  // Keeps the drag useful outside the assistant, where a plain path is the
  // most portable representation browsers expose.
  dataTransfer.setData("text/plain", payload.path);
}

export function getAssistantFileDragData(
  dataTransfer: Pick<DataTransfer, "getData">
): AssistantFileDragPayload | null {
  const raw = dataTransfer.getData(ASSISTANT_FILE_DRAG_MIME);
  if (!raw) return null;

  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const payload = value as Record<string, unknown>;
    if (typeof payload.path !== "string" || typeof payload.name !== "string") return null;
    if (payload.source === "foundation-docs") {
      return { source: payload.source, path: payload.path, name: payload.name };
    }
    if (payload.source === "vault") {
      return { source: payload.source, path: payload.path, name: payload.name };
    }
    if (payload.source === "host-folder") {
      return { source: payload.source, path: payload.path, name: payload.name };
    }
    if (payload.source === "docs" && typeof payload.areaId === "string") {
      return {
        source: payload.source,
        areaId: payload.areaId,
        path: payload.path,
        name: payload.name,
      };
    }
  } catch {
    // Ignore malformed drag data from other browser contexts.
  }
  return null;
}

export async function loadAssistantDraggedFile(
  payload: Exclude<AssistantFileDragPayload, { source: "host-folder" }>
): Promise<File> {
  if (payload.source === "foundation-docs") {
    const doc = await apiClient.get<{ path: string; content: string }>("/api/v1/foundation-docs/doc", {
      params: { path: payload.path },
    });
    return new File([doc.content], payload.name, { type: "text/markdown" });
  }

  if (payload.source === "vault") {
    const note = await apiClient.get<{ path: string; content: string }>("/api/v1/vault/note", {
      params: { path: payload.path },
    });
    return new File([note.content], payload.name, { type: "text/markdown" });
  }

  const query = new URLSearchParams({ area_id: payload.areaId, path: payload.path });
  const { blob, filename } = await apiClient.downloadFile(`/api/v1/docs/download?${query.toString()}`);
  return new File([blob], filename || payload.name, {
    type: blob.type || "application/octet-stream",
  });
}
