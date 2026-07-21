import { isValidElement, useEffect, useId, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";
import { AlertTriangle, Check, Code2, Copy, Maximize2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme";

/** Code blocks (```...```) get a hover-reveal copy button -- reads
 * .textContent off the rendered <pre> rather than re-serializing the
 * markdown AST, so it copies exactly what's on screen regardless of
 * nested inline markup. */
function CodeBlock({ children }: { children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  async function handleCopy() {
    const text = preRef.current?.textContent ?? "";
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group/code relative mb-2 last:mb-0">
      <pre ref={preRef} className="overflow-x-auto rounded-md bg-black/10 p-2">
        {children}
      </pre>
      <button
        type="button"
        aria-label="Copy code"
        title="Copy code"
        onClick={handleCopy}
        className="absolute right-1.5 top-1.5 rounded bg-black/20 p-1 opacity-0 transition-opacity group-hover/code:opacity-100 hover:bg-black/30"
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      </button>
    </div>
  );
}

/** Full-screen overlay for a rendered diagram -- same fixed-backdrop pattern
 * as ConfirmDialog (no Radix Dialog dependency in this codebase yet). */
function MermaidFullscreen({ svg, onClose }: { svg: string; onClose: () => void }) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 max-h-full max-w-full overflow-auto rounded-lg bg-background p-6 shadow-2xl">
        <button
          type="button"
          aria-label="Close"
          title="Close"
          onClick={onClose}
          className="absolute right-2 top-2 rounded p-1 hover:bg-black/10"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="[&_svg]:max-w-none" dangerouslySetInnerHTML={{ __html: svg }} />
      </div>
    </div>
  );
}

/** Renders a ```mermaid fenced block as an actual diagram, with a header
 * toggle to view the raw source and a fullscreen expand -- mirrors the
 * Mermaid block UX users already know from ChatGPT/Claude canvases. */
function MermaidDiagram({ source }: { source: string }) {
  const { resolvedTheme } = useTheme();
  const rawId = useId().replace(/[^a-zA-Z0-9-]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: resolvedTheme === "dark" ? "dark" : "default",
      fontFamily: "inherit",
    });
    (async () => {
      try {
        // Validate first with suppressErrors -- calling render() directly on
        // invalid input makes mermaid inject its own error graphic straight
        // into <body> (outside our card, impossible to style/remove) rather
        // than just rejecting the promise.
        const valid = await mermaid.parse(source, { suppressErrors: true });
        if (!valid) {
          if (!cancelled) {
            setSvg(null);
            setError("Invalid Mermaid syntax");
          }
          return;
        }
        const { svg: rendered } = await mermaid.render(`mermaid-${rawId}`, source);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setSvg(null);
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source, resolvedTheme, rawId]);

  return (
    <div className="mb-2 overflow-hidden rounded-md border border-current/15 last:mb-0">
      <div className="flex items-center justify-between bg-black/10 px-2 py-1">
        <span className="text-xs font-medium opacity-70">Mermaid</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={showSource ? "Show diagram" : "Show source"}
            title={showSource ? "Show diagram" : "Show source"}
            onClick={() => setShowSource((v) => !v)}
            className="rounded p-1 hover:bg-black/10"
          >
            <Code2 className="h-3.5 w-3.5" />
          </button>
          {svg && !error && (
            <button
              type="button"
              aria-label="Fullscreen"
              title="Fullscreen"
              onClick={() => setFullscreen(true)}
              className="rounded p-1 hover:bg-black/10"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
      <div className="overflow-x-auto p-3">
        {error ? (
          <div className="flex items-start gap-2 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>Could not render Mermaid diagram: {error}</span>
          </div>
        ) : showSource || !svg ? (
          <pre className="overflow-x-auto text-xs">
            <code>{source}</code>
          </pre>
        ) : (
          <div className="flex justify-center [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />
        )}
      </div>
      {fullscreen && svg && !error && (
        <MermaidFullscreen svg={svg} onClose={() => setFullscreen(false)} />
      )}
    </div>
  );
}

function isMermaidCodeElement(node: React.ReactNode): boolean {
  if (!isValidElement(node)) return false;
  const { className } = node.props as { className?: string };
  return typeof className === "string" && className.includes("language-mermaid");
}

const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ className, children }) => {
    if (className?.includes("language-mermaid")) {
      return <MermaidDiagram source={String(children).replace(/\n$/, "")} />;
    }
    return className ? (
      <code className={cn("font-mono text-[0.85em]", className)}>{children}</code>
    ) : (
      <code className="rounded bg-black/10 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
    );
  },
  pre: ({ children }) => (isMermaidCodeElement(children) ? <>{children}</> : <CodeBlock>{children}</CodeBlock>),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-current/30 pl-2 italic last:mb-0">{children}</blockquote>
  ),
  h1: ({ children }) => <h1 className="mb-2 text-base font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 text-sm font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold">{children}</h3>,
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-current/20 px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-current/20 px-2 py-1">{children}</td>,
};

export function Markdown({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("[&>*:last-child]:mb-0", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
