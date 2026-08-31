import * as React from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Loader2, Trash2, Wrench, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "./button";

interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  closeLabel?: string;
  variant?: "destructive" | "default";
  icon?: "trash" | "warning" | "wrench";
  loading?: boolean;
  confirmDisabled?: boolean;
  dismissDisabled?: boolean;
  error?: string | null;
  children?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  closeLabel,
  variant = "destructive",
  icon,
  loading = false,
  confirmDisabled = false,
  dismissDisabled = false,
  error,
  children,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation("common");
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const openerRef = React.useRef<HTMLElement | null>(null);
  const titleId = React.useId();
  const descriptionId = React.useId();

  title ??= t("confirmDialog.defaultTitle");
  confirmLabel ??= t("confirmDialog.defaultConfirm");
  cancelLabel ??= t("cancel");
  icon ??= variant === "destructive" ? "trash" : "warning";

  React.useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialogElement = dialogRef.current;
    const backgroundElements = Array.from(document.body.children).filter(
      (element) => element !== dialogElement,
    );
    const inertState = backgroundElements.map((element) => ({
      element,
      wasInert: element.hasAttribute("inert"),
    }));
    const previousOverflow = document.body.style.overflow;

    backgroundElements.forEach((element) => element.setAttribute("inert", ""));
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();

    return () => {
      inertState.forEach(({ element, wasInert }) => {
        if (!wasInert) element.removeAttribute("inert");
      });
      document.body.style.overflow = previousOverflow;
      openerRef.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  const dismiss = () => {
    if (!dismissDisabled) onCancel();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      dismiss();
      return;
    }
    if (event.key !== "Tab") return;

    const controls = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (controls.length === 0) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      aria-busy={loading || undefined}
      onKeyDown={onKeyDown}
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        aria-hidden="true"
        onMouseDown={dismiss}
      />

      <div
        className={cn(
          "relative z-10 max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card shadow-2xl",
          "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-95 motion-safe:duration-150",
        )}
      >
        <div className={cn("h-1 w-full rounded-t-xl", variant === "destructive" ? "bg-destructive/80" : "bg-amber-500/80")} />

        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
              variant === "destructive" ? "bg-destructive/10" : "bg-amber-500/10",
            )}>
              {icon === "trash" ? (
                <Trash2 className="h-5 w-5 text-destructive" aria-hidden="true" />
              ) : icon === "wrench" ? (
                <Wrench className="h-5 w-5 text-amber-500" aria-hidden="true" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-amber-500" aria-hidden="true" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="text-base font-semibold leading-tight">
                {title}
              </h2>
              {description && (
                <p id={descriptionId} className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {description}
                </p>
              )}
            </div>
            {closeLabel && (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-8 w-8 shrink-0 cursor-pointer"
                aria-label={closeLabel}
                onClick={dismiss}
                disabled={dismissDisabled}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
          </div>

          {children && <div className="mt-4">{children}</div>}

          {error && (
            <p role="alert" className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="mt-6 flex justify-end gap-3">
            <Button
              ref={cancelRef}
              type="button"
              variant="outline"
              onClick={dismiss}
              disabled={dismissDisabled}
              className="min-w-[88px] cursor-pointer"
            >
              {cancelLabel}
            </Button>
            <Button
              type="button"
              variant={variant}
              onClick={onConfirm}
              disabled={loading || confirmDisabled}
              aria-busy={loading}
              className="min-w-[88px] cursor-pointer"
            >
              {loading && <Loader2 className="mr-1.5 h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
