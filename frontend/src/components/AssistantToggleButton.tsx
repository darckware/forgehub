import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAssistantStore } from "@/store/assistantStore";

interface AssistantToggleButtonProps {
  /** Kept for source compatibility; the shared control is always icon-only. */
  size?: "default" | "sm" | "lg" | "icon" | null;
  className?: string;
  /** Title shown while closed -- the open-state title is always "Close assistant". */
  openTitle?: string;
}

/** Opens/closes the global Assistant panel (see AssistantDrawer). Shared
 * across every page's header so the button/icon/wiring can't drift between
 * pages the way 10 hand-copied instances did. */
export function AssistantToggleButton({
  className,
  openTitle,
}: AssistantToggleButtonProps) {
  const { t } = useTranslation("common");
  const assistantOpen = useAssistantStore((s) => s.open);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const accessibleLabel = assistantOpen ? t("assistant.close") : openTitle ?? t("assistant.open");

  return (
    <Button
      size="icon"
      variant={assistantOpen ? "secondary" : "outline"}
      className={className}
      title={accessibleLabel}
      aria-label={accessibleLabel}
      onClick={() => setAssistantOpen(!assistantOpen)}
    >
      <Bot className="h-4 w-4" />
      <span className="sr-only">{accessibleLabel}</span>
    </Button>
  );
}
