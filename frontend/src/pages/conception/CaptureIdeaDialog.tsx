import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Plus, Sparkles, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateIdea } from "@/hooks/useSystemScope";
import { useProducts } from "@/hooks/useProduct";

const EMPTY_FORM = {
  selected_product_id: "",
  opening_type: "new_implementation", // "new_implementation" | "maintenance"
  name: "",
  problem_statement: "",
  vision: "",
  scope_summary: "",
  requested_by: "",
  priority: "medium",
};

export function CaptureIdeaDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("conception");
  const { data: products } = useProducts();
  const create = useCreateIdea();
  const [form, setForm] = useState(EMPTY_FORM);
  const [isCustomProduct, setIsCustomProduct] = useState(false);

  if (!open) return null;

  function reset() {
    setForm(EMPTY_FORM);
    setIsCustomProduct(false);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const typePrefix = form.opening_type === "maintenance" ? "[Manutenção] " : "[Nova Implementação] ";
    const effectiveName = form.name.startsWith("[") ? form.name : `${typePrefix}${form.name}`;

    await create.mutateAsync({
      name: effectiveName,
      problem_statement: form.problem_statement,
      vision: form.vision || undefined,
      scope_summary: form.scope_summary || undefined,
      requested_by: form.requested_by || undefined,
    });
    reset();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => { reset(); onClose(); }}
      />
      <div className="relative z-10 w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <form className="p-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <h2 className="text-base font-bold flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              Abertura de Concepção de Projeto
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Vincule a concepção a um Produto existente para manter o histórico evolutivo de versões.
            </p>
          </div>

          {/* 1. Seleção de Produto e Tipo de Abertura */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg border bg-muted/20">
            <div>
              <Label className="text-xs font-semibold flex items-center gap-1.5 mb-1">
                <Package className="h-3.5 w-3.5 text-primary" />
                Produto Associado
              </Label>
              <Select
                value={isCustomProduct ? "__new__" : form.selected_product_id}
                onChange={(e) => {
                  if (e.target.value === "__new__") {
                    setIsCustomProduct(true);
                    setForm({ ...form, selected_product_id: "" });
                  } else {
                    setIsCustomProduct(false);
                    const prod = products?.find((p) => p.id === e.target.value);
                    setForm({
                      ...form,
                      selected_product_id: e.target.value,
                      name: prod ? `${prod.name}` : form.name,
                    });
                  }
                }}
                className="text-xs"
              >
                <option value="">Selecione um Produto...</option>
                {products?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
                <option value="__new__">+ Novo Produto</option>
              </Select>
            </div>

            <div>
              <Label className="text-xs font-semibold flex items-center gap-1.5 mb-1">
                Tipo de Abertura
              </Label>
              <Select
                value={form.opening_type}
                onChange={(e) => setForm({ ...form, opening_type: e.target.value })}
                className="text-xs font-medium"
              >
                <option value="new_implementation">🚀 Nova Implementação</option>
                <option value="maintenance">🔧 Manutenção</option>
              </Select>
            </div>
          </div>

          {/* 2. Título / Nome da Concepção */}
          <div>
            <Label className="text-xs">{t("captureIdea.fields.name")}</Label>
            <Input
              required
              placeholder={form.opening_type === "maintenance" ? "Ex: Correção de autenticação e otimização de consultas" : "Ex: Módulo de Cobrança Recorrente PIX"}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="text-xs font-medium"
            />
          </div>

          {/* 3. Problema / Necessidade */}
          <div>
            <Label className="text-xs">{t("captureIdea.fields.problemStatement")}</Label>
            <Textarea
              required
              rows={3}
              placeholder="Descreva o problema a ser resolvido ou o objetivo desta abertura..."
              value={form.problem_statement}
              onChange={(e) => setForm({ ...form, problem_statement: e.target.value })}
              className="text-xs"
            />
          </div>

          {/* 4. Visão e Escopo Inicial */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">{t("captureIdea.fields.vision")}</Label>
              <Textarea
                rows={2}
                placeholder="Visão da solução..."
                value={form.vision}
                onChange={(e) => setForm({ ...form, vision: e.target.value })}
                className="text-xs"
              />
            </div>
            <div>
              <Label className="text-xs">{t("captureIdea.fields.initialScope")}</Label>
              <Textarea
                rows={2}
                placeholder="Resumo do escopo..."
                value={form.scope_summary}
                onChange={(e) => setForm({ ...form, scope_summary: e.target.value })}
                className="text-xs"
              />
            </div>
          </div>

          {/* 5. Prioridade e Solicitante */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">{t("captureIdea.fields.priority")}</Label>
              <Select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                className="text-xs"
              >
                <option value="low">{t("captureIdea.priorityOptions.low")}</option>
                <option value="medium">{t("captureIdea.priorityOptions.medium")}</option>
                <option value="high">{t("captureIdea.priorityOptions.high")}</option>
                <option value="critical">{t("captureIdea.priorityOptions.critical")}</option>
              </Select>
            </div>
            <div>
              <Label className="text-xs">{t("captureIdea.fields.requestedBy")}</Label>
              <Input
                placeholder="Ex: Usuário / Product Owner"
                value={form.requested_by}
                onChange={(e) => setForm({ ...form, requested_by: e.target.value })}
                className="text-xs"
              />
            </div>
          </div>

          {create.isError && (
            <p className="text-xs text-destructive">{(create.error as Error)?.message}</p>
          )}

          <div className="pt-2 flex justify-end gap-2 border-t">
            <Button type="button" variant="outline" size="sm" onClick={() => { reset(); onClose(); }}>
              {t("captureIdea.buttons.cancel")}
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending} className="min-w-[88px] gap-1.5 font-semibold">
              {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              {t("captureIdea.buttons.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
