import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { PRODUCT_SALE_KEY } from "@/hooks/useProduct";

export type ProductSaleStatus = "idle" | "confirming" | "submitting" | "error";

export interface ProductSaleViewModel {
  status: ProductSaleStatus;
  offer: () => void;
  askWithdraw: () => void;
  cancelWithdraw: () => void;
  withdraw: () => void;
}

/** Offers a product for sale in Darckware, or takes it off sale after a confirmation. */
export function useProductSaleViewModel(productId: string): ProductSaleViewModel {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const mutation = useMutation({
    mutationFn: (action: "offer-for-sale" | "withdraw-from-sale") =>
      apiClient.post(`/api/v1/client-ops/products/${productId}:${action}`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PRODUCT_SALE_KEY }),
    onSettled: () => setConfirming(false),
  });

  let status: ProductSaleStatus = "idle";
  if (mutation.isPending) status = "submitting";
  else if (confirming) status = "confirming";
  else if (mutation.isError) status = "error";

  return {
    status,
    offer: () => mutation.mutate("offer-for-sale"),
    askWithdraw: () => {
      mutation.reset();
      setConfirming(true);
    },
    cancelWithdraw: () => setConfirming(false),
    withdraw: () => mutation.mutate("withdraw-from-sale"),
  };
}
