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
