/**
 * A small accessible actions menu (2026-11-11, Remote Access "Ações"): a
 * trigger button that opens a list of commands. No dependency -- the codebase
 * has no Radix dropdown, and the hand-rolled "..." menus (ChatItemMenu) are
 * neither keyboard-navigable nor safe inside a scrolling table.
 *
 * Behavior: the trigger carries `aria-haspopup="menu"` and `aria-expanded`;
 * the list is `role="menu"` with `role="menuitem"` entries. Opening (click,
 * Enter, Space, ArrowDown) focuses the first enabled item; ArrowUp/ArrowDown
 * cycle, Home/End jump, Esc closes and gives focus back to the trigger, Tab
 * closes, a click outside closes. Choosing an item puts focus back on the
 * trigger *before* running it, so a side panel opened by the item returns
 * focus there when it closes.
 *
 * The list is portaled to `document.body` with fixed positioning, so a menu
 * in a table row isn't clipped by the table's `overflow-x-auto` box. It is
 * right-aligned to the trigger, never wider than the viewport minus a gutter
 * (fits a 390 px phone), opens upwards when there's no room below, and
 * scrolls when taller than the space it has. Width is min(256 px, viewport -
 * 16 px) and the left edge is clamped so neither side leaves the screen.
 */
import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

export interface ActionMenuItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  /** Draws a separator line above this item. */
  separatorBefore?: boolean;
}

export interface ActionMenuProps {
  /** Accessible name of the trigger (and of the menu). */
  label: string;
  items: ActionMenuItem[];
  /** What the trigger shows; defaults to the label. */
  children?: React.ReactNode;
  /** Classes for the trigger button. */
  triggerClassName?: string;
  /** Shown as the trigger's tooltip (icon-only triggers). */
  title?: string;
  disabled?: boolean;
}

const GUTTER = 8;
const MAX_HEIGHT = 360;
const MENU_WIDTH = 256;

interface Position {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
}

/** Below the trigger (above when there's no room), right edge on the trigger's
 * right edge, but both edges kept at least GUTTER px inside the viewport. */
export function menuPlacement(rect: DOMRect | { top: number; bottom: number; right: number }, vw: number, vh: number): Position {
  const width = Math.max(0, Math.min(MENU_WIDTH, vw - 2 * GUTTER));
  const left = Math.min(Math.max(rect.right - width, GUTTER), Math.max(GUTTER, vw - width - GUTTER));
  const below = vh - rect.bottom - GUTTER;
  const above = rect.top - GUTTER;
  if (below < Math.min(MAX_HEIGHT, 200) && above > below) {
    return { bottom: vh - rect.top + 4, left, width, maxHeight: Math.min(MAX_HEIGHT, Math.max(120, above - 4)) };
  }
  return { top: rect.bottom + 4, left, width, maxHeight: Math.min(MAX_HEIGHT, Math.max(120, below - 4)) };
}

function placement(trigger: HTMLElement): Position {
  return menuPlacement(trigger.getBoundingClientRect(), window.innerWidth || 0, window.innerHeight || 0);
}

export function ActionMenu({ label, items, children, triggerClassName, title, disabled }: ActionMenuProps) {
  const [open, setOpen] = React.useState(false);
  const [position, setPosition] = React.useState<Position | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const menuId = React.useId();

  const enabledItems = () =>
    Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])') ?? []);

  const close = React.useCallback((focusTrigger: boolean) => {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }, []);

  const show = () => {
    if (disabled || !triggerRef.current) return;
    setPosition(placement(triggerRef.current));
    setOpen(true);
  };

  // Focus the first enabled item once the list is in the DOM.
  React.useEffect(() => {
    if (open) enabledItems()[0]?.focus();
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      close(false);
    };
    // A scroll of the page moves the trigger away from the fixed list.
    const onScroll = (event: Event) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      close(false);
    };
    const onResize = () => close(false);
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open, close]);

  const onMenuKeyDown = (event: React.KeyboardEvent) => {
    const list = enabledItems();
    const index = list.indexOf(document.activeElement as HTMLButtonElement);
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        list[(index + 1) % list.length]?.focus();
        break;
      case "ArrowUp":
        event.preventDefault();
        list[(index - 1 + list.length) % list.length]?.focus();
        break;
      case "Home":
        event.preventDefault();
        list[0]?.focus();
        break;
      case "End":
        event.preventDefault();
        list[list.length - 1]?.focus();
        break;
      case "Escape":
        // Handled here: nothing behind the menu (a panel, a dialog) reacts.
        event.preventDefault();
        event.stopPropagation();
        event.nativeEvent.stopImmediatePropagation?.();
        close(true);
        break;
      case "Tab":
        // Back on the trigger first, so Tab moves on from there.
        close(true);
        break;
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={children ? undefined : label}
        title={title}
        disabled={disabled}
        onClick={() => (open ? close(false) : show())}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            show();
          }
        }}
        className={cn(
          "inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
          triggerClassName,
        )}
      >
        {children ?? label}
      </button>
      {open && position && createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          style={{ top: position.top, bottom: position.bottom, left: position.left, width: position.width, maxHeight: position.maxHeight }}
          className="fixed z-50 overflow-y-auto rounded-md border border-border bg-card py-1 text-card-foreground shadow-lg"
        >
          {items.map((item) => (
            <React.Fragment key={item.key}>
              {item.separatorBefore && <div role="separator" className="my-1 h-px bg-border" />}
              <button
                type="button"
                role="menuitem"
                tabIndex={-1}
                disabled={item.disabled}
                onClick={() => {
                  close(true);
                  item.onSelect();
                }}
                className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                {item.icon && <span className="shrink-0 text-muted-foreground" aria-hidden="true">{item.icon}</span>}
                <span className="min-w-0 break-words">{item.label}</span>
              </button>
            </React.Fragment>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
