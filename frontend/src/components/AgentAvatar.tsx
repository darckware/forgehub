import { cn } from "@/lib/utils";


export const AGENT_AVATAR_MAX_BYTES = 512 * 1024;
const AGENT_AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export type AgentAvatarValidationError = "type" | "empty" | "size";

export function validateAgentAvatar(file: File): AgentAvatarValidationError | null {
  if (!AGENT_AVATAR_TYPES.has(file.type)) return "type";
  if (file.size === 0) return "empty";
  if (file.size > AGENT_AVATAR_MAX_BYTES) return "size";
  return null;
}

export function agentInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toLocaleUpperCase() || "?";
}

const SIZE_CLASS = {
  sm: "h-9 w-9 text-xs",
  md: "h-12 w-12 text-sm",
  lg: "h-20 w-20 text-xl",
};

export function AgentAvatar({
  name,
  avatarDataUrl,
  imageAlt = "",
  size = "md",
  className,
}: {
  name: string;
  avatarDataUrl?: string | null;
  imageAlt?: string;
  size?: keyof typeof SIZE_CLASS;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted font-semibold uppercase text-muted-foreground",
        SIZE_CLASS[size],
        className,
      )}
    >
      {avatarDataUrl ? (
        <img src={avatarDataUrl} alt={imageAlt} className="h-full w-full object-cover" />
      ) : (
        agentInitials(name)
      )}
    </span>
  );
}
