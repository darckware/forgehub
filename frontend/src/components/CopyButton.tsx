import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Icon-only copy-to-clipboard button -- same hover-reveal copy affordance
 * as Markdown.tsx's code-block copy button, generalized to any text (here:
 * a whole document's raw content) instead of a single fenced block. */
export function CopyButton({ getText, title }: { getText: () => string; title: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(getText());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Button variant="outline" size="icon" title={title} aria-label={title} onClick={handleCopy}>
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
    </Button>
  );
}
