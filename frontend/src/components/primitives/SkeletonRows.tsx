type Props = {
  rows?: number;
  /** Per-cell width preset in percent or px. Length defines the column count. */
  cols: Array<number | string>;
};

const SHIMMER_BG =
  "linear-gradient(90deg, rgb(229 229 233 / 0.55) 0%, rgb(245 245 247) 50%, rgb(229 229 233 / 0.55) 100%)";

function Bar({ width }: { width: number | string }) {
  const w = typeof width === "number" ? `${width}%` : width;
  return (
    <div
      className="h-3 rounded-sm motion-reduce:animate-none"
      style={{
        width: w,
        backgroundImage: SHIMMER_BG,
        backgroundSize: "200% 100%",
        animationName: "shimmer",
        animationDuration: "1.6s",
        animationTimingFunction: "ease-in-out",
        animationIterationCount: "infinite",
      }}
      aria-hidden="true"
    />
  );
}

export function SkeletonRows({ rows = 5, cols }: Props) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <tr key={`skeleton-${rowIdx}`} aria-hidden="true">
          {cols.map((w, colIdx) => (
            <td key={colIdx} className="py-3">
              <Bar width={w} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
