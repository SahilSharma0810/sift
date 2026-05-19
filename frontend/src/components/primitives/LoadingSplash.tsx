import { SiftMark } from "@/components/primitives/SiftMark";

type Props = {
  message?: string;
  size?: "full" | "page";
};

export function LoadingSplash({ message = "Sifting", size = "full" }: Props) {
  const isFull = size === "full";
  const wrapper = isFull
    ? "grid h-screen w-full place-items-center bg-canvas"
    : "grid min-h-[240px] w-full place-items-center py-10";
  const markSize = isFull ? 44 : 32;
  const barW = isFull ? "w-48" : "w-32";

  return (
    <div className={wrapper} role="status" aria-live="polite" aria-busy="true">
      <div className="flex flex-col items-center gap-5">
        <div className="animate-sift-pulse motion-reduce:animate-none">
          <SiftMark size={markSize} label="" />
        </div>

        <div className={`relative h-px ${barW} overflow-hidden bg-hairline`}>
          <div className="absolute inset-y-0 left-0 w-1/4 bg-action animate-indeterminate motion-reduce:animate-none motion-reduce:w-full motion-reduce:opacity-50" />
        </div>

        <div className="flex items-baseline gap-0.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-60">
          <span>{message}</span>
          <span aria-hidden="true" className="ml-0.5 inline-flex">
            <span
              className="animate-loading-dot motion-reduce:animate-none"
              style={{ animationDelay: "0ms" }}
            >
              .
            </span>
            <span
              className="animate-loading-dot motion-reduce:animate-none"
              style={{ animationDelay: "180ms" }}
            >
              .
            </span>
            <span
              className="animate-loading-dot motion-reduce:animate-none"
              style={{ animationDelay: "360ms" }}
            >
              .
            </span>
          </span>
        </div>
      </div>
      <span className="sr-only">{message}, please wait</span>
    </div>
  );
}
