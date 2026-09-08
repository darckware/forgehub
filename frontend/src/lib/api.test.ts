import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "./api";


describe("authenticated file downloads", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    localStorage.setItem(
      "forgehub-auth",
      JSON.stringify({ state: { token: "synthetic-admin-token", user: null } }),
    );
  });

  it("POSTs JSON and returns the attachment blob and filename", async () => {
    const blob = new Blob(["package bytes"], { type: "application/zip" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(blob, {
        status: 200,
        headers: { "Content-Disposition": 'attachment; filename="nexo-package.zip"' },
      }),
    );

    const result = await apiClient.postDownload("/api/v1/workstations/abc/installation-package", {
      build_id: "build-123",
    });

    expect(result.filename).toBe("nexo-package.zip");
    expect(result.blob).toBeInstanceOf(Blob);
    expect(result.blob.size).toBe(13);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/workstations/abc/installation-package"),
      expect.objectContaining({
        method: "POST",
        headers: {
          Authorization: "Bearer synthetic-admin-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ build_id: "build-123" }),
      }),
    );
  });

  it("omits the POST body while retaining authentication", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["zip"]), { status: 200 }),
    );

    const result = await apiClient.postDownload("/api/v1/package");

    expect(result.filename).toBe("package");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ method: "POST", body: undefined }),
    );
  });

  it("projects a failed POST download as the shared API error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Build is not ready" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiClient.postDownload("/api/v1/package")).rejects.toMatchObject({
      status: 409,
      body: { detail: "Build is not ready" },
    } satisfies Partial<ApiError>);
  });
});
