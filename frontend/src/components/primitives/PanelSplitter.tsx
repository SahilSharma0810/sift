import {
  useCallback,
  useState,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent,
} from "react";

type Props = {
  width: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  /** Set true when the resizable panel sits on the RIGHT of the splitter.
   *  Then dragging left increases its width. Defaults to right-side. */
  side?: "right" | "left";
  className?: string;
  ariaLabel?: string;
};

const KB_STEP = 16;

export function PanelSplitter({
  width,
  onChange,
  min,
  max,
  side = "right",
  className,
  ariaLabel = "Resize panel",
}: Props) {
  const [dragging, setDragging] = useState(false);

  const clamp = useCallback(
    (n: number) => Math.max(min, Math.min(max, n)),
    [min, max],
  );

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    setDragging(true);
    const startX = e.clientX;
    const startW = width;
    const sign = side === "right" ? -1 : 1;

    const onMove = (ev: PointerEvent) => {
      const delta = (ev.clientX - startX) * sign;
      onChange(clamp(startW + delta));
    };
    const onUp = (ev: PointerEvent) => {
      try {
        el.releasePointerCapture(ev.pointerId);
      } catch {
        // already released
      }
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const grow = side === "right" ? "ArrowLeft" : "ArrowRight";
    const shrink = side === "right" ? "ArrowRight" : "ArrowLeft";
    if (e.key === grow) {
      e.preventDefault();
      onChange(clamp(width + KB_STEP));
    } else if (e.key === shrink) {
      e.preventDefault();
      onChange(clamp(width - KB_STEP));
    }
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={width}
      aria-label={ariaLabel}
      tabIndex={0}
      data-active={dragging || undefined}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      className={className}
    />
  );
}
