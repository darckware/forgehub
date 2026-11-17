import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { NewVersionBanner } from "@/components/layout/NewVersionBanner";
import { useNewVersionViewModel } from "@/hooks/useNewVersionViewModel";
import { requestVersionCheck } from "@/lib/appVersion";

describe("NewVersionBanner (MSG-052)", () => {
  it("stays hidden until a new version is found", () => {
    render(<NewVersionBanner viewModel={{ status: "idle", reload: vi.fn() }} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("asks for a reload and reloads only on click", async () => {
    const reload = vi.fn();
    render(<NewVersionBanner viewModel={{ status: "available", reload }} />);
    expect(screen.getByRole("status")).toHaveTextContent(/nova versão|new version|nueva versión/i);
    fireEvent.click(screen.getByRole("button"));
    expect(reload).toHaveBeenCalledOnce();
  });

  it("checks right away when a schema error asks for it", async () => {
    const check = vi.fn().mockResolvedValue(true);
    const { result } = renderHook(() => useNewVersionViewModel(check));
    expect(result.current.status).toBe("idle");
    act(() => requestVersionCheck());
    await waitFor(() => expect(result.current.status).toBe("available"));
    expect(check).toHaveBeenCalledOnce();
  });
});
