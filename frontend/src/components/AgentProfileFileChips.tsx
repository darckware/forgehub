import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Loader2, SquareArrowOutUpRight, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { profileFileNamesFor, useAgentProfileFile, type Agent } from "@/hooks/useAgent";

/**
 * One chip per profile Markdown file, sitting on the same line as the agent's
 * profile directory in the org chart — the directory and what is inside it
 * belong together.
 *
 * The chip list is computed client-side from the agent's runtime/slug
 * (`profileFileNamesFor`, mirroring the backend allow-list) rather than
 * fetched: the chart renders a dozen agents at once, and a listing request
 * per card would be a dozen round trips before the user has clicked anything.
 * Only the file actually opened is fetched, and a file that turns out not to
 * exist reports itself as such (content comes back null, not 404).
 */

const ROLE_KEYS: Record<string, string> = {
  "SOUL.md": "soul",
  "IDENTITY.md": "identity",
  "USER.md": "user",
  "TOOLS.md": "tools",
  "AGENTS.md": "agents",
  "CLAUDE.md": "claude",
  "FOUNDATION_LINK.md": "foundationLink",
  "HEARTBEAT.md": "heartbeat",
  "MEMORY.md": "memory",
  "CONTINUITY.md": "continuity",
};

function roleKeyFor(filename: string): string {
  return ROLE_KEYS[filename] ?? (filename.endsWith("_SUBAGENTS.md") ? "subagents" : "generic");
}

/** Chip label: drop the shared `.md` suffix, and shorten the long
 *  `<PROFILE>_SUBAGENTS.md` to just SUBAGENTS — the profile is already named
 *  at the top of the card. */
function chipLabel(filename: string): string {
  if (filename.endsWith("_SUBAGENTS.md")) return "SUBAGENTS";
  return filename.replace(/\.md$/, "");
}

function FilePreview({ agent, filename }: { agent: Agent; filename: string }) {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error } = useAgentProfileFile(agent.id, filename);

  return (
    // basis-full: the chips sit on the directory line inside a flex-wrap row,
    // so the preview has to claim a line of its own rather than squeeze in
    // beside them.
    <div className="mt-2 w-full basis-full rounded-md border bg-muted/20">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="font-mono text-xs font-medium">{filename}</span>
            {data && data.content === null && (
              <Badge variant="outline" className="text-[10px]">
                {t("profileFiles.notCreated")}
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {t(`profileFiles.roles.${roleKeyFor(filename)}`)}
          </p>
        </div>
        {/* The chart is a read surface; editing lives on the agent page. */}
        <Link
          to={`/agents/${agent.id}`}
          className="inline-flex items-center gap-1 whitespace-nowrap text-[11px] text-muted-foreground hover:text-foreground hover:underline"
        >
          <SquareArrowOutUpRight className="h-3 w-3" />
          {t("profileChips.openToEdit")}
        </Link>
      </div>

      {/* Own vertical scrollbar so a long SOUL.md never stretches the card. */}
      <div className="max-h-72 overflow-y-auto px-3 py-2">
        {isLoading && (
          <p className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {t("profileFiles.loading", { filename })}
          </p>
        )}
        {isError && (
          <p className="py-2 text-xs text-destructive">
            {t("profileFiles.loadError", { filename, message: (error as Error)?.message })}
          </p>
        )}
        {data &&
          (data.content ? (
            <Markdown content={data.content} className="text-xs" />
          ) : (
            <p className="py-2 text-xs italic text-muted-foreground">
              {t("profileChips.notCreatedHint", { filename })}
            </p>
          ))}
      </div>
    </div>
  );
}

export function AgentProfileFileChips({ agent }: { agent: Agent }) {
  const { t } = useTranslation("agent");
  const [openFile, setOpenFile] = useState<string | null>(null);
  const filenames = profileFileNamesFor(agent);

  // No profile directory means no profile files -- an agent registered by
  // hand with no filesystem presence, not an error.
  if (!agent.effective_home_path) return null;

  return (
    <>
      <div
        role="tablist"
        aria-label={t("profileChips.ariaLabel")}
        className="flex min-w-0 flex-wrap items-center gap-1"
      >
        {filenames.map((filename) => {
          const isOpen = openFile === filename;
          return (
            <button
              key={filename}
              type="button"
              role="tab"
              aria-selected={isOpen}
              title={`${filename} — ${t(`profileFiles.roles.${roleKeyFor(filename)}`)}`}
              onClick={() => setOpenFile(isOpen ? null : filename)}
              className={cn(
                "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] leading-tight transition-colors",
                isOpen
                  ? "border-primary/50 bg-primary/10 text-foreground"
                  : "border-transparent bg-muted/60 text-muted-foreground hover:text-foreground"
              )}
            >
              {chipLabel(filename)}
            </button>
          );
        })}
        {openFile && (
          <button
            type="button"
            onClick={() => setOpenFile(null)}
            aria-label={t("profileChips.close")}
            title={t("profileChips.close")}
            className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
      {openFile && <FilePreview agent={agent} filename={openFile} />}
    </>
  );
}
