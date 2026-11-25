import { useCallback, useEffect, useState } from "react";
import {
  kharcha as books,
  type Kharcha as KharchaData,
  type MonthOutlook,
  type NudgeKind,
  type SpendCategory,
} from "@saathi/api-client";
import type { Lang, Strings } from "@saathi/i18n";
import { Info, Shield } from "@saathi/ui-web";

/**
 * Kharcha: what the journey is costing this family, and what next month will.
 *
 * Only the family sees this page; nobody at the hospital can open it. If a
 * month looks like more than they said they can manage, the hospital is told
 * that help is wanted — never the figures.
 *
 * Every number on it can say where it came from ("why this number"): their own
 * words, a provider's price, or their own last trips repeated. When there is
 * nothing to work from, the page says so instead of showing a typical cost.
 */

const LOCALE: Record<Lang, string> = { hi: "hi-IN", bn: "bn-IN", or: "or-IN", ta: "ta-IN", en: "en-IN" };

const CATEGORY_WORD: Record<SpendCategory, keyof Strings> = {
  travel: "catTravel",
  stay: "catStay",
  food: "catFood",
  medicine: "catMedicine",
  hospital: "catHospital",
  other: "catOther",
};

const NUDGE_WORD: Record<NudgeKind, keyof Strings> = {
  stay_costs_more: "nudgeStay",
  scheme_may_cover: "nudgeScheme",
  rail_concession: "nudgeRail",
  over_what_you_said: "nudgeOver",
};

const CATEGORIES: SpendCategory[] = ["travel", "stay", "food", "medicine", "hospital", "other"];

function rupees(paise: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang], {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(paise / 100);
}

function monthName(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(LOCALE[lang], { month: "long" }).format(new Date(`${iso}T00:00:00`));
}

/** Two bars a month: what is spent and booked, and what is still to come. Words carry the meaning. */
function Bars({ months, lang, s }: { months: MonthOutlook[]; lang: Lang; s: Strings }) {
  const totals = months.map((m) => m.spent_paise + m.booked_paise + (m.expected_paise ?? 0));
  const top = Math.max(...totals, 1);
  return (
    <div className="fx-k-bars" role="img" aria-label={months.map((m, i) => `${monthName(m.month, lang)} ${rupees(totals[i] ?? 0, lang)}`).join(", ")}>
      {months.map((m, i) => {
        const known = m.spent_paise + m.booked_paise;
        const ahead = m.expected_paise ?? 0;
        return (
          <div key={m.month} className="fx-k-bar">
            <div className="fx-k-bar-track">
              <span className="fx-k-bar-known" style={{ height: `${(known / top) * 100}%` }} />
              <span className="fx-k-bar-ahead" style={{ height: `${(ahead / top) * 100}%` }} />
            </div>
            <span className="fx-k-bar-label">{monthName(m.month, lang)}</span>
            <span className="fx-k-bar-total">
              {m.expected_paise === null && m.visits_ahead.length > 0 ? "?" : rupees(totals[i] ?? 0, lang)}
            </span>
          </div>
        );
      })}
      <div className="fx-k-legend">
        <span><i className="fx-k-dot-known" /> {s.kharchaSpent} + {s.kharchaBooked}</span>
        <span><i className="fx-k-dot-ahead" /> {s.kharchaExpected}</span>
      </div>
    </div>
  );
}

