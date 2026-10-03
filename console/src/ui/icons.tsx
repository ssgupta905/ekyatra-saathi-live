/**
 * Inline glyphs, SF-Symbols in character: 1.8px stroke on a 20px box.
 *
 * These exist because a status colour never carries meaning alone — every
 * badge, gate and pip in this console pairs its colour with one of these and
 * with a word, so the decision survives greyscale printing and colour-vision
 * deficiency alike.
 */

type P = { size?: number; className?: string };

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

export const CheckCircle = ({ size = 15, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="10" cy="10" r="7.6" />
    <path d="M6.6 10.3l2.3 2.3 4.5-4.9" />
  </svg>
);

export const Clock = ({ size = 15, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="10" cy="10" r="7.6" />
    <path d="M10 5.9V10l3 1.9" />
  </svg>
);

export const Question = ({ size = 15, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="10" cy="10" r="7.6" />
    <path d="M7.9 7.8a2.1 2.1 0 1 1 3 1.9c-.6.4-.9.9-.9 1.6" />
    <path d="M10 14.3h.01" strokeWidth="2.2" />
  </svg>
);

export const Stop = ({ size = 15, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="10" cy="10" r="7.6" />
    <path d="M7.2 7.2l5.6 5.6M12.8 7.2l-5.6 5.6" />
  </svg>
);

export const Shield = ({ size = 15, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M10 2.9l5.4 2v4.4c0 3.2-2.1 6-5.4 7.1-3.3-1.1-5.4-3.9-5.4-7.1V4.9l5.4-2z" />
  </svg>
);

export const Chevron = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M8 5.5l5 4.5-5 4.5" />
  </svg>
);

export const Phone = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <rect x="6" y="2.6" width="8" height="14.8" rx="2" />
    <path d="M9.1 15.2h1.8" />
  </svg>
);

export const Doc = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M11.4 2.8H6.6a1.4 1.4 0 0 0-1.4 1.4v11.6a1.4 1.4 0 0 0 1.4 1.4h6.8a1.4 1.4 0 0 0 1.4-1.4V6.2z" />
    <path d="M11.4 2.8v3.4h3.4" />
  </svg>
);

export const Link = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M8.3 11.7a2.8 2.8 0 0 1 0-4l1.8-1.7a2.8 2.8 0 0 1 4 4l-.8.8" />
    <path d="M11.7 8.3a2.8 2.8 0 0 1 0 4L9.9 14a2.8 2.8 0 0 1-4-4l.8-.8" />
  </svg>
);

export const Pin = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M10 17.2s5-4.4 5-8.2a5 5 0 0 0-10 0c0 3.8 5 8.2 5 8.2z" />
    <circle cx="10" cy="8.8" r="1.9" />
  </svg>
);

export const Wave = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M3 10h2.4l1.6-4.6L9.4 15l2-7.4L13 11.4l1-1.4H17" />
  </svg>
);

export const Search = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="9" cy="9" r="5.2" />
    <path d="M12.9 12.9L16.6 16.6" />
  </svg>
);

export const Play = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className} fill="currentColor" stroke="none">
    <path d="M7 4.6l8.4 5.4L7 15.4z" />
  </svg>
);

export const Pause = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className} fill="currentColor" stroke="none">
    <rect x="6.4" y="4.6" width="2.7" height="10.8" rx="0.9" />
    <rect x="10.9" y="4.6" width="2.7" height="10.8" rx="0.9" />
  </svg>
);

export const StepForward = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className} fill="currentColor" stroke="none">
    <path d="M5.4 4.6l7.2 5.4-7.2 5.4z" />
    <rect x="13.4" y="4.6" width="2.2" height="10.8" rx="0.9" />
  </svg>
);

export const Rewind = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M4.2 10a5.8 5.8 0 1 0 1.9-4.3" />
    <path d="M3.6 4.4v3.4h3.4" />
  </svg>
);

export const Spark = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M10 3.2l1.6 4.1 4.2 1.5-4.2 1.5L10 14.4l-1.6-4.1-4.2-1.5 4.2-1.5z" />
  </svg>
);

export const Bell = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M10 3.4a4 4 0 0 0-4 4c0 3.6-1.2 4.6-1.2 4.6h10.4S14 11 14 7.4a4 4 0 0 0-4-4z" />
    <path d="M8.9 15.1a1.4 1.4 0 0 0 2.2 0" />
  </svg>
);

export const Inbox = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M3.4 11.2h3.3l1.1 1.9h4.4l1.1-1.9h3.3" />
    <path d="M5.4 4.2h9.2l2 7v4.2a1.4 1.4 0 0 1-1.4 1.4H4.8a1.4 1.4 0 0 1-1.4-1.4V11.2z" />
  </svg>
);

export const Speaker = ({ size = 14, className }: P) => (
  <svg {...box(size)} className={className}>
    <path d="M5 8h2.4L10.6 5v10L7.4 12H5z" />
    <path d="M13.2 7.6a3.4 3.4 0 0 1 0 4.8" />
  </svg>
);

export const Info = ({ size = 13, className }: P) => (
  <svg {...box(size)} className={className}>
    <circle cx="10" cy="10" r="7.6" />
    <path d="M10 9.2v4.4" />
    <path d="M10 6.6h.01" strokeWidth="2.2" />
  </svg>
);
