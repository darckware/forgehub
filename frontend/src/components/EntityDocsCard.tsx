import { Link } from "react-router-dom";
import { BookOpen, ExternalLink, Loader2, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useDeleteDocLink, useEntityDocLinks, type DocLinkEntityType } from "@/hooks/useDocLinks";

/**
 * "Docs" section for a Planning entity's detail screen: every document in
 * /root/docs linked to this entity (doc_links, see docs.py). Read/unlink
 * here; linking itself happens from the Docs page (pick the entity while
 * viewing the doc) to keep one place responsible for the mutation.
 */
export function EntityDocsCard({
  entityType,
  entityId,
}: {
  entityType: DocLinkEntityType;
  entityId: string | undefined;
}) {
  const { data: links, isLoading } = useEntityDocLinks(entityType, entityId);
  const deleteLink = useDeleteDocLink();

  if (!entityId) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <BookOpen className="h-4 w-4" /> Docs
          {links && <span className="text-xs font-normal text-muted-foreground">{links.length}</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {links && links.length === 0 && (
          <p className="text-xs italic text-muted-foreground">
            Nenhum documento vinculado. Abra a página Docs e vincule um documento a este item.
          </p>
        )}
        {links?.map((link) => (
          <div key={link.id} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50">
            <Link
              to={`/docs?path=${encodeURIComponent(link.doc_path)}`}
              className="flex min-w-0 items-center gap-1.5 text-sm hover:underline"
              title={link.doc_path}
            >
              <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{link.doc_path}</span>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              aria-label="Desvincular"
              title="Desvincular"
              onClick={() => deleteLink.mutate(link.id)}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
