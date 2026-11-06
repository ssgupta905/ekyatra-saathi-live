import type { FamilyAction, GuideStage, JourneyGuide, StageKind } from "@saathi/api-client";
import { localDate, localDateShort, type Lang, type Strings } from "@saathi/i18n";
import { CheckCircle, Clock, Doc, Pin, Question } from "@saathi/ui-web";

/**
 * The whole journey, from the first test to the doctor, in the order it happens.
 *
 * Two things, in this order: what the family should do now (often "nothing, we
 * are on it", which is itself the answer), then the chain behind and ahead of
 * them. Each link says who has it. A date appears only on the visit and only when
 * the hospital has promised one, and a link that has gone wrong says so in words
 * and never by colour alone.
 */

const LABEL = (kind: StageKind, s: Strings): string =>
  ({
    tests: s.stageTests,
    reports: s.stageReports,
    insurance: s.stageInsurance,
    pharmacy: s.stagePharmacy,
    appointment: s.stageAppointment,
    doctor: s.stageDoctor,
    ride: s.stageRide,
    stay: s.stageStay,
    bed: s.stageBed,
    documents: s.stageDocuments,
    visit: s.stageVisit,
    next_session: s.stageNextSession,
  })[kind];

const ACTION = (action: FamilyAction, s: Strings): string | null =>
  ({
    nothing_yet: s.actionNothingYet,
    wait_for_team: s.actionWaitForTeam,
    keep_documents_ready: s.actionKeepDocuments,
    be_ready_for_pickup: s.actionPickup,
    go_to_first_stop: s.actionFirstStop,
    none: null,
  })[action];

const STATE_WORD = (stage: GuideStage, s: Strings): string =>
  stage.state === "done"
    ? s.stateDone
    : stage.state === "problem"
      ? s.stateProblem
      : stage.is_now
        ? s.stateNow
        : stage.state === "waiting"
          ? s.stateWaiting
          : s.stateNext;

const ICON = (stage: GuideStage) =>
  stage.state === "done" ? (
    <CheckCircle size={15} />
  ) : stage.state === "problem" ? (
    <Question size={15} />
  ) : stage.state === "waiting" ? (
    <Clock size={15} />
  ) : stage.kind === "visit" ? (
    <Pin size={15} />
  ) : (
    <Doc size={15} />
  );

export function Journey({ guide, lang, s }: { guide: JourneyGuide | null | undefined; lang: Lang; s: Strings }) {
  if (!guide || guide.stages.length === 0) {
    return (
      <section className="fx-card">
        <p className="fx-empty">{s.noJourney}</p>
      </section>
    );
  }
  const now = guide.stages.find((st) => st.id === guide.now_stage_id) ?? null;
  const percent = Math.round((guide.done / Math.max(guide.total, 1)) * 100);
  const progress = s.progress.replace("{done}", String(guide.done)).replace("{total}", String(guide.total));

  return (
    <>
      {now && (
        <section className={`fx-card fx-now ${now.state}`} aria-labelledby="fx-now-h">
          <h2 className="fx-h2" id="fx-now-h">
            {s.doNow}
          </h2>
          <p className="fx-now-what">
            <span className="fx-step-dot" aria-hidden>{ICON(now)}</span>
            <strong>{LABEL(now.kind, s)}</strong>
            <span className={`fx-pill ${now.state}`}>{STATE_WORD(now, s)}</span>
          </p>
          {ACTION(now.action, s) && <p className="fx-now-action">{ACTION(now.action, s)}</p>}
          {now.party && <p className="fx-now-party">{now.party}{now.detail ? ` · ${now.detail}` : ""}</p>}
          {now.window && (
            <p className="fx-now-party">
              {s.expectedBetween} {localDateShort(now.window[0], lang)} – {localDateShort(now.window[1], lang)}
            </p>
          )}
        </section>
      )}

      <section className="fx-card">
        <h2 className="fx-h2">{s.journey}</h2>
        <div
          className="fx-progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={guide.total}
          aria-valuenow={guide.done}
          aria-label={progress}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
        <p className="fx-progress-text">{progress}</p>

        <ol className="fx-steps fx-chain">
          {guide.stages.map((stage, i) => {
            const state = stage.state === "upcoming" ? "ahead" : stage.state;
            const action = stage.is_now ? null : ACTION(stage.action, s);
            return (
              <li
                key={stage.id}
                className={`${state}${stage.is_now ? " next" : ""}`}
                aria-current={stage.is_now ? "step" : undefined}
              >
                <span className="fx-step-rail">
                  <span className="fx-step-dot">{ICON(stage)}</span>
                </span>
                <span className="fx-step-body">
                  <span className="fx-step-what">
                    {i + 1}. {LABEL(stage.kind, s)}
                  </span>
                  <span className="fx-step-meta">
                    {stage.on ? localDate(stage.on, lang) : null}
                    <span className="fx-step-state">{STATE_WORD(stage, s)}</span>
                    {stage.party && <span className="fx-step-tag">{stage.party}</span>}
                  </span>
                  {stage.state === "problem" && action && <span className="fx-step-note">{action}</span>}
                  {stage.kind === "visit" && stage.first_stop && (
                    <span className="fx-step-note">
                      {s.firstStop}: {stage.first_stop}
                    </span>
                  )}
                  {stage.kind === "documents" && stage.bring.length > 0 && (
                    <span className="fx-step-note">{stage.bring.join(" · ")}</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </section>
    </>
  );
}
