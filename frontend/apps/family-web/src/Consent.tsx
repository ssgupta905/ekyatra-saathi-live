import { useCallback, useEffect, useState } from "react";
import {
  consent as api,
  type ConsentCapacity,
  type ConsentSnapshot,
} from "@saathi/api-client";
import type { Lang } from "@saathi/i18n";
import { Shield } from "@saathi/ui-web";

/**
 * What the family has been asked to share, answered by the family.
 *
 * Until now consent existed in full on the server — purposes, capacity,
 * expiry, revocation, an access log — and the only place to answer was the
 * hospital's own console, with a navigator typing in who had said yes over
 * the phone. That works, and it is how most of India's consent actually gets
 * taken. It is also the weakest link in the chain: the record of agreement is
 * written by the party that benefits from it.
 *
 * So the family can now answer here, with their own thumb, and the grant
 * records `Channel.APP` rather than a navigator's account of a phone call.
 *
 * Three things this screen refuses to make easy.
 *
 * **Agreeing is per purpose.** There is no "accept all". Each request is its
 * own card with its own button, because the whole design of `ConsentPurpose`
 * is that agreeing to visit coordination is not agreeing to research, and a
 * single sweeping tap would quietly undo that.
 *
 * **Who is answering is asked, not assumed.** A phone in a family is handled
 * by whoever is nearest. The domain distinguishes the patient from a nominee
 * for good reason, so the screen asks rather than stamping `self` on whatever
 * thumb arrives.
 *
 * **Withdrawing is the same size as agreeing.** Consent that is easy to give
 * and buried to take back is not consent. The button sits next to the grant,
 * in the same place, at the same weight.
 */

//: Kept local rather than in `@saathi/i18n`, deliberately. That package also
//: generates the Android app's `Translations.kt`, whose generator deletes
//: hand-written entries and has broken the build once already; these strings
//: are used by this screen alone and nothing in Kotlin reads them.
type Words = {
  title: string;
  lead: string;
  waiting: string;
  inForce: string;
  nothing: string;
  wants: string;
  wouldSee: string;
  until: string;
  whoAnswers: string;
  yourName: string;
  iAmPatient: string;
  answeringFor: string;
  agree: string;
  notNow: string;
  withdraw: string;
  withdrawn: string;
  declined: string;
  never: string;
  saving: string;
};

