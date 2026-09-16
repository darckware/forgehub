import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import type { ClientReport } from "@/hooks/useClientReports";
import { ClientReportsPanel } from "./client-reports";

const mocks = vi.hoisted(() => ({
  useClientReports: vi.fn(),
  generateClientReport: vi.fn(),
  generateMonthlyReport: vi.fn(),
  reviewClientReport: vi.fn(),
  downloadReportFile: vi.fn(),
}));

vi.mock("@/hooks/useClientReports", () => ({
  useClientReports: (clientId: string) => mocks.useClientReports(clientId),
  useGenerateClientReport: () => ({
    mutateAsync: mocks.generateClientReport,
    isPending: false,
    error: null,
  }),
  useGenerateMonthlyReport: () => ({
    mutateAsync: mocks.generateMonthlyReport,
    isPending: false,
    error: null,
  }),
  useReviewClientReport: () => ({
    mutate: mocks.reviewClientReport,
    isPending: false,
    error: null,
  }),
  downloadReportFile: (id: string) => mocks.downloadReportFile(id),
}));

describe("ClientReportsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state", () => {
    mocks.useClientReports.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    });

    render(<ClientReportsPanel clientId="client-1" />);
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();
  });

  it("renders empty state", () => {
    mocks.useClientReports.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    });

    render(<ClientReportsPanel clientId="client-1" />);
    expect(
      screen.getByText(/nenhum relatório gerado para este cliente/i)
    ).toBeInTheDocument();
  });

  it("renders report items and triggers download and review actions", () => {
    const mockReports: ClientReport[] = [
      {
        id: "rep-1",
        client_id: "client-1",
        kind: "monthly",
        period_start: "2026-08-01",
        period_end: "2026-08-31",
        irregularity_id: null,
        generated_at: "2026-09-01T00:00:00Z",
        generated_by_user_id: null,
        reviewed_at: null,
        reviewed_by_user_id: null,
        created_at: "2026-09-01T00:00:00Z",
        updated_at: "2026-09-01T00:00:00Z",
      },
      {
        id: "rep-2",
        client_id: "client-1",
        kind: "on_demand",
        period_start: "2026-08-10",
        period_end: "2026-08-15",
        irregularity_id: "irreg-1",
        generated_at: "2026-08-16T00:00:00Z",
        generated_by_user_id: null,
        reviewed_at: "2026-08-17T00:00:00Z",
        reviewed_by_user_id: "admin-1",
        created_at: "2026-08-16T00:00:00Z",
        updated_at: "2026-08-17T00:00:00Z",
      },
    ];

    mocks.useClientReports.mockReturnValue({
      isLoading: false,
      isError: false,
      data: mockReports,
    });

    render(<ClientReportsPanel clientId="client-1" />);

    expect(screen.getByText("2026-08-01 → 2026-08-31")).toBeInTheDocument();
    expect(screen.getByText("2026-08-10 → 2026-08-15")).toBeInTheDocument();
    expect(screen.getByText(/rascunho/i)).toBeInTheDocument();
    expect(screen.getByText(/revisado/i)).toBeInTheDocument();

    const downloadButtons = screen.getAllByRole("button", { name: /baixar html/i });
    expect(downloadButtons).toHaveLength(2);
    fireEvent.click(downloadButtons[0]);
    expect(mocks.downloadReportFile).toHaveBeenCalledWith("rep-1");

    const reviewButton = screen.getByRole("button", { name: /confirmar revisão/i });
    fireEvent.click(reviewButton);
    expect(mocks.reviewClientReport).toHaveBeenCalledWith({
      reportId: "rep-1",
      reviewed: true,
    });
  });
});
