import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Bot,
  Camera,
  ChevronDown,
  ExternalLink,
  Globe,
  Loader2,
  MousePointer2,
  Package,
  Plus,
  RefreshCw,
  Wand2,
  Workflow,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MacroInstructionsPanel } from "@/components/MacroInstructionsPanel";
import { WebAutomationPanel } from "@/components/WebAutomationPanel";
import type { Product } from "@/hooks/useProduct";
import {
  type AutomationTarget,
  useBackWorkspaceBrowser,
  useCreateStandaloneApp,
  useNavigateWorkspaceBrowser,
  useReloadWorkspaceBrowser,
  useStandaloneApps,
  useStartWorkspaceBrowser,
  useWorkspaceBrowserPointer,
  useWorkspaceBrowserScroll,
  useWorkspaceBrowserState,
} from "@/hooks/useWorkspaceBrowser";

interface WebAppPaneProps {
  url: string;
  products: Product[];
  onUrlChange: (url: string) => void;
}

const TARGET_MODE_KEY = "forgehub-webapp-target-mode";
const TARGET_PRODUCT_KEY = "forgehub-webapp-target-product";
const TARGET_APP_KEY = "forgehub-webapp-target-app";

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
export function WebAppPane({ url, products, onUrlChange }: WebAppPaneProps) {
  const state = useWorkspaceBrowserState(true);
  const start = useStartWorkspaceBrowser();
  const navigate = useNavigateWorkspaceBrowser();
  const pointer = useWorkspaceBrowserPointer();
  const scroll = useWorkspaceBrowserScroll();
  const reload = useReloadWorkspaceBrowser();
  const back = useBackWorkspaceBrowser();
  const { data: standaloneApps = [] } = useStandaloneApps();
  const createApp = useCreateStandaloneApp();

  const [draftUrl, setDraftUrl] = useState(url);
  const [invalidUrl, setInvalidUrl] = useState(false);
  const [missingTargetUrl, setMissingTargetUrl] = useState(false);
  const [automationsOpen, setAutomationsOpen] = useState(false);
  const [macroOpen, setMacroOpen] = useState(false);
  const [addAppOpen, setAddAppOpen] = useState(false);
  const [newAppName, setNewAppName] = useState("");
  const [newAppUrl, setNewAppUrl] = useState("");
  const pointerStart = useRef<{ x: number; y: number } | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [cursorPosition, setCursorPosition] = useState<{ left: number; top: number } | null>(null);
  const lastPointer = state.data?.last_pointer;

  const [targetMode, setTargetMode] = useState<"product" | "app">(
    () => (localStorage.getItem(TARGET_MODE_KEY) as "product" | "app" | null) ?? "product"
  );
  const [targetProductId, setTargetProductId] = useState(() => localStorage.getItem(TARGET_PRODUCT_KEY) ?? "");
  const [targetAppId, setTargetAppId] = useState(() => localStorage.getItem(TARGET_APP_KEY) ?? "");

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

  useEffect(() => {
    if (products.length === 0 || targetProductId) return;
    const fallback = products.find((product) => product.name.trim().toLowerCase() === "forgehub") ?? products[0];
    setTargetProductId(fallback.id);
  }, [products, targetProductId]);

  useEffect(() => { localStorage.setItem(TARGET_MODE_KEY, targetMode); }, [targetMode]);
  useEffect(() => { if (targetProductId) localStorage.setItem(TARGET_PRODUCT_KEY, targetProductId); }, [targetProductId]);
  useEffect(() => { if (targetAppId) localStorage.setItem(TARGET_APP_KEY, targetAppId); }, [targetAppId]);

  function downloadScreenshot() {
    if (!state.data?.image_base64) return;
    const link = document.createElement("a");
    link.href = `data:image/jpeg;base64,${state.data.image_base64}`;
    link.download = `workspace-browser-${new Date().toISOString().replace(/[:.]/g, "-")}.jpg`;
    link.click();
  }

  function go(value: string) {
    const normalized = normalizeUrl(value);
    if (!normalized) {
      setInvalidUrl(true);
      return;
    }
    setInvalidUrl(false);
    navigate.mutate({ url: normalized });
  }

  const selectedProduct = products.find((product) => product.id === targetProductId);
  const selectedApp = standaloneApps.find((app) => app.id === targetAppId);
  const target: AutomationTarget | undefined =
    targetMode === "product" && selectedProduct
      ? { type: "product", id: selectedProduct.id }
      : targetMode === "app" && selectedApp
        ? { type: "app", id: selectedApp.id }
        : undefined;
  const targetName = targetMode === "product" ? selectedProduct?.name : selectedApp?.name;

  function selectProduct(productId: string) {
    setTargetProductId(productId);
    const product = products.find((item) => item.id === productId);
    if (!product?.application_url) {
      setMissingTargetUrl(true);
      return;
    }
    setMissingTargetUrl(false);
    go(product.application_url);
  }

  function selectApp(appId: string) {
    setTargetAppId(appId);
    const app = standaloneApps.find((item) => item.id === appId);
    if (!app) return;
    setMissingTargetUrl(false);
    go(app.url);
  }

  function saveNewApp() {
    if (!newAppName.trim() || !newAppUrl.trim()) return;
    createApp.mutate(
      { name: newAppName.trim(), url: newAppUrl.trim() },
      {
        onSuccess: (app) => {
          setNewAppName("");
          setNewAppUrl("");
          setAddAppOpen(false);
          selectApp(app.id);
        },
      }
    );
  }

  const busy = start.isPending || navigate.isPending || pointer.isPending || reload.isPending || back.isPending;
  const error = state.error ?? start.error ?? navigate.error ?? pointer.error;
  const currentUrl = state.data?.url ?? url;

  return (
    <div className="absolute inset-0 flex min-h-0 bg-muted/20 p-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-1.5 rounded-t-md border border-b-0 border-border bg-background p-1.5">
          <div className="flex items-center gap-1">
            <Button size="icon" variant="outline" className="h-8 w-8" title="Back" onClick={() => back.mutate({})}>
              <ArrowLeft className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" title="Reload" onClick={() => reload.mutate({})}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="flex items-center rounded-md border border-input p-0.5">
            <Button
              size="icon" variant={targetMode === "product" ? "default" : "ghost"} className="h-7 w-7"
              title="Product" onClick={() => setTargetMode("product")}
            >
              <Package className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="icon" variant={targetMode === "app" ? "default" : "ghost"} className="h-7 w-7"
              title="Standalone app" onClick={() => setTargetMode("app")}
            >
              <Globe className="h-3.5 w-3.5" />
            </Button>
          </div>

          {targetMode === "product" ? (
            <div className="relative">
              <select
                aria-label="Selected product application"
                value={targetProductId}
                className="h-8 max-w-56 appearance-none rounded-md border border-input bg-background py-1 pl-3 pr-8 text-sm font-medium"
                onChange={(event) => selectProduct(event.target.value)}
              >
                {products.length === 0 && <option value="">No products registered</option>}
                {products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground" />
            </div>
          ) : (
            <>
              <div className="relative">
                <select
                  aria-label="Selected standalone app"
                  value={targetAppId}
                  className="h-8 max-w-56 appearance-none rounded-md border border-input bg-background py-1 pl-3 pr-8 text-sm font-medium"
                  onChange={(event) => selectApp(event.target.value)}
                >
                  {standaloneApps.length === 0 && <option value="">No standalone apps registered</option>}
                  {standaloneApps.map((app) => <option key={app.id} value={app.id}>{app.name}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground" />
              </div>
              <Button size="icon" variant="outline" className="h-8 w-8" title="Add standalone app" onClick={() => setAddAppOpen((v) => !v)}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
          {missingTargetUrl && selectedProduct && (
            <span className="text-xs text-destructive">Configure the application URL for {selectedProduct.name} in Products.</span>
          )}

          <form className="flex min-w-56 flex-1" onSubmit={(event) => { event.preventDefault(); go(draftUrl); }}>
            <input
              value={draftUrl}
              aria-label="Shared browser URL"
              className={`h-8 w-full rounded-md border bg-background px-2 font-mono text-xs outline-none focus:ring-1 focus:ring-ring ${invalidUrl ? "border-destructive" : "border-input"}`}
              onChange={(event) => setDraftUrl(event.target.value)}
            />
          </form>
          <div className="flex items-center gap-1">
            <Button size="icon" variant="outline" className="h-8 w-8" title="Automations" disabled={!target} onClick={() => setAutomationsOpen(true)}>
              <Workflow className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" title="Macro" disabled={!target} onClick={() => setMacroOpen(true)}>
              <Wand2 className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" title="Save screenshot" disabled={!state.data?.image_base64} onClick={downloadScreenshot}>
              <Camera className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="outline" className="h-8 w-8" title="Open externally" onClick={() => window.open(currentUrl, "_blank", "noopener,noreferrer")}>
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {addAppOpen && targetMode === "app" && (
          <div className="flex items-center gap-2 border border-b-0 border-t-0 border-border bg-background p-2">
            <Input className="h-8 max-w-48 text-xs" placeholder="App name" value={newAppName} onChange={(e) => setNewAppName(e.target.value)} />
            <Input className="h-8 flex-1 font-mono text-xs" placeholder="https://example.com" value={newAppUrl} onChange={(e) => setNewAppUrl(e.target.value)} />
            <Button size="sm" disabled={!newAppName.trim() || !newAppUrl.trim() || createApp.isPending} onClick={saveNewApp}>
              {createApp.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Add"}
            </Button>
            <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setAddAppOpen(false)}><X className="h-3.5 w-3.5" /></Button>
          </div>
        )}

        <div
          className={`relative min-h-0 flex-1 overscroll-contain overflow-hidden border bg-zinc-950 transition-shadow ${
            state.data?.control_owner === "agent"
              ? "border-amber-400/70 shadow-[inset_0_0_0_2px_rgba(251,191,36,0.35),0_0_18px_rgba(251,191,36,0.35)]"
              : "border-border"
          }`}
        >
          {state.data?.control_owner === "agent" && (
            <span className="absolute left-2 top-2 z-10 flex items-center gap-1.5 rounded-full bg-amber-400/90 px-2.5 py-1 text-[11px] font-medium text-amber-950 shadow">
              <Bot className="h-3 w-3" /> Agent in control
            </span>
          )}
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
          {cursorPosition && lastPointer && state.data?.control_owner === "agent" && (
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

      {automationsOpen && target && targetName && (
        <WebAutomationPanel target={target} targetName={targetName} onClose={() => setAutomationsOpen(false)} />
      )}

      {macroOpen && target && targetName && (
        <MacroInstructionsPanel target={target} targetName={targetName} onClose={() => setMacroOpen(false)} />
      )}
    </div>
  );
}