const WORDS: Record<Lang, Words> = {
  en: {
    title: "What you share",
    lead: "You decide, one thing at a time. You can change your mind whenever you like.",
    waiting: "Waiting for your answer",
    inForce: "You have agreed to",
    nothing: "Nobody has asked you for anything.",
    wants: "wants to be told",
    wouldSee: "They would see",
    until: "until",
    whoAnswers: "Who is answering?",
    yourName: "Your name",
    iAmPatient: "I am the patient",
    answeringFor: "I am answering for them",
    agree: "Yes, I agree",
    notNow: "Not now",
    withdraw: "Withdraw",
    withdrawn: "Withdrawn",
    declined: "Left unanswered. Nobody is told anything.",
    never: "Saying no never changes your treatment.",
    saving: "Saving…",
  },
  hi: {
    title: "आप क्या साझा करते हैं",
    lead: "आप एक-एक करके तय करें। आप कभी भी अपना मन बदल सकते हैं।",
    waiting: "आपके उत्तर की प्रतीक्षा",
    inForce: "आपने अनुमति दी है",
    nothing: "किसी ने आपसे कुछ नहीं माँगा है।",
    wants: "जानना चाहते हैं",
    wouldSee: "उन्हें दिखेगा",
    until: "तक",
    whoAnswers: "कौन उत्तर दे रहा है?",
    yourName: "आपका नाम",
    iAmPatient: "मैं मरीज़ हूँ",
    answeringFor: "मैं उनकी ओर से उत्तर दे रहा/रही हूँ",
    agree: "हाँ, मैं सहमत हूँ",
    notNow: "अभी नहीं",
    withdraw: "वापस लें",
    withdrawn: "वापस ली गई",
    declined: "उत्तर नहीं दिया गया। किसी को कुछ नहीं बताया जाएगा।",
    never: "मना करने से आपके इलाज पर कोई असर नहीं पड़ेगा।",
    saving: "सहेजा जा रहा है…",
  },
  bn: {
    title: "আপনি কী ভাগ করেন",
    lead: "আপনি একটি একটি করে ঠিক করুন। যেকোনো সময় মত বদলাতে পারেন।",
    waiting: "আপনার উত্তরের অপেক্ষায়",
    inForce: "আপনি অনুমতি দিয়েছেন",
    nothing: "কেউ আপনার কাছে কিছু চায়নি।",
    wants: "জানতে চায়",
    wouldSee: "তারা দেখতে পাবে",
    until: "পর্যন্ত",
    whoAnswers: "কে উত্তর দিচ্ছেন?",
    yourName: "আপনার নাম",
    iAmPatient: "আমি রোগী",
    answeringFor: "আমি তাঁর হয়ে উত্তর দিচ্ছি",
    agree: "হ্যাঁ, আমি রাজি",
    notNow: "এখন নয়",
    withdraw: "ফিরিয়ে নিন",
    withdrawn: "ফিরিয়ে নেওয়া হয়েছে",
    declined: "উত্তর দেওয়া হয়নি। কাউকে কিছু জানানো হবে না।",
    never: "না বললে আপনার চিকিৎসায় কোনো পরিবর্তন হবে না।",
    saving: "সংরক্ষণ হচ্ছে…",
  },
  or: {
    title: "ଆପଣ କ’ଣ ଅଂଶୀଦାର କରନ୍ତି",
    lead: "ଆପଣ ଗୋଟି ଗୋଟି କରି ସ୍ଥିର କରନ୍ତୁ। ଯେକୌଣସି ସମୟରେ ମତ ବଦଳାଇ ପାରିବେ।",
    waiting: "ଆପଣଙ୍କ ଉତ୍ତରର ଅପେକ୍ଷା",
    inForce: "ଆପଣ ଅନୁମତି ଦେଇଛନ୍ତି",
    nothing: "କେହି ଆପଣଙ୍କଠାରୁ କିଛି ମାଗି ନାହାନ୍ତି।",
    wants: "ଜାଣିବାକୁ ଚାହାଁନ୍ତି",
    wouldSee: "ସେମାନେ ଦେଖିବେ",
    until: "ପର୍ଯ୍ୟନ୍ତ",
    whoAnswers: "କିଏ ଉତ୍ତର ଦେଉଛନ୍ତି?",
    yourName: "ଆପଣଙ୍କ ନାମ",
    iAmPatient: "ମୁଁ ରୋଗୀ",
    answeringFor: "ମୁଁ ତାଙ୍କ ପାଇଁ ଉତ୍ତର ଦେଉଛି",
    agree: "ହଁ, ମୁଁ ରାଜି",
    notNow: "ବର୍ତ୍ତମାନ ନୁହେଁ",
    withdraw: "ପ୍ରତ୍ୟାହାର କରନ୍ତୁ",
    withdrawn: "ପ୍ରତ୍ୟାହୃତ",
    declined: "ଉତ୍ତର ଦିଆଯାଇ ନାହିଁ। କାହାକୁ କିଛି କୁହାଯିବ ନାହିଁ।",
    never: "ନା କହିଲେ ଆପଣଙ୍କ ଚିକିତ୍ସାରେ କିଛି ବଦଳିବ ନାହିଁ।",
    saving: "ସଞ୍ଚୟ ହେଉଛି…",
  },
  ta: {
    title: "நீங்கள் பகிர்வது",
    lead: "ஒவ்வொன்றாக நீங்களே முடிவு செய்யுங்கள். எப்போது வேண்டுமானாலும் மாற்றலாம்.",
    waiting: "உங்கள் பதிலுக்காக காத்திருக்கிறது",
    inForce: "நீங்கள் ஒப்புக்கொண்டவை",
    nothing: "யாரும் உங்களிடம் எதுவும் கேட்கவில்லை.",
    wants: "தெரிந்துகொள்ள விரும்புகிறது",
    wouldSee: "அவர்கள் பார்ப்பது",
    until: "வரை",
    whoAnswers: "யார் பதிலளிக்கிறார்கள்?",
    yourName: "உங்கள் பெயர்",
    iAmPatient: "நான் தான் நோயாளி",
    answeringFor: "நான் அவர்களுக்காக பதிலளிக்கிறேன்",
    agree: "ஆம், நான் ஒப்புக்கொள்கிறேன்",
    notNow: "இப்போது வேண்டாம்",
    withdraw: "திரும்பப் பெறு",
    withdrawn: "திரும்பப் பெறப்பட்டது",
    declined: "பதில் அளிக்கப்படவில்லை. யாருக்கும் எதுவும் சொல்லப்படாது.",
    never: "வேண்டாம் என்பது உங்கள் சிகிச்சையை மாற்றாது.",
    saving: "சேமிக்கிறது…",
  },
};

/** The purposes, in words a family uses rather than the enum's. */
const PURPOSE: Record<string, Record<Lang, string>> = {
  care_coordination: {
    en: "Arranging your visits", hi: "आपकी विज़िट की व्यवस्था",
    bn: "আপনার ভিজিট সাজানো", or: "ଆପଣଙ୍କ ଭିଜିଟ୍ ବ୍ୟବସ୍ଥା", ta: "உங்கள் வருகைகளை ஏற்பாடு செய்தல்",
  },
  record_movement: {
    en: "Moving your records to another centre", hi: "आपके रिकॉर्ड दूसरे केंद्र भेजना",
    bn: "আপনার রেকর্ড অন্য কেন্দ্রে পাঠানো", or: "ଆପଣଙ୍କ ରେକର୍ଡ ଅନ୍ୟ କେନ୍ଦ୍ରକୁ ପଠାଇବା",
    ta: "உங்கள் பதிவுகளை மற்றொரு மையத்திற்கு அனுப்புதல்",
  },
  research: {
    en: "Research (optional)", hi: "शोध (वैकल्पिक)", bn: "গবেষণা (ঐচ্ছিক)",
    or: "ଗବେଷଣା (ବୈକଳ୍ପିକ)", ta: "ஆராய்ச்சி (விருப்பத்தேர்வு)",
  },
  molecular_records: {
    en: "A list of the tests you have had", hi: "आपके हुए टेस्ट की सूची",
    bn: "আপনার করা পরীক্ষার তালিকা", or: "ଆପଣ କରିଥିବା ପରୀକ୍ଷାର ତାଲିକା",
    ta: "நீங்கள் செய்த பரிசோதனைகளின் பட்டியல்",
  },
};

