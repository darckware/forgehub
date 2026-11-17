/**
 * "Há uma nova versão do ForgeHub" (MSG-052, 2026-11-16, Marcelo: aviso).
 *
 * A tab opened before a deploy keeps running the old bundle, and its Zod
 * schemas reject a value the new backend started sending (`waiting_quota`
 * took the whole Messages inbox down on 2026-11-14 until a reload). Instead of
 * loosening every schema, the page notices that it is outdated and asks for a
 * reload. The signal is the hashed entry script: Vite names it after its
 * content, and nginx serves index.html with no-cache, so a different entry in
 * a fresh index.html means a new build is live. No build id, no extra file.
 * In `vite dev` there is no hashed entry, so this never fires there.
 */
const ENTRY_SELECTOR = 'script[type="module"][src*="/assets/"]';

export function entryOf(doc: Document, base: string = window.location.href): string | null {
  const src = doc.querySelector<HTMLScriptElement>(ENTRY_SELECTOR)?.getAttribute("src");
  return src ? new URL(src, base).pathname : null;
}

export function entryFromHtml(html: string): string | null {
  return entryOf(new DOMParser().parseFromString(html, "text/html"));
}

/** True only when both entries are known and differ; any failure is "no". */
export async function isNewVersionAvailable(fetchImpl: typeof fetch = fetch): Promise<boolean> {
  const current = entryOf(document);
  if (!current) return false;
  try {
    const response = await fetchImpl("/index.html", { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) return false;
    const latest = entryFromHtml(await response.text());
    return latest !== null && latest !== current;
  } catch {
    return false;
  }
}

const listeners = new Set<() => void>();

/** Ask for an immediate check, e.g. when a response no longer fits a schema. */
export function requestVersionCheck(): void {
  listeners.forEach((listener) => listener());
}

export function onVersionCheckRequest(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
