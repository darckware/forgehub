# ForgeHub Shared UI Primitives

ForgeHub uses React 18 with TypeScript, Tailwind CSS, `class-variance-authority`, and a small shadcn-inspired component layer in `frontend/src/components/ui/`. The catalog below contains every production primitive in that directory, deduplicated and with its full source. Page-specific and test components are intentionally excluded.

## Badge

- File: `frontend/src/components/ui/badge.tsx`
- Description: Semantic pill badge with default, secondary, destructive, outline, success, and warning variants.
- Key props: Standard `HTMLDivElement` attributes plus `variant`.

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "border-border text-foreground",
        success: "border-transparent bg-emerald-100 text-emerald-800",
        warning: "border-transparent bg-amber-100 text-amber-800",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
```

## Breadcrumb

- File: `frontend/src/components/ui/breadcrumb.tsx`
- Description: Accessible breadcrumb trail with linked ancestors and a current-page label.
- Key props: `items: { label: string; href?: string }[]`, `className?`.

```tsx
import * as React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" className={cn("flex items-center gap-1 text-sm text-muted-foreground", className)}>
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50" />}
          {item.href ? (
            <Link to={item.href} className="hover:text-foreground transition-colors">
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-foreground">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
```

## Button

- File: `frontend/src/components/ui/button.tsx`
- Description: Shared button primitive with semantic visual and size variants.
- Key props: Standard button attributes plus `variant` and `size`.

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

## Card

- File: `frontend/src/components/ui/card.tsx`
- Description: Composable bordered card surface with header, title, description, content, and footer primitives.
- Key props: Standard element attributes and refs for each exported subcomponent.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-lg border border-border bg-card text-card-foreground shadow-sm", className)}
      {...props}
    />
  )
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-2xl font-semibold leading-none tracking-tight", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
  )
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  )
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter };
```

## ConfirmDialog

- File: `frontend/src/components/ui/confirm-dialog.tsx`
- Description: Modal confirmation surface with destructive/default treatments, keyboard dismissal, loading, and inline error state.
- Key props: `open`, labels/copy overrides, `variant`, `icon`, `loading`, `error`, `onConfirm`, `onCancel`.

```tsx
import * as React from "react";
import { AlertTriangle, Loader2, Trash2, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "./button";

interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "destructive" | "default";
  icon?: "trash" | "warning" | "wrench";
  loading?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = "destructive",
  icon,
  loading = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation("common");
  title ??= t("confirmDialog.defaultTitle");
  confirmLabel ??= t("confirmDialog.defaultConfirm");
  cancelLabel ??= t("cancel");
  icon ??= variant === "destructive" ? "trash" : "warning";
  React.useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby="confirm-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Panel */}
      <div
        className={cn(
          "relative z-10 w-full max-w-md rounded-xl border border-border bg-card shadow-2xl",
          "animate-in fade-in-0 zoom-in-95 duration-150"
        )}
      >
        {/* Top accent bar */}
        <div className={cn("h-1 w-full rounded-t-xl", variant === "destructive" ? "bg-destructive/80" : "bg-amber-500/80")} />

        <div className="p-6">
          {/* Icon + title */}
          <div className="flex items-start gap-4">
            <div className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
              variant === "destructive" ? "bg-destructive/10" : "bg-amber-500/10",
            )}>
              {icon === "trash" ? (
                <Trash2 className="h-5 w-5 text-destructive" />
              ) : icon === "wrench" ? (
                <Wrench className="h-5 w-5 text-amber-500" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-amber-500" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <h2
                id="confirm-dialog-title"
                className="text-base font-semibold leading-tight"
              >
                {title}
              </h2>
              {description && (
                <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
                  {description}
                </p>
              )}
            </div>
          </div>

          {error && (
            <p role="alert" className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="mt-6 flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={onCancel}
              className="min-w-[88px]"
            >
              {cancelLabel}
            </Button>
            <Button
              variant={variant}
              onClick={onConfirm}
              disabled={loading}
              className="min-w-[88px]"
            >
              {loading && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

## Input

- File: `frontend/src/components/ui/input.tsx`
- Description: Styled text input with shared focus, placeholder, and disabled states.
- Key props: Standard `InputHTMLAttributes<HTMLInputElement>`.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
          "placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
```

## Label

- File: `frontend/src/components/ui/label.tsx`
- Description: Styled form label with peer-disabled states.
- Key props: Standard `LabelHTMLAttributes<HTMLLabelElement>`.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export type LabelProps = React.LabelHTMLAttributes<HTMLLabelElement>;

const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
        className
      )}
      {...props}
    />
  )
);
Label.displayName = "Label";

