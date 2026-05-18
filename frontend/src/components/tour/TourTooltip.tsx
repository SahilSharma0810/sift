import type { CSSProperties } from "react";

import { Kbd } from "@/components/primitives/Kbd";
import { useTour } from "@/components/tour/TourProvider";
import { useTourTarget } from "@/components/tour/useTourTarget";
import type { TourPlacement, TourStep } from "@/components/tour/steps";

type Props = { step: TourStep; index: number; total: number };

const CARD_W = 320;
const CARD_H_EST = 200;
const GAP = 12;
const EDGE = 8;

function pickPlacement(
  rect: DOMRect,
  preferred: TourPlacement,
): "top" | "bottom" | "left" | "right" {
  if (preferred !== "auto") return preferred;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const order: Array<["top" | "bottom" | "left" | "right", number]> = [
    ["bottom", vh - rect.bottom],
    ["right", vw - rect.right],
    ["top", rect.top],
    ["left", rect.left],
  ];
  order.sort((a, b) => b[1] - a[1]);
  return order[0][0];
}

export function TourTooltip({ step, index, total }: Props) {
  const { next, back, skip } = useTour();
  const rect = useTourTarget(step.selector);
  const isLast = index === total - 1;
  const isFirst = index === 0;

  let style: CSSProperties;
  if (!rect) {
    style = {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      width: CARD_W,
    };
  } else {
    const vw = window.innerWidth;
    const side = pickPlacement(rect, step.placement ?? "auto");
    let top = 0;
    let left = 0;
    if (side === "bottom") {
      top = rect.bottom + GAP;
      left = Math.max(
        EDGE,
        Math.min(vw - CARD_W - EDGE, rect.left + rect.width / 2 - CARD_W / 2),
      );
    } else if (side === "top") {
      top = Math.max(EDGE, rect.top - GAP - CARD_H_EST);
      left = Math.max(
        EDGE,
        Math.min(vw - CARD_W - EDGE, rect.left + rect.width / 2 - CARD_W / 2),
      );
    } else if (side === "right") {
      top = Math.max(EDGE, rect.top + rect.height / 2 - CARD_H_EST / 2);
      left = rect.right + GAP;
    } else {
      top = Math.max(EDGE, rect.top + rect.height / 2 - CARD_H_EST / 2);
      left = Math.max(EDGE, rect.left - GAP - CARD_W);
    }
    style = { position: "fixed", top, left, width: CARD_W };
  }

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label={step.title}
      className="z-[90] border border-hairline bg-surface shadow-2xl"
      style={style}
    >
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
        <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-ink-60">
          {String(index + 1).padStart(2, "0")} /{" "}
          {String(total).padStart(2, "0")}
          <span className="ml-2 text-ink-48">Product tour</span>
        </span>
        <button
          type="button"
          onClick={skip}
          className="text-[11px] uppercase tracking-[0.04em] text-ink-60 transition-colors hover:text-ink"
        >
          Skip
        </button>
      </div>

      <div className="px-4 py-3.5">
        <div className="text-[14px] font-medium text-ink">{step.title}</div>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-80">
          {step.body}
        </p>
      </div>

      <div className="flex items-center justify-between border-t border-hairline px-4 py-2.5">
        <div className="flex items-center gap-1 text-[11px] text-ink-60">
          <Kbd>←</Kbd>
          <Kbd>→</Kbd>
          <span className="pl-1">to navigate</span>
        </div>
        <div className="flex gap-2">
          {!isFirst && (
            <button
              type="button"
              onClick={back}
              className="border border-hairline px-3 py-1.5 text-[12px] text-ink-80 transition-colors hover:bg-surface-recess"
            >
              Back
            </button>
          )}
          <button
            type="button"
            onClick={next}
            className="bg-action px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-action-focus"
          >
            {isLast ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
