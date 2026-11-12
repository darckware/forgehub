/**
 * A right-hand side panel: forms and read-only details open beside the list
 * instead of as a centered modal (2026-11-11, Marcelo: "não quero essa tela
 * modal. O formulário precisa abrir a direita"). Extracted from the server form,
 * which became a right panel on 2026-10-18.
 *
 * Layout: full height on the right, `max-w-xl` by default, full width on a
 * phone; a light overlay (`bg-black/30`) so the list stays visible. A fixed
 * header (title, optional description, close), one scrolling body and an
 * optional fixed footer for the actions -- so the actions stay on screen no
 * matter how long the content grows.
 *
 * Behavior: `role="dialog"` + `aria-modal` + `aria-labelledby` on the title.
 * Esc and a click on the overlay close it, except while `busy` (a save in
 * flight must not be abandoned halfway). An Esc already handled by a dialog
 * inside the panel (ConfirmDialog calls preventDefault) closes only that
 * dialog. Focus moves to the first field on open and back to whatever had it
 * (normally the button that opened the panel) on close; a field that took
 * focus itself (`autoFocus`) keeps it. With several panels open, only the
 * topmost reacts to Esc. The page behind doesn't scroll while a panel is open.
 *
 * `as="form"` renders the panel itself as the `<form>`, so a footer submit
 * button submits it.
 */
import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

const SIZES = {
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
  "3xl": "max-w-3xl",
} as const;

export type SidePanelSize = keyof typeof SIZES;

/** Open panels, oldest first: only the last one reacts to Esc. */
const openPanels: symbol[] = [];

