import type { ReactNode } from "react";
import { Chevron } from "../ui/icons";

type Tone = "neutral" | "go" | "wait" | "critical" | "info";

/**
 * One number, one label, one place it leads. The smallest unit on a screen:
 * read it at a glance, click it to go one level deeper.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
  onOpen,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  icon?: ReactNode;
  onOpen?: () => void;
}) {
  const body = (
    <>
      <div className="tile-top">
        {icon && <span className={`tile-icon ${tone}`}>{icon}</span>}
        <span className="tile-label">{label}</span>
      </div>
      <div className={`tile-value ${tone}`}>{value}</div>
      {hint && <div className="tile-hint">{hint}</div>}
      {onOpen && (
        <span className="tile-open">
          Open <Chevron size={10} />
        </span>
      )}
    </>
  );

  return onOpen ? (
    <button type="button" className="tile interactive" onClick={onOpen}>
      {body}
    </button>
  ) : (
    <div className="tile">{body}</div>
  );
}
