import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import type { NavGroupEntry, NavSectionEntry } from "@/components/layout/navSections";

interface FlatEntry {
  to: string;
  label: string;
  section: string;
  module?: string;
  icon: React.ComponentType<{ className?: string }>;
}

function flattenSections(sections: NavSectionEntry[]): FlatEntry[] {
  const out: FlatEntry[] = [];
  for (const section of sections) {
    for (const entry of section.entries) {
      if (entry.type === "link") {
        out.push({ to: entry.to, label: entry.label, section: section.label, module: entry.module, icon: entry.icon });
      } else {
        for (const item of (entry as NavGroupEntry).items) {
          out.push({
            to: item.to,
            label: `${entry.label} / ${item.label}`,
            section: section.label,
            module: item.module,
            icon: item.icon,
          });
        }
      }
    }
  }
  return out;
}

/** Cmd/Ctrl+K quick navigation, filtered to whatever the signed-in user can
 * actually view -- reuses the same permission map the sidebar reads, not a
 * per-item hook call (avoids conditional hooks over a mapped list). */
export function CommandPalette({
  sections,
  open,
  onOpenChange,
}: {
  sections: NavSectionEntry[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const setOpen = onOpenChange;
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const permissions = useAuthStore((s) => s.permissions);

  const canView = React.useCallback(
    (module: string | undefined) => {
      if (!module) return true;
      if (!user) return false;
      if (user.is_admin) return true;
      return permissions[module]?.can_view ?? false;
    },
    [user, permissions]
  );

  const allEntries = React.useMemo(() => flattenSections(sections), [sections]);

  const visibleEntries = React.useMemo(() => {
    const withPerm = allEntries.filter((entry) => canView(entry.module));
    if (!query.trim()) return withPerm;
    const q = query.trim().toLowerCase();
    return withPerm.filter(
      (entry) => entry.label.toLowerCase().includes(q) || entry.section.toLowerCase().includes(q)
    );
  }, [allEntries, canView, query]);

  React.useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isK = e.key.toLowerCase() === "k";
      if ((e.metaKey || e.ctrlKey) && isK) {
        e.preventDefault();
        setOpen(!open);
        return;
      }
      if (!open) return;
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, visibleEntries.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = visibleEntries[activeIndex];
        if (target) {
          navigate(target.to);
          setOpen(false);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, visibleEntries, activeIndex, navigate]);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 sm:pt-[15vh]"
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative z-10 flex max-h-full w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a page..."
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Sair"
            title="Sair"
            className="flex shrink-0 items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <X className="h-3 w-3" />
            Sair
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {visibleEntries.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">No matching pages.</p>
          )}
          {visibleEntries.map((entry, i) => (
            <button
              key={entry.to}
              type="button"
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => {
                navigate(entry.to);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm",
                i === activeIndex ? "bg-accent text-accent-foreground" : "text-foreground"
              )}
            >
              <entry.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{entry.label}</span>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/60">
                {entry.section}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
