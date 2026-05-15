type IconProps = { d: string; size?: number; fill?: string; strokeWidth?: number }

const Icon = ({ d, size = 14, fill = 'none', strokeWidth = 1.75 }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d={d} />
  </svg>
)

export const Icons = {
  inbox: () => <Icon d="M3 13l3-8h12l3 8M3 13v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6M3 13h5l1 3h6l1-3h5" />,
  search: () => <Icon d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3" />,
  bell: () => <Icon d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16l-2-2zM9 19a3 3 0 0 0 6 0" />,
  spark: () => <Icon d="M12 3v3M12 18v3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M3 12h3M18 12h3M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />,
  vendor: () => <Icon d="M3 21h18M5 21V8l7-4 7 4v13M9 21V13h6v8" />,
  doc: () => <Icon d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 13h6M9 17h4" />,
  upload: () => <Icon d="M12 16V4M6 10l6-6 6 6M4 20h16" />,
  check: () => <Icon d="M5 12l5 5L20 7" />,
  x: () => <Icon d="M6 6l12 12M18 6 6 18" />,
  warn: () => <Icon d="M12 9v4M12 17h.01M10.3 4l-8 14a2 2 0 0 0 1.7 3h16a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.4 0z" />,
  alert: () => <Icon d="M12 8v4M12 16h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />,
  copy: () => <Icon d="M8 4h10a2 2 0 0 1 2 2v10M16 8H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />,
  hash: () => <Icon d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18" />,
  brain: () => <Icon d="M9 4a3 3 0 0 0-3 3v0a3 3 0 0 0-1 5.8V15a3 3 0 0 0 4 2.8V21M15 4a3 3 0 0 1 3 3v0a3 3 0 0 1 1 5.8V15a3 3 0 0 1-4 2.8V21" />,
  bot: () => <Icon d="M9 2v3M15 2v3M5 8h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zM9 13h.01M15 13h.01" />,
  pen: () => <Icon d="M12 19l7-7 3 3-7 7-3-3zM18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5zM2 2l7.6 7.6M11 11a2 2 0 1 0 4 0 2 2 0 0 0-4 0z" />,
  lock: () => <Icon d="M5 12h14a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1zM8 12V7a4 4 0 1 1 8 0v5" />,
  refresh: () => <Icon d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" />,
  arrowL: () => <Icon d="M19 12H5M12 19l-7-7 7-7" />,
  chevron: () => <Icon d="M9 18l6-6-6-6" />,
  filter: () => <Icon d="M3 5h18M6 12h12M10 19h4" />,
  layers: () => <Icon d="M12 2 2 8l10 6 10-6-10-6zM2 16l10 6 10-6M2 12l10 6 10-6" />,
  command: () => <Icon d="M9 6V9H6a3 3 0 1 1 3-3zM15 6V9h3a3 3 0 1 0-3-3zM9 18v-3H6a3 3 0 1 0 3 3zM15 18v-3h3a3 3 0 1 1-3 3zM9 9h6v6H9z" />,
  dollar: () => <Icon d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />,
  plus: () => <Icon d="M12 5v14M5 12h14" />,
  cascade: () => <Icon d="M4 6h10l2 3 2-3h2M4 12h6l2 3 2-3h6M4 18h12l2 3 2-3" />,
  zap: () => <Icon d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />,
  history: () => <Icon d="M12 8v4l3 2M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" />,
  link: () => <Icon d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />,
  eye: () => <Icon d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zM12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z" />,
  download: () => <Icon d="M12 4v12M6 10l6 6 6-6M4 20h16" />,
} as const
