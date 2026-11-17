import { afterEach, describe, expect, it, vi } from "vitest";
import { entryFromHtml, isNewVersionAvailable, onVersionCheckRequest, requestVersionCheck } from "@/lib/appVersion";

const page = (entry: string) =>
  `<!doctype html><html><head><script type="module" crossorigin src="${entry}"></script></head><body></body></html>`;
const respond = (body: string, ok = true) => vi.fn().mockResolvedValue({ ok, text: () => Promise.resolve(body) }) as unknown as typeof fetch;

function loadEntry(entry: string | null) {
  document.head.querySelectorAll("script").forEach((el) => el.remove());
  if (entry) {
    const script = document.createElement("script");
    script.type = "module";
    script.setAttribute("src", entry);
    document.head.appendChild(script);
  }
}

afterEach(() => loadEntry(null));

describe("appVersion (MSG-052)", () => {
  it("reads the hashed entry of an index.html", () => {
    expect(entryFromHtml(page("/assets/index-abc123.js"))).toBe("/assets/index-abc123.js");
    expect(entryFromHtml("<html><body>no script</body></html>")).toBeNull();
  });

  it("reports a new version only when the live entry differs", async () => {
    loadEntry("/assets/index-old.js");
    expect(await isNewVersionAvailable(respond(page("/assets/index-new.js")))).toBe(true);
    expect(await isNewVersionAvailable(respond(page("/assets/index-old.js")))).toBe(false);
  });

  it("never claims a new version on failure or in vite dev", async () => {
    loadEntry("/assets/index-old.js");
    expect(await isNewVersionAvailable(respond("", false))).toBe(false);
    expect(await isNewVersionAvailable(vi.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch)).toBe(false);
    expect(await isNewVersionAvailable(respond("<html></html>"))).toBe(false);
    loadEntry("/src/main.tsx");
    const fetchSpy = respond(page("/assets/index-new.js"));
    expect(await isNewVersionAvailable(fetchSpy)).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards check requests to listeners until unsubscribed", () => {
    const listener = vi.fn();
    const off = onVersionCheckRequest(listener);
    requestVersionCheck();
    off();
    requestVersionCheck();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
