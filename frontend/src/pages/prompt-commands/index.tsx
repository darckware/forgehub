import { useMemo, useState } from "react";
import { Command, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  RESERVED_PROMPT_COMMAND_NAMES,
  normalizePromptCommandName,
  useCreatePromptCommand,
  useDeletePromptCommand,
  usePromptCommands,
  useUpdatePromptCommand,
  type PromptCommand,
} from "@/hooks/usePromptCommands";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";

type Draft = {
  name: string;
  description: string;
  prompt: string;
};

const EMPTY_DRAFT: Draft = {
  name: "",
  description: "",
  prompt: "",
};

function CommandFormModal({
  initial,
  onClose,
}: {
  initial: PromptCommand | null;
  onClose: () => void;
}) {
  const createCommand = useCreatePromptCommand();
  const updateCommand = useUpdatePromptCommand();
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(
    initial
      ? { name: initial.name, description: initial.description, prompt: initial.prompt }
      : EMPTY_DRAFT
  );

  const normalizedName = useMemo(() => normalizePromptCommandName(draft.name), [draft.name]);
  const pending = createCommand.isPending || updateCommand.isPending;

  function handleSave() {
    setError(null);
    if (!normalizedName) {
      setError("Enter a short name, like review-pr or plan.");
      return;
    }
    if (RESERVED_PROMPT_COMMAND_NAMES.includes(normalizedName)) {
      setError(`/${normalizedName} is already a reserved Hermes command.`);
      return;
    }
    if (!draft.description.trim()) {
      setError("Enter a short description.");
      return;
    }
    if (!draft.prompt.trim()) {
      setError("Enter the prompt in Markdown.");
      return;
    }
    const payload = {
      name: normalizedName,
      description: draft.description,
      prompt: draft.prompt,
    };
    const opts = {
      onSuccess: onClose,
      onError: (e: Error) => setError(e.message || "Could not save."),
    };
    if (initial) updateCommand.mutate({ id: initial.id, payload }, opts);
    else createCommand.mutate(payload, opts);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">{initial ? "Edit command" : "New command"}</h2>
            <p className="text-xs text-muted-foreground">Appears in chat as /{normalizedName || "name"}.</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto p-5">
          <div className="grid gap-4 md:grid-cols-[220px_1fr]">
            <div className="space-y-1.5">
              <Label htmlFor="command-name">Short name</Label>
              <Input
                id="command-name"
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                placeholder="review-pr"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="command-description">Description</Label>
              <Input
                id="command-description"
                value={draft.description}
                onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                placeholder="Review a PR focused on risks and tests"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="command-prompt">Markdown prompt</Label>
            <Textarea
              id="command-prompt"
              value={draft.prompt}
              onChange={(e) => setDraft((d) => ({ ...d, prompt: e.target.value }))}
              className="min-h-[320px] font-mono text-xs"
              placeholder={"## Goal\nReview the current code and list bugs, risks, and missing tests.\n\n## Expected output\n- Findings by severity\n- Affected files\n- Verification commands"}
              spellCheck={false}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={pending}>
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {initial ? "Save" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function PromptCommandsPage() {
  const { data: commands = [], isLoading, isError, error } = usePromptCommands();
  const deleteCommand = useDeletePromptCommand();
  const [editing, setEditing] = useState<PromptCommand | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<PromptCommand | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Chat Commands</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Register reusable prompts to show up alongside Hermes commands when typing / in chat.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setCreating(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            New command
          </Button>
          <AssistantToggleButton className="gap-2" />
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Command</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Prompt</TableHead>
                <TableHead className="w-28 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {commands.map((command) => (
                <TableRow key={command.id}>
                  <TableCell className="font-mono text-xs">/{command.name}</TableCell>
                  <TableCell>{command.description}</TableCell>
                  <TableCell className="max-w-xl">
                    <p className="line-clamp-2 whitespace-pre-wrap text-xs text-muted-foreground">
                      {command.prompt}
                    </p>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" aria-label="Edit" onClick={() => setEditing(command)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" aria-label="Delete" onClick={() => setDeleting(command)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {commands.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
                      {isLoading ? (
                        <Loader2 className="h-8 w-8 animate-spin" />
                      ) : (
                        <Command className="h-8 w-8" />
                      )}
                      <p className="text-sm">
                        {isLoading
                          ? "Loading commands..."
                          : isError
                            ? `Failed to load: ${(error as Error)?.message}`
                            : "No commands registered yet."}
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {creating && <CommandFormModal initial={null} onClose={() => setCreating(false)} />}
      {editing && <CommandFormModal initial={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete command"
        description={`Delete /${deleting?.name ?? ""}? It will no longer appear in chat.`}
        confirmLabel="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          deleteCommand.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        loading={deleteCommand.isPending}
      />
    </div>
  );
}
