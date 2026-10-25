import { useCallback, useEffect, useMemo, useState } from "react";
import { family, type FamilyHome, type Thread as ThreadData, useLiveWorld } from "@saathi/api-client";
import { useSession } from "@saathi/auth";
import { LANGS, t, type Lang } from "@saathi/i18n";
import { Verdict } from "./Verdict";
import { Why } from "./Why";
import { PlanStrip } from "./PlanStrip";
import { Thread } from "./Thread";
import { Composer } from "./Composer";
import { Inbox, Pin, Shield, Spark } from "@saathi/ui-web";

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
function patientFromUrl(allowed: string[] | null): string {
  const asked = new URLSearchParams(window.location.search).get("patient");
  // Signed in, a family sees only its own: the link may name one of them, and
  // anything else falls back to the first. Not signed in (the demo), the link decides.
  if (allowed) return asked && allowed.includes(asked) ? asked : (allowed[0] ?? "");
  return asked ?? "P-SHAMBHU";
}

export default function FamilyApp() {
  const { principal, signOut } = useSession();
  const allowed = principal?.patient_ids ?? null;
  const patientId = useMemo(() => patientFromUrl(allowed), [allowed]);
  const [home, setHome] = useState<FamilyHome | null>(null);
  const [thread, setThread] = useState<ThreadData | null>(null);
  const [switching, setSwitching] = useState(false);
  // Two tabs, because a phone screen holds one thing at a time. The plan and
  // the conversation were stacked, which put the conversation permanently below
  // the fold — a family could not find the messages they were sent without
  // scrolling past their whole care pathway.
  const [tab, setTab] = useState<"plan" | "messages">("plan");
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
  const messageCount = thread?.thread.length ?? 0;

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
          {principal && (
            <button type="button" className="fx-signout" onClick={signOut}>
              Sign out
            </button>
          )}
        </div>
      </header>

      {(mine.length > 0 || switching) && (
        <div className="fx-working">
          <Spark size={13} />
          <span>{switching ? s.working : (mine[0]?.task ?? s.working)}</span>
        </div>
      )}

      {/* The answer stays put. Whichever tab is open, the family can always
          see whether to travel without going looking for it. */}
      <Verdict home={home} lang={lang} s={s} />

      <nav className="fx-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "plan"}
          onClick={() => setTab("plan")}
        >
          <Pin size={14} />
          {s.planTab}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "messages"}
          onClick={() => setTab("messages")}
        >
          <Inbox size={14} />
          {s.messages}
          {messageCount > 0 && <span className="fx-tab-count">{messageCount}</span>}
        </button>
      </nav>

      <main className="fx-scroll">
        {error && <div className="fx-error">{error}</div>}

        {tab === "plan" ? (
          <>
            <Why waits={home?.waiting_for ?? []} lang={lang} s={s} />
            <PlanStrip steps={home?.steps ?? []} lang={lang} s={s} />

            {home && (
              <p className="fx-journey">
                {home.patient.distance_km} {s.kmAway}
                {home.patient.hours_each_way != null && (
                  <> · {home.patient.hours_each_way.toFixed(0)} {s.hoursEachWay}</>
                )}
              </p>
            )}
          </>
        ) : (
          <Thread entries={thread?.thread ?? []} lang={lang} s={s} />
        )}

        <p className="fx-boundary">
          <Shield size={12} />
          {lang === "en"
            ? "Travel and appointments only. Saathi never discusses results."
            : s.aPersonWillReply}
        </p>
      </main>

      <Composer
        patientId={patientId}
        lang={lang}
        s={s}
        onSent={() => {
          // Jump to the conversation: the answer arrives there, and leaving the
          // family on the plan tab would look like nothing happened.
          setTab("messages");
          refresh();
        }}
      />
    </div>
  );
}
