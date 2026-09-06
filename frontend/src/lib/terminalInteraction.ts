export interface TerminalBufferLineLike {
  readonly isWrapped: boolean;
  translateToString(trimRight?: boolean): string;
}

export interface TerminalBufferLike {
  readonly length: number;
  getLine(index: number): TerminalBufferLineLike | undefined;
}

const HTTP_URL_PATTERN = /https?:\/\/[^\s\x00-\x1f"'<>]+/gi;

export function findLastHttpUrl(text: string): string | null {
  const matches = text.match(HTTP_URL_PATTERN);
  if (!matches?.length) return null;
  return matches[matches.length - 1].replace(/[),.;!?]+$/, "");
}

export function terminalBufferToText(buffer: TerminalBufferLike): string {
  const logicalLines: string[] = [];

  for (let index = 0; index < buffer.length; index += 1) {
    const line = buffer.getLine(index);
    if (!line) continue;
    const text = line.translateToString(true);
    if (line.isWrapped && logicalLines.length > 0) {
      logicalLines[logicalLines.length - 1] += text;
    } else {
      logicalLines.push(text);
    }
  }

  return logicalLines.join("\n").trimEnd();
}

export async function copyTerminalText(text: string): Promise<boolean> {
  if (!text) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through for HTTP/non-secure contexts and denied permissions.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand?.("copy") ?? false;
  textarea.remove();
  return copied;
}
