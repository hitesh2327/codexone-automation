import { useEffect, useState } from "react";

/**
 * Appearance: Light (default), Dark, or System (follows the device, live). The choice is kept in this browser
 * (localStorage) and applied as `.dark` on <html>; index.html applies it before first paint so there is no flash.
 * Keep THEME_KEY and the logic in sync with the inline script in index.html.
 */
export type ThemePref = "light" | "dark" | "system";
export const THEME_KEY = "mintly-theme";
const EVENT = "mintly-theme-change";
const PAGE_BG = { light: "#F6F7F9", dark: "#0D1117" } as const;

const darkQuery = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null);

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "dark" || v === "system" || v === "light" ? v : "light";
  } catch {
    return "light";
  }
}

export function resolveTheme(pref: ThemePref): "light" | "dark" {
  return pref === "system" ? (darkQuery()?.matches ? "dark" : "light") : pref;
}

export function applyTheme(pref: ThemePref = getThemePref()): void {
  const resolved = resolveTheme(pref);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", PAGE_BG[resolved]);
}

export function setThemePref(pref: ThemePref): void {
  try {
    localStorage.setItem(THEME_KEY, pref);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  applyTheme(pref);
  window.dispatchEvent(new CustomEvent(EVENT));
}

/** The current preference and its resolved theme; re-renders on changes from any control and on device changes. */
export function useTheme(): { pref: ThemePref; resolved: "light" | "dark"; setPref: (p: ThemePref) => void } {
  const [pref, setPrefState] = useState<ThemePref>(getThemePref);
  const [resolved, setResolved] = useState(() => resolveTheme(getThemePref()));
  useEffect(() => {
    const sync = () => {
      const p = getThemePref();
      setPrefState(p);
      setResolved(resolveTheme(p));
    };
    const onDevice = () => {
      if (getThemePref() === "system") applyTheme("system");
      sync();
    };
    const mq = darkQuery();
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);   // another tab changed it
    mq?.addEventListener("change", onDevice);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
      mq?.removeEventListener("change", onDevice);
    };
  }, []);
  return { pref, resolved, setPref: setThemePref };
}
