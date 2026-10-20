import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Copy-to-clipboard button -- same hover-reveal copy affordance as
 * Markdown.tsx's code-block copy button, generalized to any text (a whole
 * document's raw content, a generation prompt, ...) instead of a single
 * fenced block. Icon-only by default; pass `label` to render it as a full
 * text+icon button matching an adjacent action button's size/style (2026-08-16,
 * Marcelo, re: Conception's context-prompt copy button sitting next to
 * "Generate from context": "o botão de cópia precisa ser igual ao gerador
 * de contexto, ele é o gerador para o contexto" -- it's the counterpart
 * generator action, not an incidental icon). */
export function CopyButton({
  getText,
  title,
  label,
}: {
  getText: () => string;
  title: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(getText());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Button
      type="button"
      variant="outline"
      size={label ? "default" : "icon"}
      title={title}
      aria-label={title}
      onClick={handleCopy}
    >
      {copied
        ? <Check className={label ? "mr-2 h-4 w-4" : "h-4 w-4"} />
        : <Copy className={label ? "mr-2 h-4 w-4" : "h-4 w-4"} />}
      {label}
    </Button>
  );
}
