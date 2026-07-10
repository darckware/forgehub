import { Bot } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { useAssistantStore } from "@/store/assistantStore";

interface AssistantToggleButtonProps {
  size?: ButtonProps["size"];
  className?: string;
  /** Title shown while closed -- the open-state title is always "Close assistant". */
  openTitle?: string;
}

/** Opens/closes the global Assistant panel (see AssistantDrawer). Shared
 * across every page's header so the button/icon/wiring can't drift between
 * pages the way 10 hand-copied instances did. */
export function AssistantToggleButton({
  size,
  className = "gap-1.5",
  openTitle = "Open the assistant",
}: AssistantToggleButtonProps) {
  const assistantOpen = useAssistantStore((s) => s.open);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);

  return (
    <Button
      size={size}
      variant={assistantOpen ? "secondary" : "outline"}
      className={className}
      title={assistantOpen ? "Close assistant" : openTitle}
      onClick={() => setAssistantOpen(!assistantOpen)}
    >
      <Bot className="h-4 w-4" /> Assistant
    </Button>
  );
}
