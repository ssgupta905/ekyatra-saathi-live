import { useLayoutEffect, useRef, useState } from "react";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/**
 * A tab/segmented switch with one sliding indicator, the same mechanism
 * everywhere it's used — the family detail tabs, the view switch, the
 * pending-approvals master list — so navigating this console always feels
 * like one system rather than several different widgets that happen to
 * look similar.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  "aria-label": ariaLabel,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  "aria-label": string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const active = container.querySelector<HTMLButtonElement>('button[aria-pressed="true"]');
    if (!active) return;
    setIndicator({ left: active.offsetLeft, width: active.offsetWidth });
  }, [value, options]);

  return (
    <div className="segmented-control" role="group" aria-label={ariaLabel} ref={containerRef}>
      {indicator && (
        <span
          className="indicator"
          style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }}
          aria-hidden="true"
        />
      )}
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
