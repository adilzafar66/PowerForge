"use client";
import { useEffect, useRef } from "react";

type Guard = {
  block: (href: string) => void;
  entry: { url: string; state: unknown };
};
let guard: Guard | null = null;

const here = () => window.location.pathname + window.location.search;

/** Hands a programmatic navigation to the active guard. True when blocked. */
export function guardNavigation(href: string) {
  if (!guard) return false;
  guard.block(href);
  return true;
}

// Registered at module load so it runs before Next's router listener, which
// would otherwise render the destination before the guard can restore it.
if (typeof window !== "undefined")
  window.addEventListener(
    "popstate",
    (event) => {
      if (!guard) return;
      const href = here();
      event.stopImmediatePropagation();
      window.history.pushState(guard.entry.state, "", guard.entry.url);
      if (href !== guard.entry.url) guard.block(href);
    },
    true,
  );

/**
 * While enabled, intercepts in-app link clicks, guarded programmatic
 * navigation and browser Back/Forward, and reports the intended destination.
 */
export function useNavigationBlocker(
  enabled: boolean,
  onBlocked: (href: string) => void,
) {
  const handler = useRef(onBlocked);
  handler.current = onBlocked;
  const current = useRef<Guard | null>(null);
  useEffect(() => {
    if (current.current)
      current.current.entry = { url: here(), state: window.history.state };
  });
  useEffect(() => {
    if (!enabled) return;
    const active: Guard = {
      block: (href) => handler.current(href),
      entry: { url: here(), state: window.history.state },
    };
    current.current = guard = active;
    function click(event: MouseEvent) {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (
        !(link instanceof HTMLAnchorElement) ||
        (link.target && link.target !== "_self") ||
        link.hasAttribute("download")
      )
        return;
      const url = new URL(link.href, window.location.href);
      const href = url.pathname + url.search;
      if (url.origin !== window.location.origin || href === here()) return;
      // Link handlers still run (closing menus) but skip navigation.
      event.preventDefault();
      active.block(href);
    }
    document.addEventListener("click", click, true);
    return () => {
      if (guard === active) guard = null;
      current.current = null;
      document.removeEventListener("click", click, true);
    };
  }, [enabled]);
}
