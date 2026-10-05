import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Check, ChevronRight, Copy, ExternalLink, HelpCircle, Keyboard, KeyboardOff, Minus, Plus, SendHorizontal, SlidersHorizontal } from "lucide-react";
import "@xterm/xterm/css/xterm.css";
import { JumpToBottomButton } from "@/components/JumpToBottomButton";
import { apiClient, getToken } from "@/lib/api";
import { attachTerminalImeInput } from "@/lib/terminalImeInput";
import {
  copyTerminalText,
  findLastHttpUrl,
  prepareTerminalContextMenu,
  terminalBufferToText,
} from "@/lib/terminalInteraction";

const FONT_SIZE_STORAGE_KEY = "forgehub_terminal_font_size";
const DEFAULT_FONT_SIZE = 14;
const MIN_FONT_SIZE = 9;
const MAX_FONT_SIZE = 32;

function getStoredFontSize(): number {
  try {
    const raw = localStorage.getItem(FONT_SIZE_STORAGE_KEY);
    if (!raw) return DEFAULT_FONT_SIZE;
    const val = parseInt(raw, 10);
    return isNaN(val) ? DEFAULT_FONT_SIZE : Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, val));
  } catch {
    return DEFAULT_FONT_SIZE;
  }
}

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

/** Phones/tablets: xterm.js takes keyboard input through a hidden textarea,
 * and Android IMEs (Gboard's suggestions/autocorrect) re-commit words already
 * sent, so typed text shows up duplicated in the PTY -- a known xterm.js
 * limitation with no fix upstream (2026-09-26, Marcelo: "no prompt de digitar
 * está apresentado um problema de digitação as vezes", and his own messages
 * arrived with phrases repeated). On a coarse pointer the terminal instead
 * gets a native input bar: the IME, autocorrect and dictation all work
 * normally there, and the text only reaches the PTY on Send. */
const TOUCH_INPUT_STORAGE_KEY = "forgehub-terminal-touch-input";

/** The copy/link/zoom/keyboard/help cluster floats over the terminal's
 * top-right corner and covered the output under it (2026-09-26, Marcelo:
 * "os botões de zoom no canto superior direito ... atrapalha na
 * visualização ... um botão de recolher", for phone and desktop alike).
 * Collapsed by default to a single small toggle; the choice persists. */
const CONTROLS_COLLAPSED_STORAGE_KEY = "forgehub-terminal-controls-collapsed";

