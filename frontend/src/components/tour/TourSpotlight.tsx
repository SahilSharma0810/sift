import { useTourTarget } from "@/components/tour/useTourTarget";

const PAD = 8;

export function TourSpotlight({ selector }: { selector: string }) {
  const rect = useTourTarget(selector);

  if (!rect) {
    return (
      <div
        className="pointer-events-none fixed inset-0 z-[80] bg-tile/40"
        aria-hidden="true"
      />
    );
  }

  const x = Math.max(0, rect.left - PAD);
  const y = Math.max(0, rect.top - PAD);
  const w = rect.width + PAD * 2;
  const h = rect.height + PAD * 2;

  return (
    <svg
      className="pointer-events-none fixed inset-0 z-[80] h-screen w-screen"
      aria-hidden="true"
    >
      <defs>
        <mask id="sift-tour-cutout">
          <rect x="0" y="0" width="100%" height="100%" fill="white" />
          <rect x={x} y={y} width={w} height={h} rx="6" fill="black" />
        </mask>
      </defs>
      <rect
        x="0"
        y="0"
        width="100%"
        height="100%"
        fill="rgb(29 29 31 / 0.55)"
        mask="url(#sift-tour-cutout)"
      />
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx="6"
        fill="none"
        stroke="#0066cc"
        strokeWidth="2"
      />
    </svg>
  );
}
