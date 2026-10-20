import { useTranslation } from "react-i18next";
import { ArrowDownToLine } from "lucide-react";

/** Round "go to the last line" button pinned to the bottom-right of a
 * scrolling transcript -- the terminal's (TerminalPane.tsx), shared by the
 * chat conversation and channel transcripts. The parent must be `relative`
 * and render it only while the user has scrolled away from the bottom. */
export function JumpToBottomButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation("workspace");
  return (
    <button
      type="button"
      onClick={onClick}
      className="absolute bottom-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-muted text-foreground shadow-md hover:bg-accent"
      title={t("terminal.jumpToBottom")}
      aria-label={t("terminal.jumpToBottom")}
    >
      <ArrowDownToLine className="h-4 w-4" />
    </button>
  );
}
