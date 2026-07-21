import { useCallback, useEffect, useRef, useState } from "react";

/** Wraps the native Fullscreen API for a single ref'd element -- lets a
 * document's content pane fill the whole screen (browser chrome and all),
 * distinct from just hiding the directory tree card within the page's own
 * layout (see DocumentWorkspace/DocumentBrowser's hideTree toggle). */
export function useElementFullscreen<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    function handleChange() {
      setIsFullscreen(document.fullscreenElement === ref.current);
    }
    document.addEventListener("fullscreenchange", handleChange);
    return () => document.removeEventListener("fullscreenchange", handleChange);
  }, []);

  const toggle = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      ref.current?.requestFullscreen();
    }
  }, []);

  return { ref, isFullscreen, toggle };
}
