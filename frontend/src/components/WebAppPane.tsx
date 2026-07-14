import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, ExternalLink, Loader2, MousePointer2, RefreshCw, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WebAutomationPanel } from "@/components/WebAutomationPanel";
import type { Product } from "@/hooks/useProduct";
import {
  useBackWorkspaceBrowser,
  useNavigateWorkspaceBrowser,
  useReloadWorkspaceBrowser,
  useStartWorkspaceBrowser,
  useWorkspaceBrowserPointer,
  useWorkspaceBrowserScroll,
  useWorkspaceBrowserState,
} from "@/hooks/useWorkspaceBrowser";

interface WebAppPaneProps {
  url: string;
  products: Product[];
  selectedProductId: string;
  onUrlChange: (url: string) => void;
  onProductChange: (productId: string) => void;
}

function normalizeUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function browserCoordinates(
  image: HTMLImageElement,
  clientX: number,
  clientY: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const bounds = image.getBoundingClientRect();
  const scale = Math.min(bounds.width / viewportWidth, bounds.height / viewportHeight);
  const offsetX = (bounds.width - viewportWidth * scale) / 2;
  const offsetY = (bounds.height - viewportHeight * scale) / 2;
  const x = (clientX - bounds.left - offsetX) / scale;
  const y = (clientY - bounds.top - offsetY) / scale;
  return x >= 0 && x <= viewportWidth && y >= 0 && y <= viewportHeight ? { x, y } : null;
}

