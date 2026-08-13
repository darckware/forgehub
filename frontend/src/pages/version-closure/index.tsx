import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, GitBranch, Loader2, Package, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { useProducts, useProductVersions, usePublishProductVersion, useUpdateProductVersion } from "@/hooks/useProduct";
import { useProjects } from "@/hooks/useProject";
import { useTasks } from "@/hooks/useTask";

const TERMINAL_STATUSES = new Set(["done", "deployed", "cancelled"]);

interface BlockingTask { project_id: string; project_name: string; task_id: string; task_number: number; title: string; status: string }

function publishBlockingTasks(error: unknown): BlockingTask[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const body = error.body as { detail?: { blocking?: BlockingTask[] } } | undefined;
  return body?.detail?.blocking ?? null;
}

export default function VersionClosurePage() {
  const products = useProducts();
  const [productId, setProductId] = useState("");
  const versions = useProductVersions(productId);
  const [versionId, setVersionId] = useState("");
  useEffect(() => setVersionId(versions.data?.[0]?.id || ""), [versions.data]);
  const version = versions.data?.find((v) => v.id === versionId);

  const projects = useProjects();
  const tasks = useTasks();
  const publish = usePublishProductVersion();
  const updateVersion = useUpdateProductVersion();
  const [releaseNotes, setReleaseNotes] = useState("");
  useEffect(() => setReleaseNotes(version?.release_notes ?? ""), [version]);

  const versionProjects = useMemo(
    () => (projects.data ?? []).filter((p) => p.product_version_id === versionId),
    [projects.data, versionId]
  );
  const tasksByProject = useMemo(() => {
    const map = new Map<string, { total: number; done: number }>();
    for (const project of versionProjects) map.set(project.id, { total: 0, done: 0 });
    for (const task of tasks.data ?? []) {
      const bucket = task.project_id ? map.get(task.project_id) : undefined;
      if (!bucket) continue;
      bucket.total += 1;
      if (TERMINAL_STATUSES.has(task.status)) bucket.done += 1;
    }
    return map;
  }, [tasks.data, versionProjects]);

  const blocking = publishBlockingTasks(publish.error);

  const handlePublish = async () => {
    if (releaseNotes !== (version?.release_notes ?? "")) {
      await updateVersion.mutateAsync({ id: versionId, release_notes: releaseNotes });
    }
    publish.mutate(versionId);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><CheckCircle2 className="h-6 w-6" />Fechamento de Versão</h1>
        <p className="text-sm text-muted-foreground">
          Publicar trava edição de escopo/telas/planejamento dos Projects desta versão. Não completa
          trabalho automaticamente -- bloqueia se houver task pendente.
        </p>
      </div>

      <Card>
        <CardContent className="grid gap-4 pt-6 md:grid-cols-2">
          <div>
            <Label>Produto</Label>
            <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">Selecione um produto...</option>
              {products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div>
            <Label>Versão</Label>
            <Select value={versionId} onChange={(e) => setVersionId(e.target.value)} disabled={!productId}>
              <option value="">Selecione uma versão...</option>
              {versions.data?.map((v) => <option key={v.id} value={v.id}>{v.version} · {v.status}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>

      {!version ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Selecione um produto e uma versão.</CardContent></Card>
      ) : version.status === "published" ? (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
            <CheckCircle2 className="h-10 w-10 text-emerald-500" />
            <p className="font-medium text-emerald-600">Versão {version.version} já publicada</p>
            <p className="text-xs text-muted-foreground">Escopo, telas e planejamento dos Projects desta versão estão travados.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-[1fr_360px]">
          <div className="space-y-6">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold"><Package className="h-4 w-4" />Projects desta versão ({versionProjects.length})</CardTitle>
                <CardDescription className="text-xs">Um por tipo de aplicação (Pacote 2) -- todos precisam ter as tasks terminadas para publicar.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {versionProjects.length === 0 && <p className="text-sm text-muted-foreground">Nenhum Project vinculado a esta versão.</p>}
                {versionProjects.map((project) => {
                  const summary = tasksByProject.get(project.id) ?? { total: 0, done: 0 };
                  const complete = summary.total > 0 && summary.done === summary.total;
                  return (
                    <div key={project.id} className="flex items-center justify-between rounded-lg border p-3">
                      <div>
                        <p className="text-sm font-medium">{project.name}</p>
                        <p className="text-xs text-muted-foreground">{project.solution_type ?? "sem tipo"}</p>
                      </div>
                      <Badge variant={complete ? "success" : "outline"}>{summary.done}/{summary.total} tasks</Badge>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold"><GitBranch className="h-4 w-4" />Notas de Lançamento</CardTitle>
              </CardHeader>
              <CardContent>
                <Textarea rows={4} value={releaseNotes} onChange={(e) => setReleaseNotes(e.target.value)} placeholder="O que mudou nesta versão..." />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card className="border-primary/30">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4" />Resumo</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-md bg-muted p-3 space-y-2 text-xs">
                  <div className="flex justify-between"><span className="text-muted-foreground">Versão:</span><span className="font-bold">{version.version}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Projects:</span><span className="font-bold">{versionProjects.length}</span></div>
                </div>
                <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px] text-muted-foreground">
                  <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" />
                  <span>Bloqueia se houver task não terminada -- nunca completa trabalho automaticamente.</span>
                </div>
                <Button className="w-full" onClick={handlePublish} disabled={publish.isPending || updateVersion.isPending}>
                  {(publish.isPending || updateVersion.isPending) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Publicar Versão
                </Button>
                {blocking && (
                  <div className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-xs text-destructive">
                    <p className="font-medium">Tasks pendentes bloqueando a publicação:</p>
                    <ul className="list-disc pl-4">
                      {blocking.map((b) => <li key={b.task_id}>{b.project_name} — #{b.task_number} {b.title} ({b.status})</li>)}
                    </ul>
                  </div>
                )}
                {publish.isError && !blocking && (
                  <p className="text-xs text-destructive">{(publish.error as Error)?.message}</p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
