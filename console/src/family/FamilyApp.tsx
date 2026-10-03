import { useCallback, useEffect, useMemo, useState } from "react";
import { family, type FamilyHome, type Thread as ThreadData } from "../lib/api";
import { useLiveWorld } from "../lib/live";
import { LANGS, t, type Lang } from "../lib/i18n";
import { Verdict } from "./Verdict";
import { Why } from "./Why";
import { PlanStrip } from "./PlanStrip";
import { Thread } from "./Thread";
import { Composer } from "./Composer";
import { Shield, Spark } from "../ui/icons";

/**
 * The family's app. A separate application from the hospital console, not a
 * persona inside it.
 *
 * That separation is the point. The two audiences share a backend and share
 * nothing else: a navigator needs a branching pathway, thirty families, and an
 * audit trail, and a caregiver standing at a bus stand needs one word and one
 * date. Building both out of the same screen produced a screen that served
 * neither, so they are now two apps — `index.html` and `family.html` — that
 * can be opened on two different devices by two different people, as they
 * would be in a pilot.
 *
 * Everything here reacts to the same event stream the console watches. When
 * the hospital's day goes wrong, this screen changes while the family is
 * looking at it, and says so.
 */

/** Which family this phone belongs to. In a pilot this comes from the link in
 *  their SMS; here it is the query string, so two phones can be opened side by
 *  side in the recorded demo. */
function patientFromUrl(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("patient") ?? "P-SHAMBHU";
}

export default function FamilyApp() {
  const patientId = useMemo(patientFromUrl, []);
  const [home, setHome] = useState<FamilyHome | null>(null);
  const [thread, setThread] = useState<ThreadData | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const world = useLiveWorld();

  const refresh = useCallback(() => {
    Promise.all([family.home(patientId), family.thread(patientId)])
      .then(([homeData, threadData]) => {
        setHome(homeData);
        setThread(threadData);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(refresh, [refresh]);

  // The live stream is the reason this screen is not a static page. Anything
  // that touches this family — a new plan, a held message, a disruption at the
  // hospital — re-reads the one endpoint rather than patching local state, so
  // what is on screen is always a thing the backend said.
  const revision = world.revisionFor(patientId);
  useEffect(() => {
    if (revision > 0) refresh();
  }, [revision, refresh]);

  const lang = (home?.patient.language ?? "en") as Lang;
  const s = t(lang);

  const choose = async (next: Lang) => {
    if (next === lang || switching) return;
    setSwitching(true);
    try {
      await family.chooseLanguage(patientId, next);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not change language");
    } finally {
      setSwitching(false);
    }
  };

  // Only this family's work. A phone showing "Saathi is checking" because
  // something is happening for a stranger in another district would be a lie
  // about whose problem is being worked on.
  const mine = world.working.filter(
    (item) => item.patientId === null || item.patientId === patientId,
  );

  return (
    <div className="fx-app" lang={lang}>
      <header className="fx-top">
        <div className="fx-id">
          <span className="fx-brand">Saathi</span>
          {home && <span className="fx-place">{home.patient.district}</span>}
        </div>

        <div className="fx-langs" role="group" aria-label={s.language}>
          {LANGS.map((option) => (
            <button
              key={option.code}
              type="button"
              aria-pressed={option.code === lang}
              disabled={switching}
              onClick={() => choose(option.code)}
              title={option.label}
            >
              {option.endonym}
            </button>
          ))}
        </div>
      </header>

      {(mine.length > 0 || switching) && (
        <div className="fx-working">
          <Spark size={13} />
          <span>{switching ? s.working : (mine[0]?.task ?? s.working)}</span>
        </div>
      )}

      <main className="fx-scroll">
        {error && <div className="fx-error">{error}</div>}

        <Verdict home={home} lang={lang} s={s} />
        <Why waits={home?.waiting_for ?? []} lang={lang} s={s} />
        <PlanStrip steps={home?.steps ?? []} lang={lang} s={s} />
        <Thread entries={thread?.thread ?? []} lang={lang} s={s} />

        {home && (
          <p className="fx-journey">
            {home.patient.distance_km} {s.kmAway}
            {home.patient.hours_each_way != null && (
              <> · {home.patient.hours_each_way.toFixed(0)} {s.hoursEachWay}</>
            )}
          </p>
        )}

        <p className="fx-boundary">
          <Shield size={12} />
          {lang === "en"
            ? "Travel and appointments only. Saathi never discusses results."
            : s.aPersonWillReply}
        </p>
      </main>

      <Composer patientId={patientId} lang={lang} s={s} onSent={refresh} />
    </div>
  );
}
