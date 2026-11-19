import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useNewVersionViewModel, type NewVersionViewModel } from "@/hooks/useNewVersionViewModel";

/** MSG-052: "Há uma nova versão do ForgeHub — recarregue". */
export function NewVersionBanner({ viewModel }: { viewModel?: NewVersionViewModel }) {
  const own = useNewVersionViewModel();
  const vm = viewModel ?? own;
  const { t } = useTranslation("common");
  if (vm.status !== "available") return null;
  return (
    <div role="status" className="fixed bottom-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 flex-col gap-3 rounded-md border bg-card p-3 text-sm shadow-lg sm:flex-row sm:items-center sm:justify-between">
      <span className="break-words">{t("newVersion.message")}</span>
      <Button size="sm" onClick={vm.reload} className="shrink-0">
        <RefreshCw className="mr-2 h-4 w-4" />{t("newVersion.reload")}
      </Button>
    </div>
  );
}
