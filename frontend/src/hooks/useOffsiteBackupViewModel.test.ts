import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { ApiError } from "@/lib/api";
import type { OffsiteBackupOverview, OffsiteBackupTarget } from "./useOffsiteBackup";

const save = vi.fn();
const remove = vi.fn();
const run = vi.fn();
const cancel = vi.fn();

function target(overrides: Partial<OffsiteBackupTarget> = {}): OffsiteBackupTarget {
  return {
    id: "t1", name: "forgehub", label: "ForgeHub", paths: ["/root/project/forgehub"], excludes: [],
    postgres_container: "forgehub_postgres", include_system_state: false, enabled: true, sort_order: 20,
    last_run: null, last_success: null, ...overrides,
  };
}

const data: OffsiteBackupOverview = {
  repository: "rclone:gdrive:vps-backup/restic",
  script: "/root/.hermes/profiles/athos/scripts/backup_offsite_projects.sh",
  schedule: null,
  schedule_error: "not_scheduled",
  running: false,
  queued: 0,
  repository_maintenance: null,
  targets: [target(), target({ id: "t2", name: "nexo", label: "Nexo", enabled: false, sort_order: 110 })],
};

vi.mock("./useOffsiteBackup", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./useOffsiteBackup")>()),
  useOffsiteBackupOverview: () => ({ data, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() }),
  useSaveOffsiteTarget: () => ({ mutateAsync: save, isPending: false }),
  useDeleteOffsiteTarget: () => ({ mutateAsync: remove, isPending: false }),
  useRunOffsiteBackup: () => ({ mutateAsync: run, isPending: false }),
  useCancelQueuedRun: () => ({ mutateAsync: cancel, isPending: false }),
}));

const { useOffsiteBackupViewModel, toOffsiteError } = await import("./useOffsiteBackupViewModel");
const { offsiteTargetFormSchema, slugifyTargetName, toOffsiteTargetPayload } = await import("./useOffsiteBackup");