function readControlsCollapsed(): boolean {
  try {
    return localStorage.getItem(CONTROLS_COLLAPSED_STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

function isCoarsePointer(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;
}

/** SGR mouse-wheel reports, as xterm writes them to the PTY once tmux turns
 * mouse reporting on (`mouse on`). Button 64 = wheel up, 65 = wheel down. */
const WHEEL_UP_RE = /\x1b\[<64;/g;
const WHEEL_DOWN_RE = /\x1b\[<65;/g;

/** Keys a phone keyboard can't produce, sent as the raw bytes a real
 * terminal would. Shift+Tab is Claude Code's mode switch. */
const TOUCH_KEYS: { label: string; data: string; aria: string }[] = [
  { label: "Esc", data: "\x1b", aria: "Escape" },
  { label: "Tab", data: "\t", aria: "Tab" },
  { label: "⇧Tab", data: "\x1b[Z", aria: "Shift+Tab" },
  { label: "^C", data: "\x03", aria: "Ctrl+C" },
  { label: "↑", data: "\x1b[A", aria: "Up" },
  { label: "↓", data: "\x1b[B", aria: "Down" },
  { label: "←", data: "\x1b[D", aria: "Left" },
  { label: "→", data: "\x1b[C", aria: "Right" },
  { label: "⏎", data: "\r", aria: "Enter" },
];

function TerminalTouchInput({ send }: { send: (data: string) => void }) {
  const { t } = useTranslation("workspace");
  const [text, setText] = useState("");

  function submit() {
    if (text) {
      send(text);
      // Enter goes out as its own write: a TUI such as Claude Code reads a
      // single chunk of text + "\r" as a paste, where the "\r" becomes a
      // newline inside the prompt instead of submitting it.
      window.setTimeout(() => send("\r"), 60);
    } else {
      send("\r");
    }
    setText("");
  }

  return (
    <div className="shrink-0 space-y-1.5 border-t border-border bg-background p-1.5">
      <div className="flex gap-1 overflow-x-auto">
        {TOUCH_KEYS.map((key) => (
          <button
            key={key.aria}
            type="button"
            aria-label={key.aria}
            // Keeps focus (and the phone keyboard) in the textarea.
            onPointerDown={(e) => e.preventDefault()}
            onClick={() => send(key.data)}
            className="h-8 min-w-[2.5rem] shrink-0 rounded-md border border-border bg-muted px-2 font-mono text-xs text-foreground active:bg-accent"
          >
            {key.label}
          </button>
        ))}
      </div>
      <div className="flex items-end gap-1.5">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={t("terminal.touchInputPlaceholder")}
          // text-base: iOS zooms into inputs under 16px on focus.
          className="max-h-32 min-h-[40px] flex-1 resize-none rounded-md border border-border bg-muted/40 px-3 py-2 text-base outline-none focus:border-primary"
        />
        <button
          type="button"
          onPointerDown={(e) => e.preventDefault()}
          onClick={submit}
          aria-label={t("terminal.touchInputSend")}
          title={t("terminal.touchInputSend")}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground active:opacity-80"
        >
          <SendHorizontal className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function TerminalPane({ sessionId, command, cwd, active }: TerminalPaneProps) {
  const { t } = useTranslation("workspace");
  const containerRef = useRef<HTMLDivElement>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [touchDevice] = useState(isCoarsePointer);
  const [touchInput, setTouchInput] = useState(() => {
    if (!isCoarsePointer()) return false;
    try {
      return localStorage.getItem(TOUCH_INPUT_STORAGE_KEY) !== "0";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    try {
      if (touchDevice) localStorage.setItem(TOUCH_INPUT_STORAGE_KEY, touchInput ? "1" : "0");
    } catch {
      // private mode / blocked storage -- the toggle just won't persist
    }
    // While the bar is on, tapping the terminal must not raise the keyboard
    // on xterm's own textarea -- that is the input path that duplicates text.
    const textarea = termRef.current?.textarea;
    if (!textarea) return;
    if (touchInput) textarea.setAttribute("inputmode", "none");
    else textarea.removeAttribute("inputmode");
  }, [touchInput, touchDevice]);
  const [controlsCollapsed, setControlsCollapsed] = useState(readControlsCollapsed);
  useEffect(() => {
    try {
      localStorage.setItem(CONTROLS_COLLAPSED_STORAGE_KEY, controlsCollapsed ? "1" : "0");
    } catch {
      // blocked storage -- the toggle just won't persist
    }
  }, [controlsCollapsed]);
  // "Follow the output like the chat" (2026-09-26, Marcelo: "a barra de
  // rolagem vertical tem que funcionar igual ao chat ... ao mover, ela tem
  // que parar ... quando coloca no final retorna o automático ... um botão
  // no lado inferior direito para a última linha"). Following and pausing
  // are already done by whatever owns the scroll -- tmux copy-mode (entered
  // with -e, so it leaves by itself at the bottom) or a TUI with its own
  // mouse scrolling, like Claude Code. What the page lacked was knowing the
  // user had scrolled away, and a way back. Neither side reports a scroll
  // position, so it's counted from the wheel reports this terminal itself
  // sends: notches up minus notches down. Replaying that many notches down
  // lands exactly where the user left the bottom, for any of them.
  const wheelUpNotchesRef = useRef(0);
  const [scrolledAway, setScrolledAway] = useState(false);
  const trackWheelInput = (data: string) => {
    const up = data.match(WHEEL_UP_RE)?.length ?? 0;
    const down = data.match(WHEEL_DOWN_RE)?.length ?? 0;
    if (!up && !down) return;
    wheelUpNotchesRef.current = Math.max(0, wheelUpNotchesRef.current + up - down);
    setScrolledAway(wheelUpNotchesRef.current > 0);
  };
  const jumpToBottom = () => {
    const socket = wsRef.current;
    const term = termRef.current;
    if (socket?.readyState !== WebSocket.OPEN || !term) return;
    const notches = wheelUpNotchesRef.current;
    wheelUpNotchesRef.current = 0;
    setScrolledAway(false);
    if (notches <= 0) return;
    // Aim at the middle of the pane; a few extra notches absorb rounding
    // (extra wheel-downs at the bottom are no-ops in tmux and in TUIs).
    const col = Math.max(1, Math.floor(term.cols / 2));
    const row = Math.max(1, Math.floor(term.rows / 2));
    const data = `\x1b[<65;${col};${row}M`.repeat(notches + 3);
    socket.send(JSON.stringify({ type: "input", data }));
  };
  const touchInputRef = useRef(touchInput);
  touchInputRef.current = touchInput;
  const sendToPty = (data: string) => {
    // Typing while scrolled up in tmux copy-mode would be read as copy-mode
    // commands (vi keys), not text -- return to the live bottom first.
    if (wheelUpNotchesRef.current > 0) jumpToBottom();
    const socket = wsRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "input", data }));
  };
  const [fontSize, setFontSize] = useState<number>(getStoredFontSize);
  const [latestLink, setLatestLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const sendResize = (cols?: number, rows?: number) => {
    const term = termRef.current;
    const socket = wsRef.current;
    if (!term || socket?.readyState !== WebSocket.OPEN) return;
    const c = cols ?? term.cols;
    const r = rows ?? term.rows;
    if (c > 0 && r > 0) {
      socket.send(JSON.stringify({ type: "resize", cols: c, rows: r }));
    }
  };

  const handleCopy = async () => {
    const term = termRef.current;
    if (!term) return;
    const text = term.hasSelection()
      ? term.getSelection()
      : terminalBufferToText(term.buffer.active);
    const succeeded = await copyTerminalText(text);
    setCopied(succeeded);
    if (succeeded) window.setTimeout(() => setCopied(false), 1800);
  };

  const handleOpenLatestLink = () => {
    if (latestLink) window.open(latestLink, "_blank", "noopener,noreferrer");
  };

  const handleZoomIn = () => {
    setFontSize((prev) => {
      const next = Math.min(MAX_FONT_SIZE, prev + 1);
      try {
        localStorage.setItem(FONT_SIZE_STORAGE_KEY, next.toString());
      } catch {}
      if (termRef.current) {
        termRef.current.options.fontSize = next;
        fitAddonRef.current?.fit();
        sendResize();
      }
      return next;
    });
  };

  const handleZoomOut = () => {
    setFontSize((prev) => {
      const next = Math.max(MIN_FONT_SIZE, prev - 1);
      try {
        localStorage.setItem(FONT_SIZE_STORAGE_KEY, next.toString());
      } catch {}
      if (termRef.current) {
        termRef.current.options.fontSize = next;
        fitAddonRef.current?.fit();
        sendResize();
      }
      return next;
    });
  };

  const handleZoomReset = () => {
    setFontSize(() => {
      try {
        localStorage.setItem(FONT_SIZE_STORAGE_KEY, DEFAULT_FONT_SIZE.toString());
      } catch {}
      if (termRef.current) {
        termRef.current.options.fontSize = DEFAULT_FONT_SIZE;
        fitAddonRef.current?.fit();
        sendResize();
      }
      return DEFAULT_FONT_SIZE;
    });
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const openLink = (uri: string) => {
      window.open(uri, "_blank", "noopener,noreferrer");
    };
    const term = new Terminal({
      cursorBlink: true,
      fontSize: getStoredFontSize(),
      theme: { background: "#0a0a0f" },
      linkHandler: {
        activate: (_event, uri) => openLink(uri),
      },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    const webLinksAddon = new WebLinksAddon((_event, uri) => openLink(uri));
    term.loadAddon(webLinksAddon);
    term.open(container);
    // Typing straight into xterm with a phone keyboard: IME edits go out as
    // diffs instead of through xterm, which re-sent the whole line on "."
    // (see terminalImeInput.ts). term.input keeps them on the onData path.
    const detachImeInput = isCoarsePointer()
      ? attachTerminalImeInput(container, () => term.textarea, (data) => term.input(data, true))
      : null;

    // Touch scrolling (2026-09-26, Marcelo: "no terminal no celular ... a
    // barra de rolagem vertical dentro do display. Não estou conseguindo").
    // The history lives in tmux, not in xterm (tmux redraws the screen and
    // has `mouse on`, see host-bridge's terminal_ws): on a desktop the wheel
    // becomes a mouse-wheel sequence that tmux turns into copy-mode
    // scrolling. xterm never maps a finger drag to that, so on a phone
    // nothing scrolled. Replaying the drag as wheel events on xterm's own
    // screen element reuses exactly the desktop path -- tmux scrollback,
    // or xterm's own buffer when nothing is tracking the mouse.
    let touchLastY: number | null = null;
    let touchStartX = 0;
    let touchStartY = 0;
    let touchScrolling = false;
    let touchCarry = 0;
    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 1) {
        touchLastY = null;
        return;
      }
      touchLastY = touchStartY = event.touches[0].clientY;
      touchStartX = event.touches[0].clientX;
      touchScrolling = false;
      touchCarry = 0;
    };
    const onTouchMove = (event: TouchEvent) => {
      if (touchLastY === null || event.touches.length !== 1) return;
      const touch = event.touches[0];
      if (!touchScrolling) {
        const dx = Math.abs(touch.clientX - touchStartX);
        const dy = Math.abs(touch.clientY - touchStartY);
        if (dy < 8 || dy < dx) return; // a tap or a sideways swipe, not a scroll
        touchScrolling = true;
      }
      event.preventDefault();
      const screen = term.element?.querySelector(".xterm-screen");
      if (!screen) return;
      const rowHeight = screen.clientHeight / Math.max(term.rows, 1) || 16;
      touchCarry += touchLastY - touch.clientY;
      touchLastY = touch.clientY;
      // tmux scrolls several lines per wheel notch, so one notch per few
      // rows dragged keeps the text roughly under the finger. Line mode, not
      // pixels: xterm treats small pixel deltas as a trackpad and scales
      // them down to 30%, which swallowed most of the drag.
      const rowsPerNotch = 3;
      while (Math.abs(touchCarry) >= rowHeight * rowsPerNotch) {
        const sign = Math.sign(touchCarry);
        touchCarry -= sign * rowHeight * rowsPerNotch;
        screen.dispatchEvent(
          new WheelEvent("wheel", {
            deltaY: sign,
            deltaMode: WheelEvent.DOM_DELTA_LINE,
            clientX: touch.clientX,
            clientY: touch.clientY,
            bubbles: true,
            cancelable: true,
          })
        );
      }
    };
    const onTouchEnd = () => {
      touchLastY = null;
    };
    container.addEventListener("touchstart", onTouchStart, { passive: true });
    container.addEventListener("touchmove", onTouchMove, { passive: false });
    container.addEventListener("touchend", onTouchEnd);
    container.addEventListener("touchcancel", onTouchEnd);
    fitAddon.fit();
    fitAddonRef.current = fitAddon;
    termRef.current = term;
    // Same rule as the touch-input effect above, which ran before this
    // terminal existed on first mount.
    if (touchInputRef.current) term.textarea?.setAttribute("inputmode", "none");

    // Auto copy on text selection (copy-on-select) so whatever text
    // is selected with the mouse is immediately written to the clipboard
    term.onSelectionChange(() => {
      const selected = term.getSelection();
      if (selected && selected.trim().length > 0) {
        void navigator.clipboard?.writeText(selected).catch(() => {});
      }
    });

    // xterm.js's own keydown handling treats Ctrl+C/Ctrl+V as raw control
    // bytes (SIGINT / SYN) and calls preventDefault on them, which stops the
    // browser's native copy/paste from ever firing -- even though xterm
    // already has "copy"/"paste" DOM listeners wired up to do the right
    // thing with the selection/clipboard. Stepping out of the way for these
    // two combos (returning false skips xterm's own handling) lets the
    // browser's native copy/paste reach those listeners instead.
    // We also explicitly write to clipboard on Ctrl+C / Cmd+C when there's a selection.
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown" || (!event.ctrlKey && !event.metaKey)) return true;
      const key = event.key.toLowerCase();
      if (key === "c" && term.hasSelection()) {
        const text = term.getSelection();
        if (text) {
          void navigator.clipboard?.writeText(text).catch(() => {});
        }
        return false;
      }
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
    let pingTimer: ReturnType<typeof setInterval> | undefined;
    const PING_INTERVAL_MS = 25_000;

    function stopHeartbeat() {
      if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = undefined;
      }
    }

    function startHeartbeat(socket: WebSocket) {
      stopHeartbeat();
      pingTimer = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "ping" }));
        }
      }, PING_INTERVAL_MS);
    }

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
      params.set("cols", String(term.cols || 80));
      params.set("rows", String(term.rows || 24));
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
      wsRef.current = socket;

      // The PTY is read in fixed-size chunks on the host, so the DECRQM
      // sequence stripped below can land split across two WebSocket
      // messages. Hold back a trailing prefix that could still grow into a
      // full match (rather than writing it immediately) and prepend it to
      // the next message, so the strip below can't be defeated by an
      // unlucky chunk boundary.
      let pendingTail = "";
      let linkScanBuffer = "";
      socket.onmessage = (event) => {
        // Keepalive heartbeat pong reply: discard without writing to the terminal
        if (typeof event.data === "string" && (event.data === '{"type":"pong"}' || event.data === '{"type": "pong"}')) {
          return;
        }
        // @xterm/xterm 6.0.0's DECRQM handler (CSI ? Pm $ p, used by CLIs
        // like Antigravity's `agy` to probe synchronized-output support)
        // throws "r is not defined" inside its own minified bundle and
        // corrupts the parser for the rest of the session -- strip the
        // query before it ever reaches xterm's parser. The app being
        // probed just treats a missing reply as "unsupported", same as
        // without this fix's filtering.
        const raw = pendingTail + (event.data as string);
        linkScanBuffer = `${linkScanBuffer}${raw}`.slice(-16_384);
        const detectedLink = findLastHttpUrl(linkScanBuffer);
        if (detectedLink) setLatestLink(detectedLink);
        const partial = raw.match(/\x1b\[\??[0-9;]*\$?$/);
        const safeEnd = partial ? partial.index! : raw.length;
        pendingTail = raw.slice(safeEnd);
        const data = raw.slice(0, safeEnd).replace(/\x1b\[\??[0-9;]*\$p/g, "");
        term.write(data);
      };
      socket.onopen = () => {
        reconnectAttempt = 0;
        fitAddon.fit();
        socket.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        startHeartbeat(socket);
      };
      // Fires for both a clean server-initiated close and a dropped
      // connection alike (WebSocket has no reliable way to tell them
      // apart) -- always attempt to reconnect unless this effect itself is
      // tearing down (`cancelled`, set right before the deliberate
      // `ws?.close()` in the cleanup below).
      socket.onclose = () => {
        stopHeartbeat();
        if (ws === socket) {
          ws = null;
          wsRef.current = null;
        }
        if (!cancelled) scheduleReconnect();
      };
    }
    connect();

    const inputDisposable = term.onData((data) => {
      trackWheelInput(data);
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

    // Prevent native browser context menu so the terminal's native/tmux menu is displayed;
    // if text is selected, right-click copies it to clipboard
    const handleContextMenu = (event: MouseEvent) => {
      const selectedText = prepareTerminalContextMenu(
        event,
        term.hasSelection() ? term.getSelection() : "",
      );
      if (selectedText) {
        void navigator.clipboard?.writeText(selectedText).catch(() => {});
      }
    };
    container.addEventListener("contextmenu", handleContextMenu);

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
      stopHeartbeat();
      wsRef.current = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      inputDisposable.dispose();
      detachImeInput?.();
      container.removeEventListener("contextmenu", handleContextMenu);
      container.removeEventListener("paste", handlePaste, true);
      container.removeEventListener("dragover", handleDragOver);
      container.removeEventListener("drop", handleDrop);
      container.removeEventListener("touchstart", onTouchStart);
      container.removeEventListener("touchmove", onTouchMove);
      container.removeEventListener("touchend", onTouchEnd);
      container.removeEventListener("touchcancel", onTouchEnd);
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
    if (term) {
      term.refresh(0, term.rows - 1);
      sendResize();
    }
  }, [active]);

  return (
    <div className="relative flex h-full w-full flex-col group">
      {/* Terminal controls (copy, link, zoom, typing bar, help) --
          collapsible so they don't cover the output in the corner. */}
      <div
        // Always fully opaque: a faded toggle relied on hover to become
        // readable, and a phone has no hover -- on the black terminal in the
        // dark theme the collapsed button all but disappeared.
        className="absolute right-3 top-2 z-10 flex items-center gap-1 rounded-md border border-border bg-muted px-1 py-0.5 shadow-md"
      >
        <button
          type="button"
          onClick={() => setControlsCollapsed((v) => !v)}
          className="flex h-6 w-6 items-center justify-center rounded text-foreground hover:bg-accent"
          title={controlsCollapsed ? t("terminal.showControls") : t("terminal.hideControls")}
          aria-label={controlsCollapsed ? t("terminal.showControls") : t("terminal.hideControls")}
          aria-expanded={!controlsCollapsed}
        >
          {controlsCollapsed ? <SlidersHorizontal className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        {!controlsCollapsed && (
        <>
        <div className="mx-0.5 h-4 w-px bg-border/70" aria-hidden="true" />
        <button
          type="button"
          onClick={() => void handleCopy()}
          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
          title={t("terminal.copyHelp")}
          aria-label={t("terminal.copy")}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
        </button>

        <button
          type="button"
          onClick={handleOpenLatestLink}
          disabled={!latestLink}
          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
          title={latestLink ? t("terminal.openLatestLink") : t("terminal.noLinkDetected")}
          aria-label={t("terminal.openLatestLink")}
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </button>

        <div className="mx-0.5 h-4 w-px bg-border/70" aria-hidden="true" />

        <button
          type="button"
          onClick={handleZoomOut}
          disabled={fontSize <= MIN_FONT_SIZE}
          className="flex h-6 w-6 items-center justify-center rounded hover:bg-accent text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
          title={t("terminal.zoomOutTitle")}
          aria-label={t("terminal.zoomOut")}
        >
          <Minus className="h-3.5 w-3.5" />
        </button>

        <button
          type="button"
          onClick={handleZoomReset}
          className="px-1.5 py-0.5 text-[11px] font-mono font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded"
          title={t("terminal.zoomReset", { size: fontSize, defaultSize: DEFAULT_FONT_SIZE })}
        >
          {fontSize}px
        </button>

        <button
          type="button"
          onClick={handleZoomIn}
          disabled={fontSize >= MAX_FONT_SIZE}
          className="flex h-6 w-6 items-center justify-center rounded hover:bg-accent text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
          title={t("terminal.zoomInTitle")}
          aria-label={t("terminal.zoomIn")}
        >
          <Plus className="h-3.5 w-3.5" />
        </button>

        <div className="mx-0.5 h-4 w-px bg-border/70" aria-hidden="true" />

        {touchDevice && (
          <button
            type="button"
            // Open AND close (2026-09-28, Marcelo: "adicionar nesse botão de
            // teclado a função de abrir e fechar"). With the bar open its
            // textarea has focus and the phone keyboard is up; without this,
            // the tap blurs the textarea first, the keyboard drops, the
            // layout jumps and the click lands elsewhere -- the bar could
            // be opened here but never closed. Same trick as the bar's keys.
            onPointerDown={(e) => e.preventDefault()}
            onClick={() => {
              if (touchInput && document.activeElement instanceof HTMLElement) {
                document.activeElement.blur(); // closing also drops the phone keyboard
              }
              setTouchInput((v) => !v);
            }}
            className={`flex h-6 w-6 items-center justify-center rounded hover:bg-accent ${touchInput ? "text-primary" : "text-muted-foreground"}`}
            title={touchInput ? t("terminal.touchInputClose") : t("terminal.touchInputOpen")}
            aria-label={touchInput ? t("terminal.touchInputClose") : t("terminal.touchInputOpen")}
            aria-pressed={touchInput}
          >
            {touchInput ? <KeyboardOff className="h-3.5 w-3.5" /> : <Keyboard className="h-3.5 w-3.5" />}
          </button>
        )}

        <details className="group/help relative">
          <summary
            className="flex h-6 w-6 cursor-pointer list-none items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground [&::-webkit-details-marker]:hidden"
            title={t("terminal.help.title")}
            aria-label={t("terminal.help.title")}
          >
            <HelpCircle className="h-3.5 w-3.5" />
          </summary>
          <div className="absolute right-0 top-8 z-20 w-80 rounded-lg border border-border bg-card p-3 text-card-foreground shadow-xl">
            <p className="mb-2 text-xs font-semibold">{t("terminal.help.title")}</p>
            <div className="space-y-1.5 text-[11px] leading-4">
              {[
                [t("terminal.help.selectShortcut"), t("terminal.help.select")],
                ["Ctrl + C", t("terminal.help.copy")],
                ["Ctrl + V", t("terminal.help.paste")],
                [t("terminal.help.linkButton"), t("terminal.help.openLink")],
                ["Ctrl + B, %", t("terminal.help.splitVertical")],
                ['Ctrl + B, "', t("terminal.help.splitHorizontal")],
                ["Ctrl + B, ← ↑ ↓ →", t("terminal.help.changePane")],
                ["Ctrl + B, z", t("terminal.help.zoomPane")],
                ["Ctrl + B, x", t("terminal.help.closePane")],
                [t("terminal.help.closeTabButton"), t("terminal.help.detach")],
              ].map(([shortcut, description]) => (
                <div key={`${shortcut}-${description}`} className="grid grid-cols-[7.25rem_1fr] items-start gap-2">
                  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground">
                    {shortcut}
                  </kbd>
                  <span className="pt-0.5 text-muted-foreground">{description}</span>
                </div>
              ))}
            </div>
          </div>
        </details>
        </>
        )}
      </div>

      <div className="relative min-h-0 w-full flex-1">
        <div ref={containerRef} className="h-full w-full" />
        {scrolledAway && <JumpToBottomButton onClick={jumpToBottom} />}
      </div>
      {touchInput && <TerminalTouchInput send={sendToPty} />}
    </div>
  );
}
