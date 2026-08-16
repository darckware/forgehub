import { useTranslation } from "react-i18next";
import { AssistantRobotIcon } from "@/components/AssistantRobotIcon";
import { cn } from "@/lib/utils";
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
 * pages the way 10 hand-copied instances did.
 * A plain clickable icon rather than a shadcn `Button` (2026-08-16, Marcelo:
 * "a sugestão de remover o botão e adicionar um icone clicavel e porque
 * ficou muito pequeno e não da para ver a animação do icone direito") --
 * `Button`'s `size="icon"` box padded the mascot down to `h-4 w-4`, too
 * small to read the blink/antenna animation. Here the icon fills almost
 * the entire clickable area instead. */
export function AssistantToggleButton({
  className,
  openTitle,
}: AssistantToggleButtonProps) {
  const { t } = useTranslation("common");
  const assistantOpen = useAssistantStore((s) => s.open);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const accessibleLabel = assistantOpen ? t("assistant.close") : openTitle ?? t("assistant.open");

  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-11 w-11 items-center justify-center rounded-md text-foreground/80 transition-colors hover:bg-accent hover:text-accent-foreground",
        assistantOpen && "bg-secondary text-secondary-foreground",
        className
      )}
      title={accessibleLabel}
      aria-label={accessibleLabel}
      onClick={() => setAssistantOpen(!assistantOpen)}
    >
      <AssistantRobotIcon className="h-8 w-8" />
      <span className="sr-only">{accessibleLabel}</span>
    </button>
  );
}
