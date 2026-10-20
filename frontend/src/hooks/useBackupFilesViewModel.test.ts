import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { BackupFiles } from "./useSystemControl";

const mutateAsync = vi.fn();
const data: BackupFiles = {
  total_count: 3,
  total_size: 1_617,
  reclaimable_size: 417,
  groups: [
    {
      group: "archives", label: "Backup archives", count: 1, total_size: 356,
      items: [{ path: "/root/backup/old", group: "archives", size: 356, mtime: "", is_dir: true, protected: null }],
    },
    {
      group: "hermes_weekly", label: "Hermes weekly", count: 2, total_size: 1_261,
      items: [
        { path: "/w/W39", group: "hermes_weekly", size: 1_200, mtime: "", is_dir: false, protected: "current" },
        { path: "/w/W38", group: "hermes_weekly", size: 61, mtime: "", is_dir: false, protected: null },
      ],
    },
  ],
};

vi.mock("./useSystemControl", () => ({
  useBackupFiles: () => ({ data, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() }),
  useDeleteBackupFiles: () => ({ mutateAsync, isPending: false }),
}));

const { useBackupFilesViewModel } = await import("./useBackupFilesViewModel");

describe("useBackupFilesViewModel", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
  });

  it("selecting a group never selects its protected items", () => {
    const { result } = renderHook(() => useBackupFilesViewModel());
    act(() => result.current.toggleGroup(data.groups[1]));
    expect([...result.current.selected]).toEqual(["/w/W38"]);
    expect(result.current.selectedSize).toBe(61);
    expect(result.current.isGroupSelected(data.groups[1])).toBe(true);
  });

  it("asks for confirmation, then moves the selection and clears it", async () => {
    mutateAsync.mockResolvedValue({ count: 1, total_size: 356, trash_path: "/root/trash/x" });
    const { result } = renderHook(() => useBackupFilesViewModel());
    act(() => result.current.toggleItem("/root/backup/old"));
    act(() => result.current.requestDelete());
    expect(result.current.status).toBe("confirming");
    expect(mutateAsync).not.toHaveBeenCalled();
    await act(() => result.current.confirmDelete());
    expect(mutateAsync).toHaveBeenCalledWith(["/root/backup/old"]);
    expect(result.current.status).toBe("success");
    expect(result.current.selected.size).toBe(0);
  });

  it("does nothing when nothing is selected", () => {
    const { result } = renderHook(() => useBackupFilesViewModel());
    act(() => result.current.requestDelete());
    expect(result.current.status).toBe("ready");
  });
});
