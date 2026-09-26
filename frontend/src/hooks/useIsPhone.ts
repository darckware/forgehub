import { useCallback, useEffect, useState } from "react";

/**
 * Phone-width helpers for the mobile layout pass (2026-09-26, see
 * docs/architecture/MOBILE_RESPONSIVE_PLAN.md). The line is 768px -- the
 * same as Tailwind's `md` and the Sidebar's MOBILE_BREAKPOINT -- so a
 * component can mix these with `max-md:`/`md:` classes without the two
 * disagreeing about what "phone" means.
 *
 * Prefer CSS variants (`max-md:`) for anything purely visual; reach for these
 * only when behavior differs (e.g. picking an item should also close a
 * panel), since a hook re-renders and CSS doesn't.
 */
const PHONE_QUERY = "(max-width: 767px)";

/** One-off check, for event handlers. */
export function isPhoneViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia(PHONE_QUERY).matches;
}

/** Reactive version -- follows rotation and window resizes. */
export function useIsPhone(): boolean {
  const [isPhone, setIsPhone] = useState(isPhoneViewport);
  useEffect(() => {
    const query = window.matchMedia(PHONE_QUERY);
    const onChange = () => setIsPhone(query.matches);
    onChange();
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return isPhone;
}

export interface PhoneListDetail {
  isPhone: boolean;
  /** Render the list column? Always true on a wider screen. */
  showList: boolean;
  /** Render the detail column? Always true on a wider screen. */
  showDetail: boolean;
  /** Call when an item is picked -- on a phone this swaps list for detail. */
  openDetail: () => void;
  /** The detail view's "back" button -- on a phone this swaps back. */
  backToList: () => void;
}

/**
 * Split screens (a list beside the item it opens -- Messages, Docs, the
 * database schema browser) leave the detail a few pixels wide on a phone.
 * There, show one at a time instead: the list first, the detail once
 * something is picked, with a back button. On a wider screen both stay
 * visible exactly as before. Same idea the Workspace's Channels pane
 * already uses for its channel list.
 *
 * `hasSelection` only decides where a phone starts: a restored selection
 * opens straight into it, like a mail app reopening the last message.
 */
export function usePhoneListDetail(hasSelection: boolean): PhoneListDetail {
  const isPhone = useIsPhone();
  const [detailOpen, setDetailOpen] = useState(hasSelection);
  const openDetail = useCallback(() => setDetailOpen(true), []);
  const backToList = useCallback(() => setDetailOpen(false), []);
  return {
    isPhone,
    showList: !isPhone || !detailOpen,
    showDetail: !isPhone || detailOpen,
    openDetail,
    backToList,
  };
}
