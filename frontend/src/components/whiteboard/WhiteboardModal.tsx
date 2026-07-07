import { Suspense, lazy, useCallback, useRef } from "react";
import { Loader2, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";
import "@excalidraw/excalidraw/index.css";

// Excalidraw's bundle is large (canvas engine + fonts) -- lazy-loaded so
// pages that never open the whiteboard don't pay for it. MIT-licensed,
// actively maintained (excalidraw.com); adopted as a complementary library
// per SPEC §7 (self-contained modal widget, doesn't replace shadcn/Radix
// as the design system). The bundled mermaid-to-excalidraw conversion
// feature is not exposed anywhere in this integration.
const Excalidraw = lazy(() =>
  import("@excalidraw/excalidraw").then((m) => ({ default: m.Excalidraw }))
);

export interface WhiteboardSaveResult {
  pngBlob: Blob;
  sceneJson: string;
}

/**
 * Full-screen Excalidraw whiteboard. `initialData` reopens a previously
 * saved scene (see docs/index.tsx's "Editar na Lousa" for .excalidraw
 * files); `onSave` hands the parent a PNG export + the scene JSON so it
 * can upload both to /docs/assets and insert the image reference.
 */
export function WhiteboardModal({
  initialData,
  onClose,
  onSave,
}: {
  initialData?: ExcalidrawInitialDataState;
  onClose: () => void;
  onSave: (result: WhiteboardSaveResult) => void;
}) {
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null);

  const handleSave = useCallback(async () => {
    const api = apiRef.current;
    if (!api) return;
    const { exportToBlob } = await import("@excalidraw/excalidraw");
    const elements = api.getSceneElements();
    const appState = api.getAppState();
    const files = api.getFiles();
    const pngBlob = await exportToBlob({
      elements,
      appState: { ...appState, exportBackground: true },
      files,
      mimeType: "image/png",
      getDimensions: () => ({ width: 1600, height: 1200 }),
    });
    const sceneJson = JSON.stringify({
      type: "excalidraw",
      version: 2,
      source: "forgehub-docs",
      elements,
      appState: { viewBackgroundColor: appState.viewBackgroundColor },
      files,
    });
    onSave({ pngBlob, sceneJson });
  }, [onSave]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <p className="text-sm font-medium">🎨 Lousa</p>
        <div className="flex items-center gap-2">
          <Button size="sm" className="gap-1.5" onClick={handleSave}>
            <Save className="h-3.5 w-3.5" /> Salvar e inserir
          </Button>
          <Button variant="outline" size="sm" onClick={onClose}>
            <X className="mr-1.5 h-3.5 w-3.5" /> Fechar
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" /> Carregando a lousa…
            </div>
          }
        >
          <Excalidraw
            excalidrawAPI={(api) => {
              apiRef.current = api;
            }}
            initialData={initialData}
            theme={document.documentElement.classList.contains("dark") ? "dark" : "light"}
          />
        </Suspense>
      </div>
    </div>
  );
}
