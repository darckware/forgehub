import { useState, type ReactNode } from "react";
import { Archive, ChevronDown, ChevronRight, FolderPlus, Loader2, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import { DEMAND_DRAG_MIME, InlineMessageList } from "@/components/AgentInboxTree";
import {
  useCreateDemandGroup,
  useDeleteDemandGroup,
  useUpdateDemandGroup,
  type DemandGroup,
} from "@/hooks/useDemands";

// Namespaced custom MIME type for reparenting a folder onto another folder
// (or the Archived root) via drag-and-drop -- same pattern as
// DocTree.tsx's DRAG_MIME. DEMAND_DRAG_MIME (dragging a message) is now
// defined in AgentInboxTree.tsx and re-exported below, since that
// component's root row also needs to be a drop target.
const GROUP_DRAG_MIME = "application/x-forgehub-demand-group-id";

interface TreeNode extends DemandGroup {
  children: TreeNode[];
}

function buildTree(groups: DemandGroup[]): TreeNode[] {
  const byId = new Map<string, TreeNode>(groups.map((g) => [g.id, { ...g, children: [] }]));
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

/** True if `candidateAncestorId` is `groupId` itself or one of its
 * descendants -- used to block dropping a folder into its own subtree
 * client-side (the backend also rejects it, this just avoids a round trip
 * and an error flash for the common case). */
function isSelfOrDescendant(groups: DemandGroup[], groupId: string, candidateAncestorId: string): boolean {
  if (groupId === candidateAncestorId) return true;
  const children = groups.filter((g) => g.parent_id === groupId);
  return children.some((c) => isSelfOrDescendant(groups, c.id, candidateAncestorId));
}

function ActionIcon({
  icon: Icon,
  label,
  onClick,
  destructive,
}: {
  icon: typeof Pencil;
  label: string;
  onClick: () => void;
  destructive?: boolean;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("h-5 w-5 shrink-0", destructive && "text-destructive")}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <Icon className="h-3 w-3" />
    </Button>
  );
}

/** Inline "new subfolder" row -- name input in place of a tree row,
 * confirmed with Enter/blur, cancelled with Escape. */
function NewGroupRow({ depth, onConfirm, onCancel }: { depth: number; onConfirm: (name: string) => void; onCancel: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="flex items-center gap-1 py-1 pr-1" style={{ paddingLeft: `${depth * 0.9 + 0.5}rem` }}>
      <Input
        autoFocus
        value={value}
        placeholder="Folder name"
        className="h-6 text-xs"
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => (value.trim() ? onConfirm(value.trim()) : onCancel())}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) onConfirm(value.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
    </div>
  );
}

