import { useMemo, useState } from "react";
import {
  useDarckwareSoftwareProducts,
  useLinkSoftwareProduct,
  type DarckwareSoftwareProduct,
} from "./useClientOps";

export interface CommercialOffersViewModel {
  linkedOffers: DarckwareSoftwareProduct[];
  unlinkedOffers: DarckwareSoftwareProduct[];
  isLinking: boolean;
  selectedOfferId: string;
  pendingUnlinkOffer: DarckwareSoftwareProduct | null;
  isLoading: boolean;
  isError: boolean;
  isMutating: boolean;
  error: Error | null;
  mutationError: Error | null;
  mutationAction: "link" | "unlink" | null;
  startLinking: () => void;
  cancelLinking: () => void;
  setSelectedOfferId: (id: string) => void;
  linkOffer: () => Promise<void>;
  confirmUnlink: (offer: DarckwareSoftwareProduct) => void;
  cancelUnlink: () => void;
  executeUnlink: () => Promise<void>;
}

export function useCommercialOffersViewModel(
  productId: string | undefined
): CommercialOffersViewModel {
  const {
    data: offers = [],
    isLoading,
    isError: isListError,
    error: queryError,
  } = useDarckwareSoftwareProducts();
  const linkMutation = useLinkSoftwareProduct();

  const [isLinking, setIsLinking] = useState(false);
  const [selectedOfferId, setSelectedOfferId] = useState("");
  const [pendingUnlinkOffer, setPendingUnlinkOffer] = useState<DarckwareSoftwareProduct | null>(null);
  const [mutationAction, setMutationAction] = useState<"link" | "unlink" | null>(null);

  const linkedOffers = useMemo(
    () => (productId ? offers.filter((o) => o.forgehub_product_id === productId) : []),
    [offers, productId]
  );

  const unlinkedOffers = useMemo(
    () => offers.filter((o) => !o.forgehub_product_id),
    [offers]
  );

  const startLinking = () => {
    linkMutation.reset();
    setMutationAction(null);
    setIsLinking(true);
    setSelectedOfferId("");
  };

  const cancelLinking = () => {
    linkMutation.reset();
    setMutationAction(null);
    setIsLinking(false);
    setSelectedOfferId("");
  };

  const linkOffer = async () => {
    if (!selectedOfferId || !productId) return;
    setMutationAction("link");
    try {
      await linkMutation.mutateAsync({
        id: selectedOfferId,
        forgehubProductId: productId,
      });
      setIsLinking(false);
      setSelectedOfferId("");
    } catch {
      // linkMutation.error is captured by React Query
    }
  };

  const confirmUnlink = (offer: DarckwareSoftwareProduct) => {
    linkMutation.reset();
    setMutationAction(null);
    setPendingUnlinkOffer(offer);
  };

  const cancelUnlink = () => {
    linkMutation.reset();
    setMutationAction(null);
    setPendingUnlinkOffer(null);
  };

  const executeUnlink = async () => {
    if (!pendingUnlinkOffer) return;
    setMutationAction("unlink");
    try {
      await linkMutation.mutateAsync({
        id: pendingUnlinkOffer.id,
        forgehubProductId: null,
      });
      setPendingUnlinkOffer(null);
    } catch {
      setPendingUnlinkOffer(null);
    }
  };

  return {
    linkedOffers,
    unlinkedOffers,
    isLinking,
    selectedOfferId,
    pendingUnlinkOffer,
    isLoading,
    isError: isListError || Boolean(queryError),
    isMutating: linkMutation.isPending,
    error: (linkMutation.error || queryError) as Error | null,
    mutationError: (linkMutation.error as Error | null) ?? null,
    mutationAction,
    startLinking,
    cancelLinking,
    setSelectedOfferId,
    linkOffer,
    confirmUnlink,
    cancelUnlink,
    executeUnlink,
  };
}