export function Consent({
  patientId,
  lang,
  revision,
}: {
  patientId: string;
  lang: Lang;
  revision: number;
}) {
  const w = WORDS[lang] ?? WORDS.en;
  const [snap, setSnap] = useState<ConsentSnapshot | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [capacity, setCapacity] = useState<ConsentCapacity | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // Asked rather than taken from the record. The family app does not carry
  // the patient's name — it is deliberately the least it can know — and a
  // grant signed by a patient id is a grant nobody can later stand behind.
  const [who, setWho] = useState("");
  const [passed, setPassed] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    api
      .snapshot(patientId)
      .then((s) => {
        setSnap(s);
        setUnavailable(null);
      })
      .catch(() => setUnavailable("—"));
  }, [patientId]);

  useEffect(load, [load, revision]);

  const say = async (requestId: string) => {
    setBusy(requestId);
    try {
      await api.grant(patientId, requestId, {
        granted_by: who.trim(),
        capacity: capacity ?? "self",
        // Their own thumb, in their own app. Not a navigator's note of a call.
        channel: "app",
      });
      load();
    } finally {
      setBusy(null);
    }
  };

  const take = async (grantId: string) => {
    setBusy(grantId);
    try {
      await api.revoke(patientId, grantId, { by: who.trim() || patientId });
      load();
    } finally {
      setBusy(null);
    }
  };

  if (unavailable) return null;
  if (!snap) return <p className="fx-quiet">…</p>;

  const pending = (snap.pending ?? []).filter((r) => !passed.has(r.id));
  const active = (snap.grants ?? []).filter((g) => g.active);
  // Nothing asked and nothing agreed is not worth a heading on a phone. The
  // panel appears when there is something to answer or something to take back.
  if (pending.length === 0 && active.length === 0) return null;
  const word = (purpose: string) => PURPOSE[purpose]?.[lang] ?? purpose;

  return (
    <section className="fx-consent">
      <h2 className="fx-consent-title">
        <Shield /> {w.title}
      </h2>
      <p className="fx-quiet">{w.lead}</p>

      {pending.length > 0 && <h3 className="fx-consent-head">{w.waiting}</h3>}
      {pending.map((ask) => (
        <article className="fx-ask" key={ask.id}>
          <p className="fx-ask-what">{word(ask.purpose)}</p>
          <p className="fx-quiet">
            <strong>{ask.requester}</strong> {w.wants}
          </p>
          <p className="fx-ask-cats">
            {w.wouldSee}: {(ask.categories ?? []).join(", ")}
          </p>

          <p className="fx-ask-who">{w.whoAnswers}</p>
          <div className="fx-ask-who-row">
            <button
              type="button"
              className={`fx-chip${capacity === "self" ? " on" : ""}`}
              onClick={() => setCapacity("self")}
            >
              {w.iAmPatient}
            </button>
            <button
              type="button"
              className={`fx-chip${capacity === "nominee" ? " on" : ""}`}
              onClick={() => setCapacity("nominee")}
            >
              {w.answeringFor}
            </button>
          </div>

          <label className="fx-ask-name">
            {w.yourName}
            <input value={who} onChange={(e) => setWho(e.target.value)} />
          </label>

          <div className="fx-ask-actions">
            <button
              type="button"
              className="fx-btn agree"
              disabled={!capacity || who.trim().length < 2 || busy === ask.id}
              onClick={() => say(ask.id)}
            >
              {busy === ask.id ? w.saving : w.agree}
            </button>
            <button
              type="button"
              className="fx-btn"
              onClick={() => setPassed(new Set([...passed, ask.id]))}
            >
              {w.notNow}
            </button>
          </div>
          <p className="fx-quiet fx-never">{w.never}</p>
        </article>
      ))}

      <h3 className="fx-consent-head">{w.inForce}</h3>
      {active.length === 0 && <p className="fx-quiet">{w.nothing}</p>}
      {active.map((g) => (
        <article className="fx-grant" key={g.id}>
          <div>
            <p className="fx-ask-what">{word(g.purpose)}</p>
            <p className="fx-quiet">
              {g.requester} · {w.until} {(g.expires_at ?? "").slice(0, 10) || "—"}
            </p>
          </div>
          <button
            type="button"
            className="fx-btn withdraw"
            disabled={busy === g.id}
            onClick={() => take(g.id)}
          >
            {busy === g.id ? w.saving : w.withdraw}
          </button>
        </article>
      ))}
    </section>
  );
}
