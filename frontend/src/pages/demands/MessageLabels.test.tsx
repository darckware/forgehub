import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it } from "vitest";
import i18n from "@/i18n";
import type { Demand } from "@/hooks/useDemands";
import { MessageLabels } from "./MessageLabels";

beforeEach(async () => { await i18n.changeLanguage("pt-BR"); });
function show(reset: string | null, detail = false) {
  const demand = { dispatch_status: "waiting_quota", message_labels: ["awaiting_executor", "quota_unavailable"], execution_wait_reason: "quota", execution_wait_until: reset } as Demand;
  return render(<MemoryRouter><MessageLabels demand={demand} detail={detail} /></MemoryRouter>);
}
it("shows quota reset date with timezone in compact list rows", () => {
  show("2026-11-15T18:00:00Z");
  expect(screen.getByText("Aguardando reset da cota")).toBeInTheDocument();
  expect(screen.getByText(/Reset da cota:.*15\/11\/2026/)).toBeInTheDocument();
  expect(screen.queryByText(/Horário não informado/)).not.toBeInTheDocument();
});
it.each([false, true])("makes unknown reset explicit, detail=%s", detail => {
  show(null, detail);
  expect(screen.getByText("Horário não informado pelo provedor")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("does not present invalid reset metadata as a date or invent a reset", () => {
  show("invalid");
  expect(screen.getByText("Horário não informado pelo provedor")).toBeInTheDocument();
});
it("identifies the executor separately from the sender", () => {
  render(<MemoryRouter><MessageLabels demand={{ dispatch_status: "waiting_quota", from_agent: "Athos", message_labels: [] } as unknown as Demand} executorName="Aramis" /></MemoryRouter>);
  expect(screen.getByText("Executor: Aramis")).toBeInTheDocument();
});
