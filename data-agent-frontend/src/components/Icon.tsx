import type { SVGProps } from 'react'

export type IconName =
  | 'arrow-left'
  | 'arrow-right'
  | 'archive'
  | 'attach'
  | 'bot'
  | 'chart'
  | 'check'
  | 'chevron-down'
  | 'chevron-right'
  | 'code'
  | 'copy'
  | 'database'
  | 'download'
  | 'external'
  | 'info'
  | 'menu'
  | 'more'
  | 'pause'
  | 'plus'
  | 'search'
  | 'send'
  | 'settings'
  | 'shield'
  | 'stop'
  | 'table'
  | 'terminal'
  | 'wave'

type IconProps = SVGProps<SVGSVGElement> & { name: IconName; size?: number }

const paths: Record<IconName, JSX.Element> = {
  'arrow-left': <path d="m15 18-6-6 6-6" />,
  'arrow-right': <path d="m9 18 6-6-6-6" />,
  archive: <><path d="M4 7h16v13H4z" /><path d="M3 3h18v4H3zM9 11h6" /></>,
  attach: <path d="m20.5 11.5-8.7 8.7a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 0 1 5.7 5.7L9 17.4a2 2 0 0 1-2.8-2.8l8.7-8.7" />,
  bot: <><rect x="5" y="7" width="14" height="12" rx="2" /><path d="M9 11h.01M15 11h.01M9 15h6M12 3v4" /></>,
  chart: <><path d="M4 19V5M4 19h16" /><path d="m7 15 4-4 3 2 5-6" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  'chevron-down': <path d="m6 9 6 6 6-6" />,
  'chevron-right': <path d="m9 6 6 6-6 6" />,
  code: <><path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14" /></>,
  copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" /></>,
  database: <><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /></>,
  download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M4 19h16" /></>,
  external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v6H5V6h6" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" /></>,
  pause: <><path d="M9 7v10M15 7v10" /><circle cx="12" cy="12" r="9" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  send: <path d="m21 3-8.2 18-2.4-7.4L3 11.2 21 3Zm-10.6 10.6L15 9" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  shield: <><path d="M12 3 5 6v5c0 5 3 8.5 7 10 4-1.5 7-5 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  stop: <rect x="7" y="7" width="10" height="10" rx="1" />,
  table: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 9v11" /></>,
  terminal: <><path d="m5 7 4 4-4 4M11 17h8" /><rect x="2" y="3" width="20" height="18" rx="2" /></>,
  wave: <path d="M3 12h3l2-7 4 14 3-10 2 6h4" />,
}

export function Icon({ name, size = 18, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {paths[name]}
    </svg>
  )
}
