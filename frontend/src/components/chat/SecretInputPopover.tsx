import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyRound, Lock, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TokenField } from "@/components/ui/token-field";
import { useClickOutside } from "@/hooks/useClickOutside";
import { cn } from "@/lib/utils";

interface SecretInputPopoverProps {
  onInsertSecret: (formattedText: string) => void;
  className?: string;
}

export function SecretInputPopover({ onInsertSecret, className }: SecretInputPopoverProps) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const [secretName, setSecretName] = useState("");
  const [environment, setEnvironment] = useState("production");
  const [secretValue, setSecretValue] = useState("");
  const [error, setError] = useState<"nameRequired" | "valueRequired" | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cleanName = secretName.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    const cleanValue = secretValue.trim();

    if (!cleanName) {
      setError("nameRequired");
      return;
    }
    if (!cleanValue) {
      setError("valueRequired");
      return;
    }

    const formattedPrompt = `${t("secretInput.agentInstruction")}\n<secret name="${cleanName}" env="${environment}">${cleanValue}</secret>`;

    onInsertSecret(formattedPrompt);
    setSecretName("");
    setSecretValue("");
    setError(null);
    setOpen(false);
  }

  return (
    <div className={cn("relative shrink-0", className)} ref={containerRef}>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn(
          "h-8 w-8 rounded-full transition-colors",
          open ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground"
        )}
        aria-label={t("secretInput.open")}
        title={t("secretInput.open")}
        onClick={() => setOpen((v) => !v)}
      >
        <Lock className="h-4 w-4" />
      </Button>

      {open && (
        <div
          className="absolute bottom-full left-0 z-30 mb-2 w-80 rounded-xl border border-border bg-card p-3 shadow-xl backdrop-blur-md"
          role="dialog"
          aria-label={t("secretInput.dialog")}
        >
          <div className="flex items-center justify-between pb-2 border-b border-border mb-2.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <KeyRound className="h-4 w-4 text-amber-500" />
              <span>{t("secretInput.title")}</span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={t("secretInput.close")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-2.5">
            <div>
              <Label className="text-[11px] font-medium text-muted-foreground">
                {t("secretInput.keyName")}
              </Label>
              <Input
                value={secretName}
                onChange={(e) => {
                  setSecretName(e.target.value);
                  if (error) setError(null);
                }}
                placeholder={t("secretInput.keyExample")}
                className="mt-1 h-7 text-xs font-mono"
                autoFocus
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-[11px] font-medium text-muted-foreground">{t("secretInput.environment")}</Label>
                <select
                  value={environment}
                  onChange={(e) => setEnvironment(e.target.value)}
                  className="mt-1 flex h-7 w-full rounded-md border border-input bg-transparent px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="production">{t("secretInput.production")}</option>
                  <option value="staging">{t("secretInput.staging")}</option>
                  <option value="development">{t("secretInput.development")}</option>
                </select>
              </div>
              <div className="flex flex-col justify-end">
                <span className="text-[10px] text-muted-foreground/80 flex items-center gap-1 pb-1">
                  <ShieldCheck className="h-3 w-3 text-emerald-500 shrink-0" />
                  {t("secretInput.encryption")}
                </span>
              </div>
            </div>

            <div>
              <Label className="text-[11px] font-medium text-muted-foreground">
                {t("secretInput.secretValue")}
              </Label>
              <div className="mt-1">
                <TokenField
                  value={secretValue}
                  onChange={(v) => {
                    setSecretValue(v);
                    if (error) setError(null);
                  }}
                  placeholder={t("secretInput.valuePlaceholder")}
                  className="h-7 text-xs"
                />
              </div>
            </div>

            {error && (
              <p className="text-[11px] font-medium text-destructive">{t(`secretInput.${error}`)}</p>
            )}

            <Button type="submit" size="sm" className="w-full h-8 text-xs font-medium gap-1.5 mt-1">
              <Lock className="h-3.5 w-3.5" />
              {t("secretInput.insert")}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