function Month({ month, title, lang, s }: { month: MonthOutlook; title: string; lang: Lang; s: Strings }) {
  const [open, setOpen] = useState(false);
  const cannotSay = month.expected_paise === null && month.visits_ahead.length > 0;
  return (
    <section className="fx-card fx-k-month">
      <h2 className="fx-h2">{title}</h2>
      <dl className="fx-k-sums">
        <div><dt>{s.kharchaSpent}</dt><dd>{rupees(month.spent_paise, lang)}</dd></div>
        <div><dt>{s.kharchaBooked}</dt><dd>{rupees(month.booked_paise, lang)}</dd></div>
        <div>
          <dt>{s.kharchaExpected}</dt>
          <dd>{cannotSay ? "—" : rupees(month.expected_paise ?? 0, lang)}</dd>
        </div>
      </dl>
      <p className="fx-k-ahead">
        {month.visits_ahead.length > 0
          ? s.kharchaVisitsAhead.replace("{n}", String(month.visits_ahead.length))
          : s.kharchaNoVisitsAhead}
      </p>
      {cannotSay && <p className="fx-k-note">{s.kharchaCannotSayYet}</p>}

      {Object.keys(month.by_category).length > 0 && (
        <ul className="fx-k-cats">
          {CATEGORIES.filter((c) => (month.by_category[c] ?? 0) > 0).map((c) => (
            <li key={c}>
              <span>{s[CATEGORY_WORD[c]]}</span>
              <span>{rupees(month.by_category[c] ?? 0, lang)}</span>
            </li>
          ))}
        </ul>
      )}

      {month.lines.some((l) => l.amount_paise !== null) && (
        <button type="button" className="fx-k-why" aria-expanded={open} onClick={() => setOpen(!open)}>
          <Info size={14} /> {s.kharchaWhy}
        </button>
      )}
      {open && (
        <ul className="fx-k-working">
          {month.lines
            .filter((l) => l.amount_paise !== null)
            .map((l) => (
              <li key={l.category}>
                <span>{s[CATEGORY_WORD[l.category]]}: {rupees(l.amount_paise ?? 0, lang)}</span>
                <span className="fx-k-basis">
                  {s.kharchaBasedOnVisits.replace("{n}", String(l.visits_used))}
                </span>
              </li>
            ))}
        </ul>
      )}
    </section>
  );
}

