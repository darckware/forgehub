import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionMenu, menuPlacement } from "./action-menu";

const rect = (left: number, right: number, top = 100, bottom = 132) =>
  ({ left, right, top, bottom, width: right - left, height: bottom - top, x: left, y: top, toJSON: () => ({}) }) as DOMRect;

describe("menuPlacement", () => {
  it("right-aligns to the trigger on a wide screen", () => {
    expect(menuPlacement(rect(1300, 1340), 1440, 900)).toMatchObject({ left: 1340 - 256, width: 256, top: 136 });
  });

  it("never lets the left edge leave a 390 px phone (trigger near the left)", () => {
    const p = menuPlacement(rect(16, 56), 390, 844);
    expect(p.left).toBe(8);
    expect(p.left + p.width).toBeLessThanOrEqual(390 - 8);
  });

  it("never lets the right edge leave the screen (trigger near the right)", () => {
    const p = menuPlacement(rect(350, 400), 390, 844);
    expect(p.left + p.width).toBeLessThanOrEqual(390 - 8);
    expect(p.left).toBeGreaterThanOrEqual(8);
  });

  it("shrinks below 256 px on a very narrow screen, keeping both gutters", () => {
    expect(menuPlacement(rect(100, 140), 240, 600)).toMatchObject({ left: 8, width: 224 });
  });

  it("opens upwards when there is no room below", () => {
    const p = menuPlacement(rect(300, 340, 780, 812), 390, 844);
    expect(p.top).toBeUndefined();
    expect(p.bottom).toBe(844 - 780 + 4);
  });
});

describe("ActionMenu", () => {
  const width = window.innerWidth;
  afterEach(() => { window.innerWidth = width; vi.restoreAllMocks(); });

  it("positions the list inside a 390 px viewport", () => {
    window.innerWidth = 390;
    render(<ActionMenu label="Ações" items={[{ key: "a", label: "Um", onSelect: vi.fn() }]} />);
    const trigger = screen.getByRole("button", { name: "Ações" });
    vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue(rect(12, 60));
    fireEvent.click(trigger);
    const menu = screen.getByRole("menu");
    expect(menu.style.left).toBe("8px");
    expect(menu.style.width).toBe("256px");
  });

  it("Tab closes the menu and puts focus back on the trigger", () => {
    render(<ActionMenu label="Ações" items={[{ key: "a", label: "Um", onSelect: vi.fn() }, { key: "b", label: "Dois", onSelect: vi.fn() }]} />);
    const trigger = screen.getByRole("button", { name: "Ações" });
    fireEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: "Um" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Tab" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("skips disabled items with the arrows", () => {
    render(<ActionMenu label="Ações" items={[
      { key: "a", label: "Um", onSelect: vi.fn() }, { key: "b", label: "Dois", disabled: true, onSelect: vi.fn() },
      { key: "c", label: "Três", onSelect: vi.fn() },
    ]} />);
    fireEvent.click(screen.getByRole("button", { name: "Ações" }));
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(screen.getByRole("menuitem", { name: "Três" })).toHaveFocus();
  });
});
