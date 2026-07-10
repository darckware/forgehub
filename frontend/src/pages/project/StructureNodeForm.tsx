import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  STRUCTURE_NODE_TYPES,
  structureNodeCreateSchema,
  type StructureNode,
  type StructureNodeCreateInput,
} from "@/hooks/useProject";

interface StructureNodeFormProps {
  siblingNodes: StructureNode[];
  defaultValues?: Partial<StructureNodeCreateInput>;
  onSubmit: (values: StructureNodeCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

export function StructureNodeForm({
  siblingNodes,
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = "Add node",
}: StructureNodeFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StructureNodeCreateInput>({
    resolver: zodResolver(structureNodeCreateSchema),
    defaultValues: {
      name: "",
      node_type: "folder",
      parent_node_id: "",
      path: "",
      description: "",
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input id="name" placeholder="task.py" {...register("name")} />
          {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="node_type">Type</Label>
          <Select id="node_type" {...register("node_type")}>
            {STRUCTURE_NODE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          {errors.node_type && (
            <p className="text-sm text-destructive">{errors.node_type.message}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="path">Path</Label>
        <Input
          id="path"
          placeholder="backend/app/db/models/task.py"
          {...register("path")}
        />
        {errors.path && <p className="text-sm text-destructive">{errors.path.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="parent_node_id">Parent node</Label>
        <Select id="parent_node_id" {...register("parent_node_id")}>
          <option value="">None (top-level)</option>
          {siblingNodes.map((node) => (
            <option key={node.id} value={node.id}>
              {node.path ?? node.name}
            </option>
          ))}
        </Select>
        {errors.parent_node_id && (
          <p className="text-sm text-destructive">{errors.parent_node_id.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          placeholder="What this part of the system is responsible for"
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