export function Kharcha({ patientId, lang, s }: { patientId: string; lang: Lang; s: Strings }) {
  const [data, setData] = useState<KharchaData | null>(null);
  const [text, setText] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState<SpendCategory | "">("");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [share, setShare] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    books
      .get(patientId)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(load, [load]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
      setError(null);
      load();
    } catch {
      setError(s.kharchaCouldNotRead);
    } finally {
      setBusy(false);
    }
  };

  const add = () =>
    act(async () => {
      const typed = Number(amount);
      await books.add(patientId, {
        text: text.trim() || undefined,
        amount: Number.isFinite(typed) && typed > 0 ? Math.round(typed) : undefined,
        category: category || undefined,
      });
      setText("");
      setAmount("");
      setCategory("");
    });

  const saveLimit = () =>
    act(async () => {
      const typed = Math.round(Number(limit));
      if (!Number.isFinite(typed) || typed <= 0) throw new Error("no amount");
      await books.setLimit(patientId, typed, limit);
      setLimit("");
    });

  if (!data) return error ? <div className="fx-error">{error}</div> : null;
  const [thisMonth, following] = data.months;
  const nothingYet =
    thisMonth.spent_paise + following.spent_paise + thisMonth.booked_paise + following.booked_paise === 0 &&
    data.to_confirm.length === 0;

  return (
    <div className="fx-kharcha">
      <p className="fx-k-private">
        <Shield size={14} /> {s.kharchaLimitHint}
      </p>

      {data.nudges.length > 0 && (
        <ul className="fx-k-nudges">
          {data.nudges.map((n) => (
            <li key={n.kind} className={n.kind === "over_what_you_said" ? "fx-k-nudge-over" : undefined}>
              {s[NUDGE_WORD[n.kind]].replace("{org}", n.organisation_name ?? "")}
            </li>
          ))}
        </ul>
      )}

      {data.bookable.map((b) => (
        <section key={b.item_id} className="fx-card fx-k-confirm">
          <h2 className="fx-h2">{s.kharchaReadyToBook}</h2>
          <p className="fx-k-confirm-line">
            {b.amount_paise !== null && <strong>{rupees(b.amount_paise, lang)}</strong>} · {b.provider}
          </p>
          {/* The seller's own price. Nothing is booked until this tap, and the
              driver gets only what the family agrees to share. */}
          <label className="fx-k-share">
            <input type="checkbox" checked={share} onChange={(ev) => setShare(ev.target.checked)} />
            <span>{s.kharchaShareContact}</span>
          </label>
          <div className="fx-k-actions">
            <button
              type="button"
              disabled={busy || !share}
              onClick={() => act(() => books.book(patientId, b.item_id, share))}
            >
              {s.kharchaBook}
            </button>
          </div>
        </section>
      ))}

      {data.payable.map((e) => (
        <section key={e.id} className="fx-card fx-k-confirm">
          <h2 className="fx-h2">{s.kharchaToPay}</h2>
          <p className="fx-k-confirm-line">
            <strong>{rupees(e.amount_paise, lang)}</strong> · {s[CATEGORY_WORD[e.category]]}
          </p>
          <div className="fx-k-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                act(async () => {
                  const { pay_url } = await books.pay(patientId, e.id);
                  // The vendor's own page; the family pays the vendor there.
                  if (pay_url) window.open(pay_url, "_blank", "noopener");
                })
              }
            >
              {s.kharchaPay.replace("{vendor}", e.party ?? "")}
            </button>
          </div>
        </section>
      ))}

      {data.to_confirm.map((e) => (
        <section key={e.id} className="fx-card fx-k-confirm">
          <h2 className="fx-h2">{s.kharchaIsThisRight}</h2>
          <p className="fx-k-confirm-line">
            <strong>{rupees(e.amount_paise, lang)}</strong> · {s[CATEGORY_WORD[e.category]]}
          </p>
          {e.stated_in && (
            <p className="fx-k-words">
              {s.kharchaYourWords}: “{e.stated_in}”
            </p>
          )}
          <div className="fx-k-actions">
            <button type="button" disabled={busy} onClick={() => act(() => books.confirm(patientId, e.id))}>
              {s.kharchaYes}
            </button>
            <button type="button" className="fx-k-secondary" disabled={busy} onClick={() => act(() => books.remove(patientId, e.id))}>
              {s.kharchaNo}
            </button>
          </div>
        </section>
      ))}

      {nothingYet ? (
        <p className="fx-card fx-k-note">{s.kharchaNothingYet}</p>
      ) : (
        <>
          <Bars months={[thisMonth, following]} lang={lang} s={s} />
          <Month month={thisMonth} title={s.kharchaThisMonth} lang={lang} s={s} />
          <Month month={following} title={s.kharchaNextMonth} lang={lang} s={s} />
        </>
      )}

      <section className="fx-card fx-k-add">
        <h2 className="fx-h2">{s.kharchaAdd}</h2>
        <label className="fx-k-field">
          <span>{s.kharchaAddHint}</span>
          <input value={text} onChange={(ev) => setText(ev.target.value)} maxLength={400} />
        </label>
        <div className="fx-k-row">
          <label className="fx-k-field">
            <span>{s.kharchaAmount}</span>
            <input inputMode="numeric" value={amount} onChange={(ev) => setAmount(ev.target.value.replace(/[^\d]/g, ""))} />
          </label>
          <label className="fx-k-field">
            <span>{s.kharchaKind}</span>
            <select value={category} onChange={(ev) => setCategory(ev.target.value as SpendCategory | "")}>
              <option value="">—</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {s[CATEGORY_WORD[c]]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className="fx-k-primary" disabled={busy || (!text.trim() && !amount)} onClick={add}>
          {s.kharchaSave}
        </button>
      </section>

      <section className="fx-card fx-k-add">
        <h2 className="fx-h2">{s.kharchaLimit}</h2>
        {data.limit && <p className="fx-k-limit">{rupees(data.limit.monthly_paise, lang)}</p>}
        <div className="fx-k-row">
          <label className="fx-k-field">
            <span>{s.kharchaAmount}</span>
            <input inputMode="numeric" value={limit} onChange={(ev) => setLimit(ev.target.value.replace(/[^\d]/g, ""))} />
          </label>
          <button type="button" className="fx-k-primary" disabled={busy || !limit} onClick={saveLimit}>
            {s.kharchaLimitSave}
          </button>
        </div>
      </section>

      {error && <div className="fx-error">{error}</div>}
    </div>
  );
}
