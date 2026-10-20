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
