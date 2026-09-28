"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The rendered width of the element `ref` is attached to, kept current with a
 * ResizeObserver. Charts draw at this width so their text stays at its real size on a
 * phone; before hydration (and in the static HTML) they draw at `fallback` and scale.
 */
export function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const w = Math.floor(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Approximate rendered width of monospace text (Geist Mono advances 0.6em per glyph). */
export function textWidth(s: string, fontSize: number): number {
  return s.length * fontSize * 0.6;
}
