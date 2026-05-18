import { useEffect, useState } from "react";

export function useTourTarget(selector: string): DOMRect | null {
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    let stopped = false;
    let raf = 0;

    const measure = (): boolean => {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) {
        setRect(null);
        return false;
      }
      const r = el.getBoundingClientRect();
      const inView =
        r.top >= 0 &&
        r.left >= 0 &&
        r.bottom <= window.innerHeight &&
        r.right <= window.innerWidth;
      if (!inView) {
        el.scrollIntoView({
          block: "center",
          inline: "center",
          behavior: "smooth",
        });
      }
      setRect(el.getBoundingClientRect());
      return true;
    };

    let attempts = 0;
    const tryFind = () => {
      if (stopped) return;
      if (measure() || attempts > 25) return;
      attempts += 1;
      window.setTimeout(tryFind, 80);
    };
    tryFind();

    const update = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(() => measure());
    };
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);

    return () => {
      stopped = true;
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [selector]);

  return rect;
}