describe("useOffsiteBackupViewModel", () => {
  beforeEach(() => {
    save.mockReset();
    remove.mockReset();
    run.mockReset();
    cancel.mockReset();
  });

  it("creates a target from the form, one path per line, placed after the last one", async () => {
    save.mockResolvedValue(target());
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    act(() => result.current.openCreate());
    await act(() =>
      result.current.submit({
        label: "Meu Projeto", name: "meu-projeto", paths: " /root/project/a \n\n/root/project/b", excludes: "*.log\n",
        postgres_container: "", include_system_state: false, enabled: true,
      }),
    );
    expect(save).toHaveBeenCalledWith({
      id: undefined,
      payload: {
        name: "meu-projeto", label: "Meu Projeto", paths: ["/root/project/a", "/root/project/b"], excludes: ["*.log"],
        postgres_container: null, include_system_state: false, enabled: true, sort_order: 120,
      },
    });
    expect(result.current.dialog).toBeNull();
  });

  it("keeps the form open with the missing folders the server named", async () => {
    save.mockRejectedValue(
      new ApiError("x", 400, { detail: { message: "These paths don't exist on the host", missing: ["/root/nope"] } }),
    );
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    act(() => result.current.openEdit(data.targets[0]));
    await act(() =>
      result.current.submit({
        label: "ForgeHub", name: "forgehub", paths: "/root/nope", excludes: "", postgres_container: "",
        include_system_state: false, enabled: true,
      }),
    );
    expect(save.mock.calls[0][0].id).toBe("t1");
    expect(result.current.dialog?.mode).toBe("edit");
    expect(result.current.formError).toEqual({ code: "missing", detail: "/root/nope" });
  });

  it("deletes only after confirmation", async () => {
    remove.mockResolvedValue(undefined);
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    act(() => result.current.requestDelete(data.targets[0]));
    expect(remove).not.toHaveBeenCalled();
    await act(() => result.current.confirmDelete());
    expect(remove).toHaveBeenCalledWith("t1");
    expect(result.current.deleting).toBeNull();
  });

  it("queues everything, the selection in list order, or one target", async () => {
    run.mockResolvedValue({ queued: ["forgehub"], skipped: [], worker_already_running: false });
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    await act(() => result.current.runTarget(data.targets[0]));
    expect(run).toHaveBeenLastCalledWith(["forgehub"]);
    expect(result.current.queueResult?.queued).toEqual(["forgehub"]);

    await act(() => result.current.runAll());
    expect(run).toHaveBeenLastCalledWith([]);

    // The disabled target can't be selected; "select all" means the enabled ones.
    act(() => result.current.toggleSelected(data.targets[1]));
    expect(result.current.selected.size).toBe(0);
    act(() => result.current.toggleSelectAll());
    expect([...result.current.selected]).toEqual(["forgehub"]);
    await act(() => result.current.runSelected());
    expect(run).toHaveBeenLastCalledWith(["forgehub"]);
    expect(result.current.selected.size).toBe(0);
  });

  it("takes a queued run out of the queue, and only a queued one", async () => {
    const queued = target({ last_run: { id: "r1", status: "queued" } as never });
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    expect(result.current.isInQueue(queued)).toBe(true);
    await act(() => result.current.cancelQueued(queued));
    expect(cancel).toHaveBeenCalledWith("r1");

    await act(() => result.current.cancelQueued(target({ last_run: { id: "r2", status: "running" } as never })));
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("shows a failed request without losing the card", async () => {
    run.mockRejectedValueOnce(new ApiError("x", 500, { detail: "Could not start the backup" }));
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    await act(() => result.current.runAll());
    expect(result.current.actionError).toEqual({ code: "generic", detail: "Could not start the backup" });
    expect(result.current.status).toBe("error");
  });

  it("flags enabled targets without a recent successful backup", () => {
    const { result } = renderHook(() => useOffsiteBackupViewModel());
    const recent = { ...data.targets[0].last_run, finished_at: new Date().toISOString() } as never;
    expect(result.current.isStale(data.targets[0])).toBe(true);
    expect(result.current.isStale(target({ last_success: recent }))).toBe(false);
    expect(result.current.isStale(data.targets[1])).toBe(false);
    expect(result.current.enabledCount).toBe(1);
  });
});

describe("off-site backup form", () => {
  it("accepts absolute paths only, never the root", () => {
    const base = { label: "X", name: "x", excludes: "", postgres_container: "", include_system_state: false, enabled: true };
    expect(offsiteTargetFormSchema.safeParse({ ...base, paths: "/root/a\n/etc" }).success).toBe(true);
    expect(offsiteTargetFormSchema.safeParse({ ...base, paths: "root/a" }).success).toBe(false);
    expect(offsiteTargetFormSchema.safeParse({ ...base, paths: "/" }).success).toBe(false);
    expect(offsiteTargetFormSchema.safeParse({ ...base, paths: "  \n" }).success).toBe(false);
    expect(offsiteTargetFormSchema.safeParse({ ...base, name: "Com Espaço", paths: "/a" }).success).toBe(false);
  });

  it("suggests the identifier from the name", () => {
    expect(slugifyTargetName("Integração São Paulo 2")).toBe("integracao-sao-paulo-2");
    expect(toOffsiteTargetPayload({
      label: " A ", name: "a", paths: "/x", excludes: "", postgres_container: "pg", include_system_state: true, enabled: false,
    })).toMatchObject({ label: "A", postgres_container: "pg", include_system_state: true, enabled: false });
  });

  it("maps server errors to messages", () => {
    expect(toOffsiteError(new ApiError("x", 409, { detail: "A target with this identifier already exists" })).code).toBe("duplicate");
    expect(toOffsiteError(new ApiError("x", 409, { detail: "Only a queued run can be cancelled" })).code).toBe("notQueued");
    expect(toOffsiteError(new ApiError("x", 422, { detail: [{ msg: "Value error, bad" }] }))).toEqual({
      code: "generic", detail: "Value error, bad",
    });
  });
});
