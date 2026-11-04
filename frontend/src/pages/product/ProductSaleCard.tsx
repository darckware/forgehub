import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useProductSaleViewModel } from "@/hooks/useProductSaleViewModel";

interface ProductSaleCardProps {
  productId: string;
  offeredForSaleAt?: string | null;
}

/** Shown only for a product marked as available for sale. */
export function ProductSaleCard({ productId, offeredForSaleAt }: ProductSaleCardProps) {
  const { t } = useTranslation("product");
  const vm = useProductSaleViewModel(productId);
  const submitting = vm.status === "submitting";
  const offered = Boolean(offeredForSaleAt);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1.5">
          <CardTitle>{t("sale.title")}</CardTitle>
          <CardDescription>{t(offered ? "sale.offeredHint" : "sale.hint")}</CardDescription>
        </div>
        <Badge className="max-sm:self-start" variant={offered ? "default" : "secondary"}>{t(offered ? "sale.offered" : "sale.notOffered")}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button
          variant={offered ? "outline" : "default"}
          disabled={submitting}
          onClick={offered ? vm.askWithdraw : vm.offer}
          className="max-md:h-auto max-md:whitespace-normal"
        >
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t(offered ? "sale.withdraw" : "sale.offer")}
        </Button>
        {vm.status === "error" && (
          <p role="alert" className="text-sm text-destructive">
            {t("sale.error")}
          </p>
        )}
      </CardContent>
      <ConfirmDialog
        open={vm.status === "confirming"}
        title={t("sale.withdrawDialog.title")}
        description={t("sale.withdrawDialog.description")}
        confirmLabel={t("sale.withdraw")}
        icon="warning"
        loading={submitting}
        onConfirm={vm.withdraw}
        onCancel={vm.cancelWithdraw}
      />
    </Card>
  );
}
