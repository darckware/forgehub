import { useTranslation } from "react-i18next";
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
  submitLabel: submitLabelProp,
}: StructureNodeFormProps) {
  const { t } = useTranslation("project");
  const submitLabel = submitLabelProp ?? t("structureNodeForm.submitLabelDefault");
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
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">{t("structureNodeForm.nameLabel")}</Label>
          <Input id="name" placeholder={t("structureNodeForm.namePlaceholder")} {...register("name")} />
          {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="node_type">{t("structureNodeForm.typeLabel")}</Label>
          <Select id="node_type" {...register("node_type")}>
            {STRUCTURE_NODE_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`enums.structureNodeType.${type}`, type)}
              </option>
            ))}
          </Select>
          {errors.node_type && (
            <p className="text-sm text-destructive">{errors.node_type.message}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="path">{t("structureNodeForm.pathLabel")}</Label>
        <Input
          id="path"
          placeholder={t("structureNodeForm.pathPlaceholder")}
          {...register("path")}
        />
        {errors.path && <p className="text-sm text-destructive">{errors.path.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="parent_node_id">{t("structureNodeForm.parentNodeLabel")}</Label>
        <Select id="parent_node_id" {...register("parent_node_id")}>
          <option value="">{t("structureNodeForm.noneTopLevel")}</option>
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
        <Label htmlFor="description">{t("structureNodeForm.descriptionLabel")}</Label>
        <Textarea className="resize-none"
          id="description"
          placeholder={t("structureNodeForm.descriptionPlaceholder")}
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("shared.cancel")}
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