function GroupRow<T>({
  label,
  node,
  depth,
  groups,
  selectedGroupId,
  onSelectGroup,
  onDropDemand,
  counts,
  messages,
  renderMessage,
  emptyMessage,
}: {
  label: string;
  node: TreeNode;
  depth: number;
  groups: DemandGroup[];
  selectedGroupId: string | null | undefined;
  onSelectGroup: (id: string) => void;
  onDropDemand: (demandId: string, groupId: string | null) => void;
  counts?: Record<string, number>;
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  // Defaults collapsed, matching Incoming/Outbox: clicking a row both
  // toggles expansion and selects it (renders its inline messages), so
  // starting expanded would make the very first click collapse it and hide
  // the list it just selected.
  const [expanded, setExpanded] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(node.name);
  const [creatingChild, setCreatingChild] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const createGroup = useCreateDemandGroup();
  const updateGroup = useUpdateDemandGroup();
  const deleteGroup = useDeleteDemandGroup();

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const demandId = e.dataTransfer.getData(DEMAND_DRAG_MIME);
    if (demandId) {
      onDropDemand(demandId, node.id);
      return;
    }
    const sourceGroupId = e.dataTransfer.getData(GROUP_DRAG_MIME);
    if (sourceGroupId && !isSelfOrDescendant(groups, sourceGroupId, node.id)) {
      updateGroup.mutate({ id: sourceGroupId, parentId: node.id });
    }
  }

  return (
    <div>
      <div
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData(GROUP_DRAG_MIME, node.id);
          e.dataTransfer.effectAllowed = "move";
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
          dragOver
            ? "bg-accent ring-1 ring-inset ring-primary"
            : selectedGroupId === node.id
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <ConfirmDialog
          open={confirmDelete}
          title={`Delete folder "${node.name}"`}
          description={`Subfolders are deleted too. Messages inside this folder fall back to the ${label} root -- nothing is deleted.`}
          loading={deleteGroup.isPending}
          onConfirm={() => deleteGroup.mutate(node.id, { onSuccess: () => setConfirmDelete(false) })}
          onCancel={() => setConfirmDelete(false)}
        />
        <button
          type="button"
          onClick={() => {
            setExpanded((v) => !v);
            onSelectGroup(node.id);
          }}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
          style={{ paddingLeft: `${depth * 0.9 + 0.5}rem` }}
        >
          {node.children.length > 0 ? (
            expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          {renaming ? (
            <Input
              autoFocus
              value={renameValue}
              className="h-6 text-xs"
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setRenameValue(e.target.value)}
              onBlur={() => {
                setRenaming(false);
                if (renameValue.trim() && renameValue !== node.name) {
                  updateGroup.mutate({ id: node.id, name: renameValue.trim() });
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                if (e.key === "Escape") {
                  setRenameValue(node.name);
                  setRenaming(false);
                }
              }}
            />
          ) : (
            <span className="truncate">{node.name}</span>
          )}
          {counts?.[node.id] ? <span className="shrink-0 text-[10px] text-muted-foreground">{counts[node.id]}</span> : null}
        </button>
        <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          <ActionIcon icon={FolderPlus} label="New subfolder" onClick={() => setCreatingChild(true)} />
          <ActionIcon icon={Pencil} label="Rename folder" onClick={() => setRenaming(true)} />
          <ActionIcon icon={Trash2} label="Delete folder" destructive onClick={() => setConfirmDelete(true)} />
        </div>
      </div>
      {expanded && (
        <>
          {selectedGroupId === node.id && (
            <div style={{ paddingLeft: `${(depth + 1) * 0.9 + 0.5}rem` }} className="pr-1">
              <InlineMessageList messages={messages} renderMessage={renderMessage} emptyMessage={emptyMessage} />
            </div>
          )}
          {node.children.map((child) => (
            <GroupRow
              key={child.id}
              label={label}
              node={child}
              depth={depth + 1}
              groups={groups}
              selectedGroupId={selectedGroupId}
              onSelectGroup={onSelectGroup}
              onDropDemand={onDropDemand}
              counts={counts}
              messages={messages}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
          ))}
          {creatingChild && (
            <NewGroupRow
              depth={depth + 1}
              onConfirm={(name) => {
                createGroup.mutate({ name, parent_id: node.id }, { onSuccess: () => setCreatingChild(false) });
              }}
              onCancel={() => setCreatingChild(false)}
            />
          )}
        </>
      )}
    </div>
  );
}

/** "Archived" tree: the root itself is synthetic (not a demand_groups
 * row -- see useDemands.ts's demandGroupSchema comment), its children are
 * user-created subfolders that nest freely. Dragging a Demand row (see the
 * Inbox page's DEMAND_DRAG_MIME producer) onto the root or any subfolder
 * files it there (and archives it, server-side). Dragging a folder row
 * onto another folder (or the root) reparents it. */
export function InboxGroupTree<T>({
  label,
  groups,
  selectedGroupId,
  onSelectRoot,
  onSelectGroup,
  onDropDemand,
  counts,
  rootCount,
  messages,
  renderMessage,
  emptyMessage,
}: {
  /** Root row label -- "Archived" started as the literal folder name, now
   * user-facing copy calls it "Anotações"/"Notes" (2026-07-24), so this is
   * a prop instead of hardcoded text. The underlying concept (demand.status
   * === "archived", group_id, drag targets) is unchanged, only the label. */
  label: string;
  groups: DemandGroup[];
  /** undefined = Archived isn't the active view at all (Incoming is
   * selected); null = the Archived root itself is selected; a group id =
   * that subfolder is selected. */
  selectedGroupId: string | null | undefined;
  onSelectRoot: () => void;
  onSelectGroup: (id: string) => void;
  onDropDemand: (demandId: string, groupId: string | null) => void;
  /** Optional per-group demand count badge. */
  counts?: Record<string, number>;
  /** Badge shown on the root row -- total archived count. */
  rootCount?: number;
  /** The already-filtered list for whichever node is currently active --
   * only rendered under that one node (root or a subfolder). */
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  const tree = buildTree(groups);
  // Defaults collapsed, matching Incoming/Outbox: clicking a row both
  // toggles expansion and selects it (renders its inline messages), so
  // starting expanded would make the very first click collapse it and hide
  // the list it just selected.
  const [expanded, setExpanded] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [creatingRoot, setCreatingRoot] = useState(false);
  const createGroup = useCreateDemandGroup();
  const updateGroup = useUpdateDemandGroup();

  function handleRootDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const demandId = e.dataTransfer.getData(DEMAND_DRAG_MIME);
    if (demandId) {
      onDropDemand(demandId, null);
      return;
    }
    const sourceGroupId = e.dataTransfer.getData(GROUP_DRAG_MIME);
    if (sourceGroupId) updateGroup.mutate({ id: sourceGroupId, parentId: null });
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleRootDrop}
        className={cn(
          "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
          dragOver
            ? "bg-accent ring-1 ring-inset ring-primary"
            : selectedGroupId === null
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <button
          type="button"
          onClick={() => {
            setExpanded((v) => !v);
            onSelectRoot();
          }}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <Archive className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate font-medium">{label}</span>
          {!!rootCount && <span className="text-[10px] text-muted-foreground">{rootCount}</span>}
        </button>
        <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          <ActionIcon icon={FolderPlus} label="New folder" onClick={() => setCreatingRoot(true)} />
        </div>
        {createGroup.isPending && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />}
      </div>
      {expanded && (
        <>
          {selectedGroupId === null && (
            <div style={{ paddingLeft: "1.4rem" }} className="pr-1">
              <InlineMessageList messages={messages} renderMessage={renderMessage} emptyMessage={emptyMessage} />
            </div>
          )}
          {tree.map((node) => (
            <GroupRow
              key={node.id}
              label={label}
              node={node}
              depth={1}
              groups={groups}
              selectedGroupId={selectedGroupId}
              onSelectGroup={onSelectGroup}
              onDropDemand={onDropDemand}
              counts={counts}
              messages={messages}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
          ))}
          {creatingRoot && (
            <NewGroupRow
              depth={1}
              onConfirm={(name) => {
                createGroup.mutate({ name, parent_id: null }, { onSuccess: () => setCreatingRoot(false) });
              }}
              onCancel={() => setCreatingRoot(false)}
            />
          )}
        </>
      )}
    </div>
  );
}

export { DEMAND_DRAG_MIME };
