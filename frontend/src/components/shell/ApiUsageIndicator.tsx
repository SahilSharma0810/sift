import { useApiUsageQuery } from "@/state/usage";

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

function toneFor(
  percent: number,
  exhausted: boolean,
): {
  bar: string;
  dot: string;
  label: string;
} {
  if (exhausted)
    return {
      bar: "bg-[#ff453a]",
      dot: "bg-[#ff453a]",
      label: "text-[#ffb4ae]",
    };
  if (percent >= 0.8)
    return {
      bar: "bg-[#ffb95f]",
      dot: "bg-[#ffb95f]",
      label: "text-[#ffd9a8]",
    };
  return {
    bar: "bg-[#6fd393]",
    dot: "bg-[#6fd393]",
    label: "text-light-muted",
  };
}

export function ApiUsageIndicator() {
  const { data, isLoading, isError } = useApiUsageQuery();

  if (isLoading || isError || !data) return null;

  const percent = Math.min(1, Math.max(0, data.percent_used));
  const widthPct = `${(percent * 100).toFixed(1)}%`;
  const tone = toneFor(percent, data.exhausted);

  return (
    <div
      className="mx-3 mb-2 mt-1 px-3 py-2.5"
      data-tour="api-usage"
      style={{ borderTop: "1px solid var(--hairline-on-dark)" }}
    >
      <div className="mb-1.5 flex items-center justify-between text-[10.5px] font-medium uppercase tracking-[0.08em] text-light-subtle">
        <span className="flex items-center gap-1.5">
          <span className={`inline-block size-1.5 rounded-full ${tone.dot}`} />
          API spend
        </span>
        <span className="font-mono text-[10px] text-light-subtle">
          {data.call_count} {data.call_count === 1 ? "call" : "calls"}
        </span>
      </div>

      <div className="flex items-baseline justify-between gap-2 font-mono text-[12px] tabular-nums">
        <span className="text-light">{formatUsd(data.spent_usd)}</span>
        <span className="text-light-subtle">/ {formatUsd(data.limit_usd)}</span>
      </div>

      <div
        className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-valuenow={Math.round(percent * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="API spend used"
      >
        <div
          className={`h-full ${tone.bar} transition-[width] duration-300 ease-out`}
          style={{ width: widthPct }}
        />
      </div>

      {data.exhausted && (
        <div className={`mt-2 text-[11px] leading-tight ${tone.label}`}>
          Limit reached. New extractions and search translations will be blocked
          until the cap is raised.
        </div>
      )}
    </div>
  );
}
