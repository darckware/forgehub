import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DockerUsage } from "@/hooks/useSystemControl";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, string>) => (vars ? `${key} ${JSON.stringify(vars)}` : key),
  }),
}));

let isAdmin = true;
vi.mock("@/store/authStore", () => ({
  useAuthStore: (select: (s: { user: { is_admin: boolean } }) => unknown) => select({ user: { is_admin: isAdmin } }),
}));

const GB = 1000 ** 3;
const stats = {
  memory: { total_bytes: 16 * GB, used_bytes: 8 * GB, available_bytes: 8 * GB, percent_used: 50 },
  disk: { total_bytes: 200 * GB, used_bytes: 164 * GB, free_bytes: 36 * GB, percent_used: 82 },
  network: { interface: "eth0", rx_bytes: 0, tx_bytes: 0 },
};
vi.mock("@/hooks/useSystemStats", () => ({
  useSystemStats: () => ({ data: stats, isLoading: false, isError: false }),
}));

let docker: DockerUsage | undefined;
const useDockerUsage = vi.fn();
vi.mock("@/hooks/useSystemControl", () => ({
  useDockerUsage: (options: unknown) => {
    useDockerUsage(options);
    return { data: docker };
  },
}));

const { SystemStatsCard } = await import("./SystemStatsCard");

function usage(buildCacheReclaimable: number): DockerUsage {
  return {
    disk: null,
    types: [
      { type: "Images", total_count: 1, active: 1, size: 24 * GB, reclaimable: 0 },
      { type: "Build Cache", total_count: 1, active: 0, size: 92 * GB, reclaimable: buildCacheReclaimable },
    ],
    unused_images: [],
  };
}

function renderCard() {
  return render(
    <MemoryRouter>
      <SystemStatsCard />
    </MemoryRouter>
  );
}

describe("SystemStatsCard Docker row", () => {
  beforeEach(() => {
    isAdmin = true;
    useDockerUsage.mockClear();
  });

  it("warns and links to System Control when a lot of Docker space is reclaimable", () => {
    docker = usage(88 * GB);
    renderCard();
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/system-control");
    expect(link.textContent).toContain("systemStats.dockerReclaimableWarning");
  });

  it("shows a plain note, no warning, when little is reclaimable and the disk isn't full", () => {
    stats.disk.percent_used = 40;
    docker = usage(1 * GB);
    renderCard();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/systemStats\.dockerReclaimable /)).toBeInTheDocument();
    stats.disk.percent_used = 82;
  });

  it("doesn't query Docker for a non-admin (the endpoint is admin-only)", () => {
    isAdmin = false;
    docker = undefined;
    renderCard();
    expect(useDockerUsage).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
    expect(screen.queryByText("systemStats.docker")).toBeNull();
  });
});