export { Label };
```

## Select

- File: `frontend/src/components/ui/select.tsx`
- Description: Native select normalized for ForgeHub dark-mode rendering with a custom chevron.
- Key props: Standard `SelectHTMLAttributes<HTMLSelectElement>` and `children`.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <select
        className={cn(
          // appearance-none takes the box out of the OS/native widget
          // rendering path entirely -- on some browser/OS combinations
          // (observed on WSL2, 2026-08-06, Marcelo: "não consigo ler o
          // texto dentro do dropdown") a native <select> paints its own
          // light-themed chrome for the closed box regardless of our
          // author background-color/color, which is exactly what made the
          // box show up as illegible white-on-white in dark mode. Explicit
          // text-foreground is a second belt-and-suspenders guard for the
          // same failure mode. The custom chevron (index.css) replaces the
          // native arrow appearance-none removes.
          "flex h-10 w-full select-chevron appearance-none rounded-md border border-input bg-background bg-no-repeat px-3 py-2 pr-8 text-sm text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      >
        {children}
      </select>
    );
  }
);
Select.displayName = "Select";

export { Select };
```

## Table

- File: `frontend/src/components/ui/table.tsx`
- Description: Responsive table composition with standardized header, row, and cell treatments.
- Key props: Standard table-section, row, heading-cell, and data-cell element attributes.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="w-full overflow-x-auto">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  )
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
  )
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  )
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn("border-b border-border transition-colors hover:bg-muted/50", className)}
      {...props}
    />
  )
);
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn(
        "h-10 px-4 text-left align-middle text-xs font-medium uppercase tracking-wide text-muted-foreground",
        className
      )}
      {...props}
    />
  )
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("p-4 align-middle", className)} {...props} />
  )
);
TableCell.displayName = "TableCell";

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
```

## Tabs

- File: `frontend/src/components/ui/tabs.tsx`
- Description: Controlled tabs composition with accessible tablist, trigger, and panel roles.
- Key props: `Tabs` takes `value`, `onValueChange`, `children`, and `className`; triggers and content take their own `value`.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabsContext(component: string) {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error(`${component} must be used within <Tabs>`);
  return ctx;
}

interface TabsProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

function Tabs({ value, onValueChange, children, className }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, setValue: onValueChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

function TabsList({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      role="tablist"
      className={cn("inline-flex items-center gap-1 rounded-md bg-muted p-1", className)}
    >
      {children}
    </div>
  );
}

function TabsTrigger({
  value,
  children,
  className,
  title,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
  /** Tooltip -- lets an icon-only trigger (no visible label) still expose
   * its name on hover/to assistive tech. */
  title?: string;
}) {
  const ctx = useTabsContext("TabsTrigger");
  const isActive = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      aria-label={title}
      title={title}
      onClick={() => ctx.setValue(value)}
      className={cn(
        "rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
        isActive
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

function TabsContent({
  value,
  children,
  className,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  const ctx = useTabsContext("TabsContent");
  if (ctx.value !== value) return null;
  return (
    <div role="tabpanel" className={className}>
      {children}
    </div>
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
```

## Textarea

- File: `frontend/src/components/ui/textarea.tsx`
- Description: Multi-line text input with shared focus, placeholder, and disabled states.
- Key props: Standard `TextareaHTMLAttributes<HTMLTextAreaElement>`.

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
          "placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Textarea.displayName = "Textarea";

export { Textarea };
```

## TokenField

- File: `frontend/src/components/ui/token-field.tsx`
- Description: Password-style input with show/hide and copy affordances for operator-managed secrets.
- Key props: `value`, `onChange`, `className`, plus input props except `value`, `onChange`, and `type`.

```tsx
import { useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { Input, type InputProps } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Password-style field with a show/hide eye toggle plus a copy-to-clipboard
 * button -- shared by every place that holds a secret an operator needs to
 * both verify (hidden by default, like a password) and paste elsewhere:
 * Settings' OpenClaw gateway token card and the Agent detail page's
 * ForgeRouter API key card. Doesn't fetch or reveal anything on its own --
 * it only toggles the `type` of whatever `value` the caller already has. */
export function TokenField({
  value,
  onChange,
  className,
  ...inputProps
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
} & Omit<InputProps, "value" | "onChange" | "type">) {
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="relative">
      <Input
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
        className={cn("pr-16 font-mono", className)}
        {...inputProps}
      />
      <div className="absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center gap-2">
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="text-muted-foreground transition-colors hover:text-foreground"
          tabIndex={-1}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={handleCopy}
          disabled={!value}
          className="text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          tabIndex={-1}
        >
          {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}
```
