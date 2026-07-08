import { useRef, useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/store/authStore";
import { useCreateDemand, useUploadDemandAttachment } from "@/hooks/useDemands";

/** "Nova nota" -- lets the logged-in user file their own inbox item (not
 * just agents via /submit), per the "console de desenvolvimento" use case:
 * day-to-day notes/procedures land here first, get triaged later. Files
 * as `from_agent = username` so the inbox shows a real sender either way. */
export function ComposeDemandDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const user = useAuthStore((s) => s.user);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const createDemand = useCreateDemand();
  const uploadAttachment = useUploadDemandAttachment();
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function reset() {
    setSubject("");
    setBody("");
    setFiles([]);
    setError(null);
  }

  async function handleSubmit() {
    setError(null);
    try {
      const demand = await createDemand.mutateAsync({
        from_agent: user?.username ?? "você",
        subject,
        body,
      });
      for (const file of files) {
        await uploadAttachment.mutateAsync({ demandId: demand.id, file });
      }
      reset();
      onClose();
    } catch (e) {
      setError((e as Error)?.message ?? "Falha ao enviar nota");
    }
  }

  const isPending = createDemand.isPending || uploadAttachment.isPending;
  const canSubmit = subject.trim().length > 0 && body.trim().length > 0 && !isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => {
          reset();
          onClose();
        }}
      />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="p-6">
          <h2 className="text-base font-semibold">Nova nota</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Registrada no inbox como enviada por você -- classifique depois em Base de
            Conhecimento, um projeto, ou planejamento.
          </p>

          <div className="mt-4 space-y-3">
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Assunto"
              maxLength={255}
            />
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Conteúdo em markdown..."
              rows={8}
              className="font-mono text-sm"
            />

            <div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  setFiles((prev) => [...prev, ...picked]);
                  e.target.value = "";
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip className="h-3.5 w-3.5" /> Anexar arquivo
              </Button>
              {files.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {files.map((f, i) => (
                    <li
                      key={`${f.name}-${i}`}
                      className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1 text-xs"
                    >
                      <span className="truncate">{f.name}</span>
                      <button
                        type="button"
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                        onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {error && <p className={cn("mt-3 text-sm text-destructive")}>{error}</p>}

          <div className="mt-6 flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => {
                reset();
                onClose();
              }}
            >
              Cancelar
            </Button>
            <Button disabled={!canSubmit} onClick={handleSubmit} className="min-w-[88px] gap-1.5">
              {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Enviar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