/** Body scroll lock shared by every open panel (nested-safe). */
let scrollLocks = 0;
let savedOverflow = "";
function lockBodyScroll() {
  if (scrollLocks === 0) {
    savedOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  scrollLocks += 1;
}
function unlockBodyScroll() {
  scrollLocks = Math.max(0, scrollLocks - 1);
  if (scrollLocks === 0) document.body.style.overflow = savedOverflow;
}

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';
const FIELDS = 'input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), select:not([disabled])';

export interface SidePanelProps {
  /** Defaults to true: most callers mount the panel only while it is open. */
  open?: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Shown before the title. */
  icon?: React.ReactNode;
  /** Fixed action row at the bottom (buttons, a summary line, an error). */
  footer?: React.ReactNode;
  children?: React.ReactNode;
  /** While true, Esc, the overlay and the close button do nothing. */
  busy?: boolean;
  size?: SidePanelSize;
  /** Extra classes for the panel element. */
  className?: string;
  bodyClassName?: string;
  footerClassName?: string;
  /** Accessible name of the close button; defaults to "Fechar". */
  closeLabel?: string;
  /** Render the panel as a `<form>`. */
  as?: "div" | "form";
  onSubmit?: React.FormEventHandler<HTMLFormElement>;
  noValidate?: boolean;
  /** Overrides the generated title id (kept stable for existing callers). */
  titleId?: string;
}

export function SidePanel({
  open = true,
  onClose,
  title,
  description,
  icon,
  footer,
  children,
  busy = false,
  size = "xl",
  className,
  bodyClassName,
  footerClassName,
  closeLabel,
  as = "div",
  onSubmit,
  noValidate,
  titleId: titleIdProp,
}: SidePanelProps) {
  const { t } = useTranslation("common");
  const generatedId = React.useId();
  const titleId = titleIdProp ?? `side-panel-title-${generatedId}`;
  const descriptionId = `side-panel-description-${generatedId}`;
  const panelRef = React.useRef<HTMLElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement>(null);
  // The latest values, read by the listeners without re-subscribing them.
  const busyRef = React.useRef(busy);
  busyRef.current = busy;
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;

  const dismiss = React.useCallback(() => {
    if (!busyRef.current) onCloseRef.current();
  }, []);

  // The opener is read during render: by the time effects run, a child's
  // `autoFocus` has already moved focus into the panel. Only an element
  // outside the panel counts as the opener.
  // Neither ref is cleared by the effect cleanup: React StrictMode (dev) runs
  // setup -> cleanup -> setup on mount without re-rendering, so a ref cleared
  // there would be gone for the real close. They reset here, once closed.
  const openerRef = React.useRef<HTMLElement | null>(null);
  // Where focus went inside the panel on open, so StrictMode's second setup
  // puts it back there (an autoFocus field) instead of on the first field.
  const initialFocusRef = React.useRef<HTMLElement | null>(null);
  if (!open) {
    openerRef.current = null;
    initialFocusRef.current = null;
  } else if (openerRef.current === null) {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body && !panelRef.current?.contains(active)) {
      openerRef.current = active;
    }
  }

  // Focus in on open (unless something inside already has it), back to the
  // opener on close; scroll lock and the Esc stack follow the same lifetime.
  React.useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const opener = openerRef.current;
    if (!panel?.contains(document.activeElement)) {
      const previous = initialFocusRef.current;
      const first = bodyRef.current?.querySelector<HTMLElement>(FIELDS);
      (previous && previous.isConnected && panel?.contains(previous) ? previous : first ?? panel)?.focus();
    }
    if (document.activeElement instanceof HTMLElement && panel?.contains(document.activeElement)) {
      initialFocusRef.current = document.activeElement;
    }
    const token = Symbol("side-panel");
    openPanels.push(token);
    lockBodyScroll();
    const onKey = (event: KeyboardEvent) => {
      // A dialog inside the panel handles its own Escape first (preventDefault):
      // that must close the dialog, not the panel. Only the topmost panel closes.
      if (event.key === "Escape" && !event.defaultPrevented && openPanels[openPanels.length - 1] === token) dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      const index = openPanels.indexOf(token);
      if (index >= 0) openPanels.splice(index, 1);
      unlockBodyScroll();
      if (opener && opener.isConnected) opener.focus();
    };
  }, [open, dismiss]);

  if (!open) return null;

  // Keep Tab inside the panel while it is open (aria-modal).
  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Tab" || !panelRef.current) return;
    const controls = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (controls.length === 0) return;
    const firstControl = controls[0];
    const lastControl = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === firstControl) {
      event.preventDefault();
      lastControl.focus();
    } else if (!event.shiftKey && document.activeElement === lastControl) {
      event.preventDefault();
      firstControl.focus();
    }
  };

  const panelClass = cn(
    "relative z-10 flex h-dvh max-h-dvh w-full flex-col overflow-hidden border-l border-border bg-card shadow-2xl outline-none",
    "motion-safe:animate-in motion-safe:slide-in-from-right",
    SIZES[size],
    className,
  );

  const content = (
    <>
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-6 py-4 max-md:px-4">
        <div className="min-w-0">
          <h2 id={titleId} className="flex items-center gap-2 text-base font-semibold">
            {icon}
            {title}
          </h2>
          {description && <p id={descriptionId} className="mt-1 text-xs text-muted-foreground">{description}</p>}
        </div>
        <button
          type="button"
          onClick={dismiss}
          disabled={busy}
          aria-label={closeLabel ?? t("sidePanel.close")}
          className="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div ref={bodyRef} className={cn("min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4 max-md:px-4", bodyClassName)}>
        {children}
      </div>

      {footer && (
        <div className={cn("flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-border px-6 py-4 max-md:px-4", footerClassName)}>
          {footer}
        </div>
      )}
    </>
  );

  const shared = {
    role: "dialog" as const,
    "aria-modal": true as const,
    "aria-labelledby": titleId,
    "aria-describedby": description ? descriptionId : undefined,
    "aria-busy": busy || undefined,
    tabIndex: -1,
    className: panelClass,
    onKeyDown,
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end" data-side-panel="">
      <div className="absolute inset-0 bg-black/30" aria-hidden="true" data-testid="side-panel-overlay" onClick={dismiss} />
      {as === "form" ? (
        <form
          {...shared}
          ref={(el) => { panelRef.current = el; }}
          onSubmit={onSubmit}
          noValidate={noValidate}
        >
          {content}
        </form>
      ) : (
        <div {...shared} ref={(el) => { panelRef.current = el; }}>
          {content}
        </div>
      )}
    </div>,
    document.body,
  );
}
