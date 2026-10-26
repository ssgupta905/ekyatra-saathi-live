/**
 * Navigation and chrome glyphs for the control centre, drawn in the same hand as
 * `@saathi/ui-web`'s icons: 1.8px stroke on a 20px box, currentColor.
 */

type P = { size?: number };

const box = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 20 20",
  fill: "none" as const,
  stroke: "currentColor" as const,
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const Home = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M3.5 9.2 10 3.8l6.5 5.4V16a.8.8 0 0 1-.8.8H12.4v-4.6H7.6v4.6H4.3a.8.8 0 0 1-.8-.8z" />
  </svg>
);
export const Users = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <circle cx="7.5" cy="7" r="2.8" />
    <path d="M2.8 16.2c.6-2.6 2.4-4 4.7-4s4.1 1.4 4.7 4" />
    <path d="M13 4.6a2.6 2.6 0 0 1 0 5M14.6 12.4c1.4.4 2.3 1.6 2.6 3.6" />
  </svg>
);
export const Approve = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M4 3.8h12v9.4l-6 3-6-3z" />
    <path d="m7.2 9.4 2 2 3.8-4.2" />
  </svg>
);
export const FileText = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M5 2.8h6.6L15 6.2v10.2a.8.8 0 0 1-.8.8H5.8a.8.8 0 0 1-.8-.8z" />
    <path d="M11.4 2.8v3.6H15M7.6 10.2h4.8M7.6 13.2h4.8" />
  </svg>
);
export const Graph = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <circle cx="4.6" cy="10" r="1.8" />
    <circle cx="15.4" cy="4.8" r="1.8" />
    <circle cx="15.4" cy="15.2" r="1.8" />
    <path d="M6.3 9.2l7.4-3.6M6.3 10.8l7.4 3.6" />
  </svg>
);
export const Alert = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M10 3.4 17.2 16H2.8z" />
    <path d="M10 8.2v3.4M10 13.7v.1" />
  </svg>
);
export const Inbox = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M3.2 11.4 5.4 4.2h9.2l2.2 7.2v4.4a.8.8 0 0 1-.8.8H4a.8.8 0 0 1-.8-.8z" />
    <path d="M3.2 11.4h4l1 1.8h3.6l1-1.8h4" />
  </svg>
);
export const UserPlus = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <circle cx="8" cy="7" r="3" />
    <path d="M2.8 16.4c.6-2.8 2.6-4.2 5.2-4.2 1.3 0 2.4.3 3.3 1M15 11v5M12.5 13.5h5" />
  </svg>
);
export const Chart = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M3.4 16.6h13.2M5.6 13.6V9.8M9.4 13.6V5.6M13.2 13.6v-6" />
  </svg>
);
export const Building = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M4 16.8V4.2a.8.8 0 0 1 .8-.8h6.4a.8.8 0 0 1 .8.8v12.6M12 8h3.2a.8.8 0 0 1 .8.8v8M2.8 16.8h14.4" />
    <path d="M6.8 6.6h2.4M6.8 9.6h2.4M6.8 12.6h2.4" />
  </svg>
);
export const Sliders = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <path d="M4 5.4h7M14.6 5.4H16M4 10h2M9.6 10H16M4 14.6h7M14.6 14.6H16" />
    <circle cx="12.8" cy="5.4" r="1.8" />
    <circle cx="7.8" cy="10" r="1.8" />
    <circle cx="12.8" cy="14.6" r="1.8" />
  </svg>
);
export const Ledger = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <rect x="3.6" y="3" width="12.8" height="14" rx="1.4" />
    <path d="M7 3v14M9.6 7h4.4M9.6 10h4.4M9.6 13h3" />
  </svg>
);
export const Film = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <rect x="3" y="4.4" width="14" height="11.2" rx="1.6" />
    <path d="m8.6 7.6 3.8 2.4-3.8 2.4z" />
  </svg>
);
export const Dial = ({ size = 18 }: P) => (
  <svg {...box(size)}>
    <circle cx="10" cy="10" r="7" />
    <path d="M10 10 13.2 6.8M10 4.6v1.2M15.4 10h-1.2M4.6 10h1.2" />
  </svg>
);
export const SearchIcon = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <circle cx="8.8" cy="8.8" r="5.2" />
    <path d="m12.8 12.8 3.6 3.6" />
  </svg>
);
export const Close = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <path d="m5 5 10 10M15 5 5 15" />
  </svg>
);
export const ChevronDown = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <path d="m5.6 7.8 4.4 4.4 4.4-4.4" />
  </svg>
);
export const ChevronRight = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <path d="m7.8 5.6 4.4 4.4-4.4 4.4" />
  </svg>
);
export const Pulse = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <path d="M2.8 10.4h3l1.8-4.6 3.2 9 2-5.4h4.4" />
  </svg>
);
export const LogOut = ({ size = 16 }: P) => (
  <svg {...box(size)}>
    <path d="M8 4H4.8a.8.8 0 0 0-.8.8v10.4a.8.8 0 0 0 .8.8H8M12.4 6.6 15.8 10l-3.4 3.4M15.6 10H8" />
  </svg>
);
export const Logo = ({ size = 28 }: P) => (
  <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden>
    <rect width="28" height="28" rx="8" fill="var(--blue-500)" />
    <path d="M8 17.5c1.6 2 3.8 3 6 3 3.3 0 5.6-1.8 5.6-4.4 0-5.4-10.8-3.3-10.8-8 0-2 1.9-3.4 4.6-3.4 1.8 0 3.4.6 4.6 1.8"
      stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none" />
  </svg>
);
