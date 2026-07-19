import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, GitBranchPlus, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useAssistantStore } from "@/store/assistantStore";
import { useProducts } from "@/hooks/useProduct";
import { useBlueprint, useBlueprintGraph, useCreateBlueprintRevision } from "@/hooks/useSystemScope";
import { FAMILY_TYPES, RELATION_TYPES, SystemMapCanvas } from "./SystemMapCanvas";

const PASTE_EXAMPLE = JSON.stringify({
  elements: [
    { key: "e1", family: "process", element_type: "journey", name: "Fazer login" },
    { key: "e2", family: "experience", element_type: "screen", name: "Tela de Login" },
    { key: "e3", family: "interface", element_type: "api", name: "api de login" },
  ],
  relations: [
    { from: "e1", to: "e2", relation_type: "contains" },
    { from: "e2", to: "e3", relation_type: "invokes" },
  ],
}, null, 2);

/** Context attached invisibly to the assistant chat (assistantStore's
 * pendingHiddenContext) -- summarizes the current map + valid vocabulary so
 * the assistant can suggest concrete elements/relations to add. It never
 * calls the mutation endpoints itself; the user still drags/connects, or
 * pastes (Ctrl+V) a JSON flow the assistant wrote out, which the canvas
 * validates and creates through the exact same code path (see
 * SystemMapCanvas.tsx's validateClipboardPayload/importPayload). */
function buildSystemMapContext(
  productName: string,
  status: string | undefined,
  graph: ReturnType<typeof useBlueprintGraph>["data"],
): string {
  const elementsByFamily = Object.entries(
    (graph?.elements ?? []).reduce<Record<string, string[]>>((all, item) => {
      (all[item.element.family] ??= []).push(`${item.element.name} (${item.element.element_type}, ${item.element.stable_key})`);
      return all;
    }, {})
  );
  const relations = (graph?.relations ?? []).map((r) => `${r.from_element_id} --${r.relation_type}--> ${r.to_element_id}`);
  return [
    `System Map for product "${productName}" (blueprint revision status: ${status ?? "unknown"}).`,
    "",
    "Current elements by layer:",
    elementsByFamily.length
      ? elementsByFamily.map(([family, items]) => `- ${family}: ${items.join(", ")}`).join("\n")
      : "(none yet)",
    "",
    "Current relations:",
    relations.length ? relations.map((r) => `- ${r}`).join("\n") : "(none yet)",
    "",
    `Valid layers and their element types: ${Object.entries(FAMILY_TYPES).map(([family, types]) => `${family} [${types.join(", ")}]`).join("; ")}.`,
    `Valid relation types: ${RELATION_TYPES.join(", ")}.`,
    "",
    "Help me decide which elements and dependency links to add. I can drag a layer chip from the toolbar onto the canvas to create one element at a time, and drag between two elements to connect them.",
    "",
    "For a whole flow at once: when I ask you to design a flow, reply with ONLY a fenced json code block in this exact shape (no other text in that block) -- I'll copy it and paste it (Ctrl+V) directly onto the canvas, which creates every element and relation in one go:",
    "```json",
    PASTE_EXAMPLE,
    "```",
    "Rules: `key` is a short local id only used to wire `relations` together (not saved anywhere); `family`/`element_type` must come from the valid layers list above; `relation_type` must come from the valid relation types list; omit `position` (the canvas lays elements out automatically); omit `stable_key` (auto-generated from the name).",
  ].join("\n");
}

export default function SystemMapPage() {
  const { t } = useTranslation("systemMap");
  const [params, setParams] = useSearchParams();
  const products = useProducts();
  const productId = params.get("product") || "";
  const blueprint = useBlueprint(productId);
  const revisionId = blueprint.data?.current_revision?.id;
  const graph = useBlueprintGraph(revisionId);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingHiddenContext = useAssistantStore((s) => s.setPendingHiddenContext);
  const createRevision = useCreateBlueprintRevision();

  const readOnly = blueprint.data?.current_revision?.status !== "draft";
  // Only safe once delivery has actually been authorized off this revision
  // (product_version_id gets set at that moment) -- creating a new revision
  // any earlier (mid-review, or approved-but-undelivered) would move
  // blueprint.current_revision_id out from under the pending governance
  // decision / :authorize-delivery-planning check, which both key off
  // "whatever is current" rather than the specific revision being decided.
  const canStartNewRevision = blueprint.data?.current_revision?.status === "approved"
    && Boolean(blueprint.data?.current_revision?.product_version_id);

  function openAssistantHelp() {
    const product = products.data?.find((p) => p.id === productId);
    setPendingHiddenContext(buildSystemMapContext(product?.name ?? "", blueprint.data?.current_revision?.status, graph.data));
    setAssistantOpen(true);
  }

  function startNewRevision() {
    createRevision.mutate({ productId, cloneFromRevisionId: revisionId });
  }

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold">{t("page.title")}</h1><p className="text-sm text-muted-foreground">{t("page.description")}</p></div>
      {productId && blueprint.data && (
        <Button size="sm" variant="outline" className="gap-1.5" onClick={openAssistantHelp}>
          <Bot className="h-4 w-4" /> {t("canvas.assistantHelp")}
        </Button>
      )}
    </div>
    <Card><CardContent className="pt-6"><Label>{t("productSelect.label")}</Label><Select value={productId} onChange={e => setParams(e.target.value ? {product:e.target.value} : {})}><option value="">{t("productSelect.placeholder")}</option>{products.data?.map(p => <option key={p.id} value={p.id}>{p.name} · {p.status}</option>)}</Select></CardContent></Card>
    {productId && blueprint.data && <>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardDescription>{t("detailCards.map")}</CardDescription><CardTitle className="text-lg">{blueprint.data.blueprint.name}</CardTitle></CardHeader></Card>
        <Card>
          <CardHeader>
            <CardDescription>{t("detailCards.revision")}</CardDescription>
            <CardTitle className="text-lg">#{blueprint.data.current_revision?.revision} <Badge variant="outline">{blueprint.data.current_revision?.status}</Badge></CardTitle>
          </CardHeader>
          {canStartNewRevision && (
            <CardContent className="pt-0">
              <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={startNewRevision} disabled={createRevision.isPending}>
                {createRevision.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranchPlus className="h-4 w-4" />}
                {t("detailCards.newRevision")}
              </Button>
            </CardContent>
          )}
        </Card>
        <Card><CardHeader><CardDescription>{t("detailCards.coverage")}</CardDescription><CardTitle className="text-lg">{graph.data?.elements.length || 0} elements · {graph.data?.relations.length || 0} links</CardTitle></CardHeader></Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{t("scopeGraph.title")}</CardTitle>
          <CardDescription>{t("scopeGraph.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          {revisionId && <SystemMapCanvas revisionId={revisionId} graph={graph.data} isLoading={graph.isLoading} readOnly={readOnly} />}
        </CardContent>
      </Card>
    </>}
  </div>;
}
