import { useEffect } from "react";
import { ArrowUpRight, Building2, Loader2, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useClients } from "@/hooks/useClients";

function supportPlanLabel(plan: string | null, t: (key: string) => string) {
  return plan ? t(`supportPlans.${plan}`) : t("supportPlans.none");
}

export default function ClientsPage() {
  const { t, i18n } = useTranslation("clients");
  const clients = useClients();

  useEffect(() => {
    document.title = `${t("list.title")} — ForgeHub`;
  }, [t]);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("list.context")}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{t("list.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("list.description")}</p>
        </div>
        <Link to="/clients/new" className={buttonVariants({ size: "sm", className: "gap-1.5" })}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t("list.newClient")}
        </Link>
      </header>

      <section className="overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="client-registry-heading">
        <h2 id="client-registry-heading" className="sr-only">{t("list.registry")}</h2>
        {clients.isLoading ? (
          <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> {t("states.loading")}
          </div>
        ) : clients.isError ? (
          <div className="min-h-40 p-6" role="alert">
            <p className="font-medium text-destructive">{t("states.loadError")}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => clients.refetch()}>{t("common.retry")}</Button>
          </div>
        ) : !clients.data?.length ? (
          <div className="flex min-h-48 flex-col items-center justify-center p-8 text-center">
            <Building2 className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
            <p className="mt-3 font-medium">{t("list.emptyTitle")}</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">{t("list.emptyDescription")}</p>
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead scope="col">{t("list.columns.client")}</TableHead>
                <TableHead scope="col">{t("list.columns.contact")}</TableHead>
                <TableHead scope="col">{t("list.columns.supportPlan")}</TableHead>
                <TableHead scope="col" className="text-right">{t("list.columns.updated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.data.map((client) => (
                <TableRow key={client.id}>
                  <TableCell>
                    <Link
                      to={`/clients/${client.id}`}
                      className="group inline-flex items-center gap-1.5 font-medium hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {client.name}
                      <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground" aria-hidden="true" />
                    </Link>
                  </TableCell>
                  <TableCell>
                    <p>{client.contact_name || t("common.notProvided")}</p>
                    {client.contact_email && <p className="text-xs text-muted-foreground">{client.contact_email}</p>}
                  </TableCell>
                  <TableCell><Badge variant="outline">{supportPlanLabel(client.support_plan, t)}</Badge></TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: "medium" }).format(new Date(client.updated_at))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
