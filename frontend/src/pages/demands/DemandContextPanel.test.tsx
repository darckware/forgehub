import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import "@/i18n";
import type { Demand } from "@/hooks/useDemands";
import { DemandContextPanel } from "./DemandContextPanel";

it("navigates between a failed attempt and its diagnostic without losing the source", () => {
  const source = { id: "original", number: 42, status: "archived", failure_check_source_id: null } as Demand;
  const check = { id: "check", number: 43, failure_check_source_id: "original" } as Demand;
  const onOpen = vi.fn();
  const view = render(<MemoryRouter><DemandContextPanel demand={source} demands={[source, check]} onOpen={onOpen} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Ver checagem #43" }));
  expect(onOpen).toHaveBeenCalledWith(check);
  view.rerender(<MemoryRouter><DemandContextPanel demand={check} demands={[source, check]} onOpen={onOpen} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Ver tentativa original #42" }));
  expect(onOpen).toHaveBeenCalledWith(source);
});
