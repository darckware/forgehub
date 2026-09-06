import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { apiClient, getToken } from "@/lib/api";

// Falls back to the page's own origin, not a hardcoded localhost:8000 --
// see the matching comment in lib/api.ts.
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
const WS_BASE = API_BASE.replace(/^http/, "ws");

interface TerminalPaneProps {
  /** Stable id for this tab (the tmux session name on the host) -- reusing
   * the same id across reconnects (e.g. after navigating away and back) is
   * what lets the host-bridge re-attach to the same tmux session instead of
   * starting a new shell, so the running process survives the round trip. */
  sessionId: string;
  /** Launcher to type into the shell once it's up (e.g. "claude"), or
   * undefined for a plain bash session. Only applied when the host-bridge
   * creates the session for the first time -- ignored on reattach. */
  command?: string;
  /** Host directory to `cd` into before the launcher (or the bare shell)
   * starts -- see WorkingDirPicker. */
  cwd?: string;
  /** Whether this pane's tab is currently selected -- panes for inactive
   * tabs stay mounted (so the session keeps running) but hidden. */
  active: boolean;
}

export function TerminalPane({ sessionId, command, cwd, active }: TerminalPaneProps) {
  const { t } = useTranslation("workspace");
  const containerRef = useRef<HTMLDivElement>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      theme: { background: "#0a0a0f" },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    const webLinksAddon = new WebLinksAddon((event, uri) => {
      window.open(uri, "_blank", "noopener,noreferrer");
    });
    term.loadAddon(webLinksAddon);
    term.open(container);
    fitAddon.fit();
    fitAddonRef.current = fitAddon;
    termRef.current = term;

    // xterm.js's own keydown handling treats Ctrl+C/Ctrl+V as raw control
    // bytes (SIGINT / SYN) and calls preventDefault on them, which stops the
    // browser's native copy/paste from ever firing -- even though xterm
    // already has "copy"/"paste" DOM listeners wired up to do the right
    // thing with the selection/clipboard. Stepping out of the way for these
    // two combos (returning false skips xterm's own handling) lets the
    // browser's native copy/paste reach those listeners instead. Cmd+C/V on
    // Mac already bypass xterm's interception on their own, so this is a
    // no-op there.
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown" || (!event.ctrlKey && !event.metaKey)) return true;
      const key = event.key.toLowerCase();
      if (key === "c" && term.hasSelection()) return false;
      if (key === "v") return false;
      return true;
    });

    // A WebSocket handshake can't carry an Authorization header, and the
    // real session JWT is long-lived (60min) -- putting it straight in the
    // URL would mean it sits in plaintext in nginx/Cloudflare tunnel access
    // logs for that whole window. Exchange it for a single-use, 30s-lived
    // ticket over a normal authenticated POST first (see terminal.py's
    // /ws-ticket + /ws), and put only that short-lived ticket in the URL.
    let ws: WebSocket | null = null;
    let cancelled = false;
    // Reconnection with backoff (Fase 6.1, 2026-07-28) -- a dropped
    // connection (host-bridge restart, brief network hiccup) used to leave
    // the pane dead on screen until the user navigated away and back. The
    // host tmux session survives a drop on its own (see terminal_ws's
    // docstring); reattaching with the SAME sessionId is what resumes it,
    // and `tmux attach-session` redraws the pane's current content by
    // itself, so no manual history replay is needed here.
    let reconnectAttempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000];

    function scheduleReconnect() {
      if (cancelled) return;
      const delay = RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
      reconnectAttempt += 1;
      term.write(`\r\n\x1b[33m${t("terminal.reconnecting", { seconds: Math.round(delay / 1000) })}\x1b[0m\r\n`);
      reconnectTimer = setTimeout(() => {
        if (!cancelled) connect();
      }, delay);
    }

    async function connect() {
      const params = new URLSearchParams();
      params.set("session", sessionId);
      if (command) params.set("command", command);
      if (cwd) params.set("cwd", cwd);
      try {
        const { ticket } = await apiClient.post<{ ticket: string }>("/api/v1/terminal/ws-ticket");
        if (cancelled) return;
        params.set("ticket", ticket);
      } catch {
        if (!cancelled) {
          term.write(`\r\n\x1b[31m${t("terminal.authFailed")}\x1b[0m\r\n`);
          scheduleReconnect();
        }
        return;
      }

      const socket = new WebSocket(`${WS_BASE}/api/v1/terminal/ws?${params.toString()}`);
      ws = socket;

      // The PTY is read in fixed-size chunks on the host, so the DECRQM
      // sequence stripped below can land split across two WebSocket
      // messages. Hold back a trailing prefix that could still grow into a
      // full match (rather than writing it immediately) and prepend it to
      // the next message, so the strip below can't be defeated by an
      // unlucky chunk boundary.
      let pendingTail = "";
      socket.onmessage = (event) => {
        // @xterm/xterm 6.0.0's DECRQM handler (CSI ? Pm $ p, used by CLIs
        // like Antigravity's `agy` to probe synchronized-output support)
        // throws "r is not defined" inside its own minified bundle and
        // corrupts the parser for the rest of the session -- strip the
        // query before it ever reaches xterm's parser. The app being
        // probed just treats a missing reply as "unsupported", same as
        // without this fix's filtering.
        const raw = pendingTail + (event.data as string);
        const partial = raw.match(/\x1b\[\??[0-9;]*\$?$/);
        const safeEnd = partial ? partial.index! : raw.length;
        pendingTail = raw.slice(safeEnd);
        const data = raw.slice(0, safeEnd).replace(/\x1b\[\??[0-9;]*\$p/g, "");
        term.write(data);
      };
      socket.onopen = () => {
        reconnectAttempt = 0;
        socket.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      };
      // Fires for both a clean server-initiated close and a dropped
      // connection alike (WebSocket has no reliable way to tell them
      // apart) -- always attempt to reconnect unless this effect itself is
      // tearing down (`cancelled`, set right before the deliberate
      // `ws?.close()` in the cleanup below).
      socket.onclose = () => {
        if (ws === socket) ws = null;
        if (!cancelled) scheduleReconnect();
      };
    }
    connect();

    const inputDisposable = term.onData((data) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    // The PTY only carries keystrokes, not the browser's clipboard -- a
    // pasted or dropped image has no representation as terminal input.
    // Instead, upload it and type its host file path, the same way dragging
    // a file onto a real terminal does; CLI agents (claude/codex/agy) that
    // support image input read it by path from there.
    const uploadImageFile = async (file: File) => {
      if (ws?.readyState !== WebSocket.OPEN) return;
      const formData = new FormData();
      formData.append("file", file, file.name || "pasted-image.png");
      const token = getToken();
      try {
        const response = await fetch(`${API_BASE}/api/v1/terminal/upload-image`, {
          method: "POST",
          body: formData,
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as { path?: unknown };
        if (typeof body.path !== "string" || !body.path.trim()) throw new Error("Missing upload path");
        if (ws?.readyState === WebSocket.OPEN) {
          const shellSafePath = body.path.replace(/'/g, "'\\''");
          ws.send(JSON.stringify({ type: "input", data: `'${shellSafePath}' ` }));
        }
      } catch {
        term.write(`\r\n\x1b[31m${t("terminal.imageUploadFailed")}\x1b[0m\r\n`);
      }
    };

    const handlePaste = (event: ClipboardEvent) => {
      const imageItem = Array.from(event.clipboardData?.items ?? []).find((item) =>
        item.type.startsWith("image/")
      );
      if (!imageItem) return;
      event.preventDefault();
      // xterm's own paste handler lives on its textarea and calls
      // stopPropagation() unconditionally (it doesn't check for images --
      // it just reads text/plain and bails if there isn't any), which would
      // otherwise stop this bubble-phase listener on `container` from ever
      // seeing the event. Listening on the capture phase intercepts it on
      // the way down, before xterm's bubble-phase handler runs.
      event.stopPropagation();
      const file = imageItem.getAsFile();
      if (file) void uploadImageFile(file);
    };
    container.addEventListener("paste", handlePaste, true);

    // xterm renders rows as plain DOM text, so a dragged file landing on it
    // would otherwise just navigate the browser to the file (the default
    // "drop" action) instead of reaching the terminal.
    const handleDragOver = (event: DragEvent) => {
      event.preventDefault();
    };
    const handleDrop = (event: DragEvent) => {
      const file = Array.from(event.dataTransfer?.files ?? []).find((f) =>
        f.type.startsWith("image/")
      );
      if (!file) return;
      event.preventDefault();
      void uploadImageFile(file);
    };
    container.addEventListener("dragover", handleDragOver);
    container.addEventListener("drop", handleDrop);

    const resizeObserver = new ResizeObserver(() => {
      // While the tab is inactive its container is display:none, which
      // collapses offsetWidth/offsetHeight to 0 -- FitAddon then proposes
      // its hard-coded floor of {cols:2, rows:1} and that bogus size gets
      // pushed straight to the real PTY (host-bridge's TIOCSWINSZ), visibly
      // corrupting whatever was rendering in the background tmux session.
      // Skip fitting while hidden; the `active` effect below re-fits with
      // the real size once the tab is shown again.
      if (container.offsetWidth === 0 || container.offsetHeight === 0) return;
      fitAddon.fit();
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    });
    resizeObserver.observe(container);

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      inputDisposable.dispose();
      container.removeEventListener("paste", handlePaste, true);
      container.removeEventListener("dragover", handleDragOver);
      container.removeEventListener("drop", handleDrop);
      resizeObserver.disconnect();
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
      term.dispose();
    };
    // sessionId/command/cwd are fixed for the lifetime of a tab -- only mount/unmount matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!active) return;
    fitAddonRef.current?.fit();
    // The pane's parent toggles display:none while inactive, so the
    // background process can keep redrawing (e.g. Hermes's live activity
    // feed) while nothing is on screen to receive it. Force a full repaint
    // on becoming visible again instead of waiting for the next byte from
    // the PTY, which could be seconds away or never come if it's idle.
    const term = termRef.current;
    if (term) term.refresh(0, term.rows - 1);
  }, [active]);

  return <div ref={containerRef} className="h-full w-full" />;
}
