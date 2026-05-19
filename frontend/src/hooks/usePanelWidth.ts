import { useCallback, useState } from "react";

type Options = {
  storageKey: string;
  defaultWidth: number;
  min: number;
  max: number;
};

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

export function usePanelWidth({ storageKey, defaultWidth, min, max }: Options) {
  const [width, setWidth] = useState<number>(() => {
    if (typeof window === "undefined") return defaultWidth;
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) return clamp(defaultWidth, min, max);
    const n = Number.parseInt(stored, 10);
    return Number.isFinite(n)
      ? clamp(n, min, max)
      : clamp(defaultWidth, min, max);
  });

  const setAndPersist = useCallback(
    (next: number) => {
      const clamped = clamp(next, min, max);
      setWidth(clamped);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(storageKey, String(clamped));
      }
    },
    [storageKey, min, max],
  );

  return [width, setAndPersist] as const;
}
