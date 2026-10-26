import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ChevronDown, Close } from "./icons";

/* ── page header ─────────────────────────────────────────────────────────── */

export function PageHeader({ title, lead, actions }: { title: string; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ui-page-head">
      <div>
        <h1>{title}</h1>
        {lead && <p>{lead}</p>}
      </div>
      {actions && <div className="ui-page-actions">{actions}</div>}
    </header>
  );
}

/* ── stat tile: one number, what it means, where it leads ────────────────── */

export type Tone = "neutral" | "go" | "wait" | "uncertain" | "critical" | "brand";

export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
  onClick,
  loading,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  onClick?: () => void;
  loading?: boolean;
}) {
  const body = (
    <>
      <div className="ui-stat-top">
        {icon && <span className={`ui-stat-icon ${tone}`}>{icon}</span>}
        <span className="ui-stat-label">{label}</span>
      </div>
      {loading ? <Skeleton width={56} height={30} /> : <div className={`ui-stat-value ${tone}`}>{value}</div>}
      {hint && <div className="ui-stat-hint">{hint}</div>}
    </>
  );
  return onClick ? (
    <button type="button" className="ui-stat interactive" onClick={onClick}>
      {body}
    </button>
  ) : (
    <div className="ui-stat">{body}</div>
  );
}

/* ── panel: a titled surface ─────────────────────────────────────────────── */

export function Panel({
  title,
  hint,
  actions,
  children,
  flush,
}: {
  title?: ReactNode;
  hint?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className="ui-panel">
      {(title || actions) && (
        <header>
          <div>
            {title && <h2>{title}</h2>}
            {hint && <p>{hint}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={flush ? "ui-panel-body flush" : "ui-panel-body"}>{children}</div>
    </section>
  );
}

/* ── layers: sections that open on demand and mount only when open ───────── */

export function Layer({
  id,
  title,
  summary,
  icon,
  open,
  onToggle,
  children,
  tone,
}: {
  id: string;
  title: string;
  /** One line said while closed, so a person knows whether to open it. */
  summary?: ReactNode;
  icon?: ReactNode;
  open: boolean;
  onToggle: (id: string) => void;
  children: () => ReactNode;
  tone?: Tone;
}) {
  return (
    <section className={`ui-layer${open ? " open" : ""}`} data-layer={id}>
      <button
        type="button"
        className="ui-layer-head"
        aria-expanded={open}
        aria-controls={`layer-${id}`}
        onClick={() => onToggle(id)}
      >
        {icon && <span className={`ui-layer-icon ${tone ?? "neutral"}`}>{icon}</span>}
        <span className="ui-layer-title">{title}</span>
        {summary && <span className="ui-layer-summary">{summary}</span>}
        <span className="ui-layer-chevron">
          <ChevronDown />
        </span>
      </button>
      {open && (
        <div className="ui-layer-body" id={`layer-${id}`}>
          {children()}
        </div>
      )}
    </section>
  );
}

/* ── drawer: detail beside the page, not instead of it ───────────────────── */

export function Drawer({
  open,
  title,
  onClose,
  children,
  width = 520,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="ui-drawer-wrap" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="ui-drawer" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} style={{ width }}>
        <header>
          <h2>{title}</h2>
          <button type="button" className="ui-icon-btn" onClick={onClose} aria-label="Close">
            <Close />
          </button>
        </header>
        <div className="ui-drawer-body">{children}</div>
      </aside>
    </div>
  );
}

/* ── toasts: say that an action happened, then get out of the way ────────── */

interface Toast {
  id: number;
  text: string;
  tone: "ok" | "error";
}

const ToastContext = createContext<(text: string, tone?: Toast["tone"]) => void>(() => undefined);

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = ++seq.current;
    setToasts((all) => [...all, { id, text, tone }]);
    window.setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="ui-toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`ui-toast ${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ── loading and emptiness ───────────────────────────────────────────────── */

export const Skeleton = ({ width = "100%", height = 14 }: { width?: number | string; height?: number }) => (
  <span className="ui-skeleton" style={{ width, height }} />
);

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="ui-skeleton-rows">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} width={`${90 - i * 12}%`} />
      ))}
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="ui-empty">
      {icon && <div className="ui-empty-icon">{icon}</div>}
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

/* ── pills and filter chips ──────────────────────────────────────────────── */

export const Pill = ({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) => (
  <span className={`ui-pill ${tone}`}>{children}</span>
);

export function FilterChips<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="ui-chips" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count != null && <span className="ui-chip-count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Remember which layers a person opened, per screen, across reloads. */
export function useOpenLayers(key: string, initial: string[]): [Set<string>, (id: string) => void, (id: string) => void] {
  const storageKey = `saathi.layers.${key}`;
  const [open, setOpen] = useState<Set<string>>(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) return new Set(JSON.parse(raw) as string[]);
    } catch {
      /* fall through */
    }
    return new Set(initial);
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify([...open]));
    } catch {
      /* per-tab only */
    }
  }, [open, storageKey]);
  const toggle = useCallback((id: string) => {
    setOpen((now) => {
      const next = new Set(now);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const ensure = useCallback((id: string) => setOpen((now) => (now.has(id) ? now : new Set([...now, id]))), []);
  return useMemo(() => [open, toggle, ensure], [open, toggle, ensure]);
}
