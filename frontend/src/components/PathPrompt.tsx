import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Small inline prompt row (new file / new folder / rename) shared by the
 * Docs and Knowledge Base pages. */
export function PathPrompt({
  label,
  initial,
  onConfirm,
  onCancel,
  pending,
  confirmLabel,
  cancelLabel,
}: {
  label: string;
  initial: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
  pending: boolean;
  confirmLabel: string;
  cancelLabel: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <Input
        autoFocus
        value={value}
        className="h-8 text-xs"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) onConfirm(value.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
      <Button size="sm" disabled={pending || !value.trim()} onClick={() => onConfirm(value.trim())}>
        {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : confirmLabel}
      </Button>
      <Button size="sm" variant="outline" onClick={onCancel}>
        {cancelLabel}
      </Button>
    </div>
  );
}
