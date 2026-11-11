/** The byte a real terminal sends for Ctrl + `char`, or null when Ctrl
 * doesn't change that character. Letters map to 0x01-0x1a (either case),
 * the punctuation keys to the rest of C0, `?` to DEL -- the same table
 * xterm and every VT100 descendant use. Used by the phone bar's sticky Ctrl
 * key, where the next typed character arrives as text, not as a keydown. */
export function ctrlByte(char: string): string | null {
  if (char.length !== 1) return null;
  const code = char.charCodeAt(0);
  if (code >= 0x61 && code <= 0x7a) return String.fromCharCode(code - 0x60); // a-z
  if (code >= 0x40 && code <= 0x5f) return String.fromCharCode(code - 0x40); // @ A-Z [ \ ] ^ _
  if (char === " ") return "\x00";
  if (char === "?") return "\x7f";
  return null;
}
