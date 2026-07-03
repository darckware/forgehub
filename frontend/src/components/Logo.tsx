import { cn } from "@/lib/utils";

/**
 * Brand mark: an anvil (the forge — building/executing the work) struck by
 * a spark (an AI agent actively at work on it). Deliberately fixed,
 * non-theme-dependent brand colors -- indigo anvil + amber spark -- so the
 * mark reads the same everywhere instead of just matching whatever text
 * color happens to surround it.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <polygon points="8,29 24,25 24,35" fill="#4f46e5" />
      <rect x="22" y="24" width="28" height="11" rx="1.5" fill="#4f46e5" />
      <rect x="29" y="35" width="10" height="9" fill="#4f46e5" />
      <polygon points="23,44 45,44 51,53 17,53" fill="#4f46e5" />
      <path
        d="M52 11 L54 16 L59 18 L54 20 L52 25 L50 20 L45 18 L50 16 Z"
        fill="#f59e0b"
      />
    </svg>
  );
}

interface LogoProps {
  className?: string;
  /** Render only the mark, no wordmark — used in collapsed layouts. */
  iconOnly?: boolean;
}

export function Logo({ className, iconOnly = false }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-2 overflow-hidden", className)}>
      <LogoMark className="h-11 w-11 shrink-0" />
      {!iconOnly && (
        <span className="text-lg font-semibold tracking-tight whitespace-nowrap">
          ForgeHub
        </span>
      )}
    </div>
  );
}
