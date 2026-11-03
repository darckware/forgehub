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
  isMutating: boolean;
  error: Error | null;
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
  const { data: offers = [], isLoading, error: queryError } = useDarckwareSoftwareProducts();
  const linkMutation = useLinkSoftwareProduct();

  const [isLinking, setIsLinking] = useState(false);
  const [selectedOfferId, setSelectedOfferId] = useState("");
  const [pendingUnlinkOffer, setPendingUnlinkOffer] = useState<DarckwareSoftwareProduct | null>(null);

  const linkedOffers = useMemo(
    () => (productId ? offers.filter((o) => o.forgehub_product_id === productId) : []),
    [offers, productId]
  );

  const unlinkedOffers = useMemo(
    () => offers.filter((o) => !o.forgehub_product_id),
    [offers]
  );

  const startLinking = () => {
    setIsLinking(true);
    setSelectedOfferId("");
  };

  const cancelLinking = () => {
    setIsLinking(false);
    setSelectedOfferId("");
  };

  const linkOffer = async () => {
    if (!selectedOfferId || !productId) return;
    await linkMutation.mutateAsync({
      id: selectedOfferId,
      forgehubProductId: productId,
    });
    setIsLinking(false);
    setSelectedOfferId("");
  };

  const confirmUnlink = (offer: DarckwareSoftwareProduct) => {
    setPendingUnlinkOffer(offer);
  };

  const cancelUnlink = () => {
    setPendingUnlinkOffer(null);
  };

  const executeUnlink = async () => {
    if (!pendingUnlinkOffer) return;
    await linkMutation.mutateAsync({
      id: pendingUnlinkOffer.id,
      forgehubProductId: null,
    });
    setPendingUnlinkOffer(null);
  };

  return {
    linkedOffers,
    unlinkedOffers,
    isLinking,
    selectedOfferId,
    pendingUnlinkOffer,
    isLoading,
    isMutating: linkMutation.isPending,
    error: (linkMutation.error || queryError) as Error | null,
    startLinking,
    cancelLinking,
    setSelectedOfferId,
    linkOffer,
    confirmUnlink,
    cancelUnlink,
    executeUnlink,
  };
}
