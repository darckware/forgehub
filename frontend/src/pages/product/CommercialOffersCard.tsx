import { useTranslation } from "react-i18next";
import { Loader2, Plus, Unlink, PackageSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useCommercialOffersViewModel } from "@/hooks/useCommercialOffersViewModel";

interface CommercialOffersCardProps {
  productId: string;
}

export function CommercialOffersCard({ productId }: CommercialOffersCardProps) {
  const { t } = useTranslation("product");
  const vm = useCommercialOffersViewModel(productId);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="text-xl font-semibold tracking-tight">
            {t("detail.offers.title")}
          </CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            {t("detail.offers.description")}
          </CardDescription>
        </div>
        {!vm.isLinking && (
          <Button
            size="sm"
            onClick={vm.startLinking}
            disabled={vm.isLoading || vm.unlinkedOffers.length === 0}
            className="w-full sm:w-auto"
          >
            <Plus className="mr-2 h-4 w-4" />
            {t("detail.offers.linkButton")}
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {vm.isLinking && (
          <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-4 sm:flex-row sm:items-center">
            <div className="flex-1">
              <Select
                value={vm.selectedOfferId}
                onChange={(e) => vm.setSelectedOfferId(e.target.value)}
                className="w-full"
                aria-label={t("detail.offers.selectPlaceholder")}
              >
                <option value="">{t("detail.offers.selectPlaceholder")}</option>
                {vm.unlinkedOffers.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name} ({o.slug})
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={vm.linkOffer}
                disabled={!vm.selectedOfferId || vm.isMutating}
              >
                {vm.isMutating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("detail.offers.confirmLink")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={vm.cancelLinking}
                disabled={vm.isMutating}
              >
                {t("detail.offers.cancel")}
              </Button>
            </div>
          </div>
        )}

        {vm.isLoading ? (
          <div className="flex items-center justify-center gap-2 p-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            {t("detail.offers.loading")}
          </div>
        ) : vm.linkedOffers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-8 text-center text-muted-foreground">
            <PackageSearch className="h-8 w-8" />
            <p className="text-sm">{t("detail.offers.empty")}</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("detail.offers.columns.name")}</TableHead>
                <TableHead>{t("detail.offers.columns.category")}</TableHead>
                <TableHead>{t("detail.offers.columns.description")}</TableHead>
                <TableHead>{t("detail.offers.columns.status")}</TableHead>
                <TableHead className="text-right">
                  {t("detail.offers.columns.actions")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vm.linkedOffers.map((offer) => (
                <TableRow key={offer.id}>
                  <TableCell>
                    <div className="font-medium text-foreground">{offer.name}</div>
                    <div className="text-xs text-muted-foreground">{offer.slug}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs font-mono">
                      {offer.category}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground text-sm">
                    {offer.description ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={offer.is_active ? "success" : "secondary"}>
                      {offer.is_active ? t("detail.offers.active") : t("detail.offers.inactive")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => vm.confirmUnlink(offer)}
                      disabled={vm.isMutating}
                      className="text-destructive hover:text-destructive"
                      title={t("detail.offers.unlinkButton")}
                    >
                      <Unlink className="mr-1.5 h-3.5 w-3.5" />
                      {t("detail.offers.unlinkButton")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ConfirmDialog
        open={Boolean(vm.pendingUnlinkOffer)}
        title={t("detail.offers.unlinkDialog.title", {
          name: vm.pendingUnlinkOffer?.name ?? "",
        })}
        description={t("detail.offers.unlinkDialog.description")}
        confirmLabel={t("detail.offers.unlinkDialog.confirm")}
        onConfirm={vm.executeUnlink}
        onCancel={vm.cancelUnlink}
        loading={vm.isMutating}
        variant="destructive"
      />
    </Card>
  );
}
