"use client";

import { type RefObject, useEffect } from "react";

/**
 * Calls `onOutside` when a pointer goes down anywhere outside `ref` while `active` is true.
 * A touch readout has no hover to end it, so it stays until the reader taps elsewhere.
 */
export function useTapOutside(
  ref: RefObject<Element | null>,
  active: boolean,
  onOutside: () => void,
) {
  useEffect(() => {
    if (!active) return;
    const handle = (e: PointerEvent) => {
      const el = ref.current;
      if (el && e.target instanceof Node && !el.contains(e.target)) onOutside();
    };
    document.addEventListener("pointerdown", handle);
    return () => document.removeEventListener("pointerdown", handle);
  }, [ref, active, onOutside]);
}
