import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldX } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((state) => state.user);
  const { t } = useTranslation("common");
  if (!user?.is_admin) {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-border p-6 text-center" role="alert">
        <ShieldX className="h-10 w-10 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 text-xl font-semibold">{t("accessDenied.title")}</h1>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">{t("accessDenied.description")}</p>
        <Link to="/" className={cn(buttonVariants({ variant: "outline" }), "mt-5 cursor-pointer")}>
          {t("accessDenied.back")}
        </Link>
      </div>
    );
  }
  return <>{children}</>;
}
