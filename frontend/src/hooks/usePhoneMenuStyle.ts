import { useLayoutEffect, useState, type CSSProperties, type RefObject } from "react";
import { useIsPhone } from "@/hooks/useIsPhone";

/**
 * Inline `top`/`max-height` for a toolbar dropdown that becomes
 * `max-md:fixed max-md:inset-x-2` on a phone (full-width, so a button wrapped
 * near either edge can't push it off-screen).
 *
 * `fixed` alone isn't enough: the menu keeps its `top-full`, which for a
 * fixed box means 100% of the *viewport* -- the menu opened just below the
 * bottom edge and looked empty (SSH and Runtimes, 2026-09-27). So on a phone
 * it's placed under the anchor measured here, and capped to the space left
 * below it so a long list scrolls instead of running off the bottom. On a
 * wider screen this returns `undefined` and the classes' `absolute top-full`
 * applies unchanged.
 */
export function usePhoneMenuStyle(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
): CSSProperties | undefined {
  const isPhone = useIsPhone();
  const [top, setTop] = useState<number | null>(null);

  useLayoutEffect(() => {
    if (!open || !isPhone) return;
    const measure = () => {
      const rect = anchorRef.current?.getBoundingClientRect();
      if (rect) setTop(rect.bottom + 4);
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [anchorRef, open, isPhone]);

  if (!isPhone || !open || top === null) return undefined;
  return { top, maxHeight: `calc(100dvh - ${top + 8}px)`, overflowY: "auto" };
}
