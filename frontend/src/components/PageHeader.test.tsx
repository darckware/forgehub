import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders title, description and actions", () => {
    render(<PageHeader title="Produtos" description="Todos os produtos" actions={<button>Novo</button>} />);
    expect(screen.getByRole("heading", { level: 1, name: "Produtos" })).toBeInTheDocument();
    expect(screen.getByText("Todos os produtos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Novo" })).toBeInTheDocument();
  });

  it("stacks below sm and lets the actions wrap, so no button runs off a phone screen", () => {
    const { container } = render(<PageHeader title="X" actions={<button>A</button>} />);
    const row = container.firstElementChild as HTMLElement;
    expect(row.className).toContain("flex-col");
    expect(row.className).toContain("sm:flex-row");
    expect(screen.getByRole("button", { name: "A" }).parentElement?.className).toContain("flex-wrap");
  });

  it("omits the actions container when there are no actions", () => {
    const { container } = render(<PageHeader title="X" />);
    expect(container.querySelectorAll(".flex-wrap")).toHaveLength(0);
  });
});
