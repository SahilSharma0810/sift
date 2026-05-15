// The Sift mark — the primary brand element. A 4×4 grid where the bottom row
// has fallen through the sieve, leaving one Action-Blue cell. Reads as a
// sieve from a distance, as data triage up close. See
// docs/logo or the brand README for the don'ts (no rotation, no rounded
// corners, no recoloring of cells — only one cell highlights).
//
// Colors are pulled from the existing CSS custom properties in sift.css
// (`--ink`, `--primary`, `--on-dark`, `--primary-on-dark`) so the mark stays
// in lockstep with the design tokens used everywhere else.

type SiftMarkProps = {
  /** Pixel size (square). Designed to survive down to 16px. */
  size?: number
  /** Set when the mark sits on a dark surface — flips squares to white and
   *  uses the on-dark blue for the highlighted cell. */
  dark?: boolean
  /** Optional className passthrough for layout (e.g. `shrink-0`). */
  className?: string
  /** Accessible label. Defaults to "Sift". Pass `''` to mark decorative. */
  label?: string
}

export function SiftMark({
  size = 24,
  dark = false,
  className,
  label = 'Sift',
}: SiftMarkProps) {
  const fill = dark ? 'var(--on-dark)' : 'var(--ink)'
  const accent = dark ? 'var(--primary-on-dark)' : 'var(--primary)'

  const a11y = label
    ? { role: 'img' as const, 'aria-label': label }
    : { 'aria-hidden': true as const }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      {...a11y}
    >
      {/* Top 2 rows — raw input. Every invoice that arrives. */}
      <rect x="8" y="8" width="20" height="20" fill={fill} />
      <rect x="30" y="8" width="20" height="20" fill={fill} />
      <rect x="52" y="8" width="20" height="20" fill={fill} />
      <rect x="74" y="8" width="20" height="20" fill={fill} />
      <rect x="8" y="30" width="20" height="20" fill={fill} />
      <rect x="30" y="30" width="20" height="20" fill={fill} />
      <rect x="52" y="30" width="20" height="20" fill={fill} />
      <rect x="74" y="30" width="20" height="20" fill={fill} />
      {/* Row 3 — the sieve filtering. One cell has fallen through. */}
      <rect x="8" y="52" width="20" height="20" fill={fill} />
      <rect x="30" y="52" width="20" height="20" fill={fill} />
      <rect x="52" y="52" width="20" height="20" fill={fill} />
      {/* Row 4 — the result. The blue cell is the one that needs attention. */}
      <rect x="30" y="74" width="20" height="20" fill={fill} />
      <rect x="74" y="74" width="20" height="20" fill={accent} />
    </svg>
  )
}
