import { useCallback, useEffect, useState } from "react";

/**
 * Where the control centre is, in the address bar: `#/section/id/tab`.
 *
 * A URL a navigator can paste to a colleague ("look at #/families/P-ANITA/why")
 * and that survives a reload, with no router dependency for four path segments.
 */
export interface Route {
  section: string;
  id: string | null;
  tab: string | null;
}

function parse(hash: string): Route {
  const [section = "", id = null, tab = null] = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  return { section, id: id || null, tab: tab || null };
}

export function useRoute(fallback: string): [Route, (next: Partial<Route> & { section?: string }) => void] {
  const [route, setRoute] = useState<Route>(() => {
    const parsed = parse(window.location.hash);
    if (parsed.section) return parsed;
    const initial = new URLSearchParams(window.location.search).get("section");
    return { section: initial ?? fallback, id: null, tab: null };
  });

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const go = useCallback(
    (next: Partial<Route>) => {
      const merged = { ...route, ...next };
      if (next.section && next.section !== route.section && next.id === undefined) merged.id = null;
      if (next.id !== undefined && next.tab === undefined && next.id !== route.id) merged.tab = null;
      const parts = [merged.section, merged.id, merged.tab].filter(Boolean).map((p) => encodeURIComponent(p!));
      window.location.hash = `/${parts.join("/")}`;
      setRoute(merged);
    },
    [route],
  );

  return [route, go];
}
