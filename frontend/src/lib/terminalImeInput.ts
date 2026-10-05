/** Phone keyboards typing straight into xterm.js (2026-10-04, Marcelo: "quando
 * clica no teclado ponto ele está duplicando o texto digitado").
 *
 * Gboard and other Android IMEs edit xterm's hidden textarea as a whole: on
 * "." (sent as keyCode 229, outside a composition) they also autocorrect the
 * word and rewrite the text before it. xterm's `_handleAnyTextareaChanges`
 * then diffs with `newValue.replace(oldValue, "")`, which only works when the
 * old value is an untouched prefix -- once the IME rewrote anything, it sends
 * the *whole* textarea again, and the line reaches the PTY twice.
 *
 * This bridge takes the textarea's IME events away from xterm on touch
 * devices and sends only the real edit: the common prefix of the old and new
 * value stays, every character after it is erased with DEL, and the new tail
 * is typed. An autocorrection therefore arrives as "backspace the word, type
 * the corrected one", exactly what the screen shows. Real keys the IME
 * reports with a proper keyCode (Enter, Backspace on an empty field, arrows)
 * still go through xterm's own key handling. */

const DEL = "\x7f";

/** Bytes that turn what the PTY already received (`previous`) into `next`. */
export function imeEditToPtyInput(previous: string, next: string): string {
  let prefix = 0;
  const max = Math.min(previous.length, next.length);
  while (prefix < max && previous[prefix] === next[prefix]) prefix += 1;
  const erased = Array.from(previous.slice(prefix)).length;
  return DEL.repeat(erased) + next.slice(prefix).replace(/\r?\n/g, "\r");
}

/** Wires the bridge onto `container` (the element xterm was opened in).
 * Listeners run in the capture phase on the container, i.e. before xterm's
 * own listeners on the textarea, and stop the events there. */
export function attachTerminalImeInput(
  container: HTMLElement,
  getTextarea: () => HTMLTextAreaElement | undefined,
  send: (data: string) => void,
): () => void {
  // What the PTY has received from the current textarea content.
  let sent = "";

  const isTerminalTextarea = (target: EventTarget | null) =>
    target instanceof HTMLTextAreaElement && target === getTextarea();

  const reset = () => {
    const textarea = getTextarea();
    if (textarea) textarea.value = "";
    sent = "";
  };

  const onInput = (event: Event) => {
    if (!isTerminalTextarea(event.target)) return;
    event.stopPropagation();
    const textarea = event.target as HTMLTextAreaElement;
    const value = textarea.value;
    const data = imeEditToPtyInput(sent, value);
    sent = value;
    if (data) send(data);
    // A line break already went out as "\r": start the next line clean,
    // or the IME would keep "correcting" a command that already ran.
    if (/\n/.test(value) && !(event as InputEvent).isComposing) reset();
  };

  const onComposition = (event: Event) => {
    if (!isTerminalTextarea(event.target)) return;
    // The edits themselves arrive as `input` events; xterm's composition
    // helper must not send its own copy at compositionend.
    event.stopPropagation();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (!isTerminalTextarea(event.target)) return;
    if (event.keyCode === 229 || event.key === "Unidentified" || event.isComposing) {
      // An IME edit -- `input` will carry it. Letting xterm see it is what
      // triggers the duplicating re-send.
      event.stopPropagation();
      return;
    }
    // A real key (Enter, Backspace, arrows, Tab...) is xterm's to send. The
    // textarea no longer mirrors the line after it, so start over.
    window.setTimeout(reset, 0);
  };

  container.addEventListener("input", onInput, true);
  container.addEventListener("compositionstart", onComposition, true);
  container.addEventListener("compositionupdate", onComposition, true);
  container.addEventListener("compositionend", onComposition, true);
  container.addEventListener("keydown", onKeyDown, true);
  return () => {
    container.removeEventListener("input", onInput, true);
    container.removeEventListener("compositionstart", onComposition, true);
    container.removeEventListener("compositionupdate", onComposition, true);
    container.removeEventListener("compositionend", onComposition, true);
    container.removeEventListener("keydown", onKeyDown, true);
  };
}
