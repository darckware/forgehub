import { useState } from "react";
import { Check, Copy, Eye, EyeOff, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Renders a masked secret token or password inside chat messages.
 * Prevents accidental exposure in screenshots or screen shares,
 * with interactive show/hide and copy-to-clipboard actions.
 */
export function SecretBadge({
  name = "SECRET",
  env = "production",
  value,
  className,
}: {
  name?: string;
  env?: string;
  value: string;
  className?: string;
}) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      className={cn(
        "my-2 inline-flex max-w-full flex-wrap items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs text-foreground shadow-sm transition-colors",
        className
      )}
      data-testid="secret-badge"
    >
      <div className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
        <Lock className="h-3.5 w-3.5 shrink-0" />
        <span className="font-semibold">ForgeVault</span>
      </div>

      {name && (
        <span
          className="rounded bg-black/15 dark:bg-white/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-primary"
          data-testid="secret-name"
        >
          {name}
        </span>
      )}

      {env && (
        <span
          className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase font-semibold text-muted-foreground"
          data-testid="secret-env"
        >
          {env}
        </span>
      )}

      <span
        className="font-mono text-muted-foreground select-none"
        data-testid="secret-value"
      >
        {revealed ? value : "••••••••••••••••"}
      </span>

      <div className="ml-auto flex items-center gap-1 pl-1">
        <button
          type="button"
          onClick={() => setRevealed((v) => !v)}
          className="rounded p-1 text-muted-foreground hover:bg-black/10 dark:hover:bg-white/10 hover:text-foreground transition-colors"
          title={revealed ? "Ocultar segredo" : "Revelar segredo"}
          aria-label={revealed ? "Ocultar segredo" : "Revelar segredo"}
          data-testid="secret-toggle"
        >
          {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>

        <button
          type="button"
          onClick={handleCopy}
          className="rounded p-1 text-muted-foreground hover:bg-black/10 dark:hover:bg-white/10 hover:text-foreground transition-colors"
          title="Copiar segredo"
          aria-label="Copiar segredo"
          data-testid="secret-copy"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
    </div>
  );
}