/** Live view of the shared Chromium CDP session used by agent browser tools. */
export function WebAppPane({
  url,
  products,
  selectedProductId,
  onUrlChange,
  onProductChange,
}: WebAppPaneProps) {
  const state = useWorkspaceBrowserState(true);
  const start = useStartWorkspaceBrowser();
  const navigate = useNavigateWorkspaceBrowser();
  const pointer = useWorkspaceBrowserPointer();
  const scroll = useWorkspaceBrowserScroll();
  const reload = useReloadWorkspaceBrowser();
  const back = useBackWorkspaceBrowser();
  const [draftUrl, setDraftUrl] = useState(url);
  const [invalidUrl, setInvalidUrl] = useState(false);
  const [missingProductUrl, setMissingProductUrl] = useState(false);
  const [automationsOpen, setAutomationsOpen] = useState(false);
  const pointerStart = useRef<{ x: number; y: number } | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [cursorPosition, setCursorPosition] = useState<{ left: number; top: number } | null>(null);
  const lastPointer = state.data?.last_pointer;

  useLayoutEffect(() => {
    const image = imageRef.current;
    if (!image || !lastPointer || !state.data) {
      setCursorPosition(null);
      return;
    }
    const bounds = image.getBoundingClientRect();
    const viewportWidth = state.data.viewport_width || image.naturalWidth;
    const viewportHeight = state.data.viewport_height || image.naturalHeight;
    const scale = Math.min(bounds.width / viewportWidth, bounds.height / viewportHeight);
    const offsetX = (bounds.width - viewportWidth * scale) / 2;
    const offsetY = (bounds.height - viewportHeight * scale) / 2;
    setCursorPosition({ left: offsetX + lastPointer.x * scale, top: offsetY + lastPointer.y * scale });
  }, [lastPointer, state.data]);

  useEffect(() => {
    if (!state.data && !state.isFetching && !start.isPending) start.mutate({ url });
    if (state.data?.url === "about:blank" && url !== "about:blank" && !start.isPending) {
      start.mutate({ url });
    }
  }, [start, state.data, state.isFetching, url]);

  useEffect(() => {
    if (!state.data?.url) return;
    setDraftUrl(state.data.url);
    if (state.data.url !== url) onUrlChange(state.data.url);
  }, [onUrlChange, state.data?.url, url]);

  function go(value: string) {
    const normalized = normalizeUrl(value);
    if (!normalized) {
      setInvalidUrl(true);
      return;
    }
    setInvalidUrl(false);
    navigate.mutate({ url: normalized });
  }

  const busy = start.isPending || navigate.isPending || pointer.isPending || reload.isPending || back.isPending;
  const error = state.error ?? start.error ?? navigate.error ?? pointer.error;
  const currentUrl = state.data?.url ?? url;
  const selectedProduct = products.find((product) => product.id === selectedProductId);

  return (
    <div className="absolute inset-0 flex min-h-0 bg-muted/20 p-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-1.5 rounded-t-md border border-b-0 border-border bg-background p-1.5">
          <Button size="icon" variant="outline" className="h-8 w-8" title="Back" onClick={() => back.mutate({})}>
            <ArrowLeft className="h-3.5 w-3.5" />
          </Button>
          <div className="relative">
            <select
              aria-label="Selected product application"
              value={selectedProductId}
              className="h-8 max-w-56 appearance-none rounded-md border border-input bg-background py-1 pl-3 pr-8 text-sm font-medium"
              onChange={(event) => {
                const product = products.find((item) => item.id === event.target.value);
                if (!product) return;
                onProductChange(product.id);
                if (!product.application_url) {
                  setMissingProductUrl(true);
                  return;
                }
                setMissingProductUrl(false);
                go(product.application_url);
              }}
            >
              {products.length === 0 && <option value="">No products registered</option>}
              {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground" />
          </div>
          {missingProductUrl && selectedProduct && (
            <span className="text-xs text-destructive">Configure the application URL for {selectedProduct.name} in Products.</span>
          )}
          <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={!selectedProduct} onClick={() => setAutomationsOpen(true)}>
            <Workflow className="h-3.5 w-3.5" /> Automations
          </Button>
          <Button size="icon" variant="outline" className="h-8 w-8" title="Reload" onClick={() => reload.mutate({})}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <form className="flex min-w-56 flex-1" onSubmit={(event) => { event.preventDefault(); go(draftUrl); }}>
            <input
              value={draftUrl}
              aria-label="Shared browser URL"
              className={`h-8 w-full rounded-md border bg-background px-2 font-mono text-xs outline-none focus:ring-1 focus:ring-ring ${invalidUrl ? "border-destructive" : "border-input"}`}
              onChange={(event) => setDraftUrl(event.target.value)}
            />
          </form>
          <Button size="icon" variant="outline" className="h-8 w-8" title="Open externally" onClick={() => window.open(currentUrl, "_blank", "noopener,noreferrer")}>
            <ExternalLink className="h-3.5 w-3.5" />
          </Button>
        </div>

        <div className="relative min-h-0 flex-1 overscroll-contain overflow-hidden border border-border bg-zinc-950">
          {state.data?.image_base64 ? (
            <img
              ref={imageRef}
              src={`data:image/jpeg;base64,${state.data.image_base64}`}
              alt={`Shared browser showing ${currentUrl}`}
              draggable={false}
              className="h-full w-full cursor-default object-contain"
              onWheel={(event) => {
                event.preventDefault();
                if (scroll.isPending) return;
                const viewportWidth = state.data?.viewport_width ?? event.currentTarget.naturalWidth;
                const viewportHeight = state.data?.viewport_height ?? event.currentTarget.naturalHeight;
                const coordinates = browserCoordinates(
                  event.currentTarget,
                  event.clientX,
                  event.clientY,
                  viewportWidth,
                  viewportHeight,
                );
                if (!coordinates) return;
                const magnitude = Math.min(1_200, Math.max(120, Math.abs(event.deltaY)));
                scroll.mutate({ ...coordinates, delta_y: Math.sign(event.deltaY) * magnitude });
              }}
              onPointerDown={(event) => {
                const viewportWidth = state.data?.viewport_width ?? event.currentTarget.naturalWidth;
                const viewportHeight = state.data?.viewport_height ?? event.currentTarget.naturalHeight;
                pointerStart.current = browserCoordinates(
                  event.currentTarget,
                  event.clientX,
                  event.clientY,
                  viewportWidth,
                  viewportHeight,
                );
                if (pointerStart.current) event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerUp={(event) => {
                const startCoordinates = pointerStart.current;
                pointerStart.current = null;
                if (!startCoordinates) return;
                const viewportWidth = state.data?.viewport_width ?? event.currentTarget.naturalWidth;
                const viewportHeight = state.data?.viewport_height ?? event.currentTarget.naturalHeight;
                const endCoordinates = browserCoordinates(
                  event.currentTarget,
                  event.clientX,
                  event.clientY,
                  viewportWidth,
                  viewportHeight,
                );
                if (!endCoordinates) return;
                pointer.mutate({
                  ...startCoordinates,
                  end_x: endCoordinates.x,
                  end_y: endCoordinates.y,
                });
              }}
              onPointerCancel={() => { pointerStart.current = null; }}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-zinc-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting shared browser…
            </div>
          )}
          {busy && <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-white" />}
          {cursorPosition && lastPointer && (
            <div
              key={lastPointer.at}
              className="pointer-events-none absolute z-10 animate-agent-cursor"
              style={{ left: cursorPosition.left, top: cursorPosition.top }}
            >
              <span className="absolute inset-0 -m-2 rounded-full bg-amber-400/40 animate-ping" />
              <MousePointer2 className="relative h-5 w-5 fill-amber-400 text-amber-950 drop-shadow" />
            </div>
          )}
        </div>

        {error && <p className="px-2 py-1 text-xs text-destructive">{error.message}</p>}
      </div>

      {automationsOpen && selectedProduct && (
        <WebAutomationPanel productId={selectedProduct.id} productName={selectedProduct.name} onClose={() => setAutomationsOpen(false)} />
      )}

    </div>
  );
}
