import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink, HelpCircle, Keyboard, KeyboardOff, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useClickOutside } from "@/hooks/useClickOutside";
import { usePhoneMenuStyle } from "@/hooks/usePhoneMenuStyle";

export function TerminalToolbar({ copied, onCopy, latestLink, onOpenLatestLink, fontSize, onZoomOut, onZoomReset, onZoomIn, touchDevice, touchInput, onToggleTouchInput }: {
  copied: boolean; onCopy: () => void; latestLink: string | null; onOpenLatestLink: () => void;
  fontSize: number; onZoomOut: () => void; onZoomReset: () => void; onZoomIn: () => void;
  touchDevice: boolean; touchInput: boolean; onToggleTouchInput: () => void;
}) {
  const { t } = useTranslation("workspace");
  const [helpOpen, setHelpOpen] = useState(false);
  const helpRef = useRef<HTMLDivElement>(null);
  useClickOutside(helpRef, () => setHelpOpen(false), helpOpen);
  const menuStyle = usePhoneMenuStyle(helpRef, helpOpen);
  const iconClass = "h-8 w-8 shrink-0";
  const linkLabel = latestLink ? t("terminal.openLatestLink") : t("terminal.noLinkDetected");
  return <>
    <Button variant="outline" size="icon" className={iconClass} title={t("terminal.copyHelp")} aria-label={t("terminal.copy")} onPointerDown={(event) => event.preventDefault()} onClick={onCopy}>{copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}</Button>
    <Button variant="outline" size="icon" className={iconClass} title={latestLink ?? linkLabel} aria-label={linkLabel} disabled={!latestLink} onClick={onOpenLatestLink}><ExternalLink className="h-4 w-4" /></Button>
    <Button variant="outline" size="icon" className={iconClass} title={t("terminal.zoomOutTitle")} aria-label={t("terminal.zoomOut")} disabled={fontSize <= 9} onClick={onZoomOut}><Minus className="h-4 w-4" /></Button>
    <Button variant="outline" size="sm" className="h-8 min-w-11 shrink-0 px-1.5 font-mono text-xs" title={t("terminal.zoomReset", { size: fontSize, defaultSize: 14 })} aria-label={t("terminal.zoomReset", { size: fontSize, defaultSize: 14 })} onClick={onZoomReset}>{fontSize}px</Button>
    <Button variant="outline" size="icon" className={iconClass} title={t("terminal.zoomInTitle")} aria-label={t("terminal.zoomIn")} disabled={fontSize >= 32} onClick={onZoomIn}><Plus className="h-4 w-4" /></Button>
    {touchDevice && <Button variant={touchInput ? "secondary" : "outline"} size="icon" className={iconClass} title={t(touchInput ? "terminal.touchInputClose" : "terminal.touchInputOpen")} aria-label={t(touchInput ? "terminal.touchInputClose" : "terminal.touchInputOpen")} aria-pressed={touchInput} onPointerDown={(event) => event.preventDefault()} onClick={onToggleTouchInput}>{touchInput ? <KeyboardOff className="h-4 w-4" /> : <Keyboard className="h-4 w-4" />}</Button>}
    <div className="relative" ref={helpRef}>
      <Button variant={helpOpen ? "secondary" : "outline"} size="icon" className={iconClass} title={t("terminal.help.title")} aria-label={t("terminal.help.title")} aria-expanded={helpOpen} onClick={() => setHelpOpen((open) => !open)}><HelpCircle className="h-4 w-4" /></Button>
      {helpOpen && <div className="absolute right-0 top-full z-30 mt-1 max-h-[70vh] w-80 overflow-y-auto rounded-md border border-border bg-card p-3 shadow-md max-md:fixed max-md:inset-x-2 max-md:w-auto" style={menuStyle}>
        <h2 className="mb-2 text-sm font-medium">{t("terminal.help.title")}</h2>
        <div className="space-y-1.5 text-[11px] leading-4">{[
          [t("terminal.help.selectShortcut"), t("terminal.help.select")], ["Ctrl + C", t("terminal.help.copy")], ["Ctrl + V", t("terminal.help.paste")],
          [t("terminal.help.linkButton"), t("terminal.help.openLink")], ["Ctrl + B, %", t("terminal.help.splitVertical")], ['Ctrl + B, "', t("terminal.help.splitHorizontal")],
          ["Ctrl + B, ← ↑ ↓ →", t("terminal.help.changePane")], ["Ctrl + B, z", t("terminal.help.zoomPane")], ["Ctrl + B, x", t("terminal.help.closePane")], [t("terminal.help.closeTabButton"), t("terminal.help.detach")],
        ].map(([shortcut, description]) => <div key={`${shortcut}-${description}`} className="grid grid-cols-[7.25rem_1fr] items-start gap-2"><kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground">{shortcut}</kbd><span className="pt-0.5 text-muted-foreground">{description}</span></div>)}</div>
      </div>}
    </div>
  </>;
}
