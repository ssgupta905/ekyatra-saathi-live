/**
 * The family app's own words.
 *
 * A careful boundary runs through this file, and it is the same boundary the
 * whole system is built on.
 *
 *   **Chrome is translated here.** "Plan", "Send", "Why", the name of a day —
 *   these are furniture. They are the same words on every family's screen
 *   regardless of what their plan says, they assert nothing, and a static table
 *   is the right way to hold them.
 *
 *   **Nothing the system *says* is translated here.** Every sentence about this
 *   family's plan — the message, the holding note, the answer to a question —
 *   is written by the language layer in `language/rendering.py`, checked by
 *   `language/guard.py` against the plan it came from, and arrives over the
 *   wire already in the family's language. This file never produces one.
 *
 * The one case worth naming: the big word on the verdict card (Come / Wait /
 * Not yet) is a *label for `plan.decision`*, an enum with three values, not a
 * generated sentence. Translating an enum label is chrome. The sentence
 * underneath it is the real rendered message, and if the guard held that
 * message the card says a person is calling instead of inventing a substitute.
 *
 * Scripts: Devanagari for Hindi, Bengali, Odia. Each `lang` attribute is set on
 * the app root so the browser picks the right font and line-breaking.
 */

export type Lang = "hi" | "bn" | "or" | "en";

export const LANGS: { code: Lang; label: string; endonym: string }[] = [
  { code: "hi", label: "Hindi", endonym: "हिन्दी" },
  { code: "bn", label: "Bengali", endonym: "বাংলা" },
  { code: "or", label: "Odia", endonym: "ଓଡ଼ିଆ" },
  { code: "en", label: "English", endonym: "English" },
];

export interface Strings {
  /** Three labels for the three values of `plan.decision`. */
  come: string;
  wait: string;
  notYet: string;
  travelOn: string;
  noPlanYet: string;
  /** Shown instead of a sentence when the guard held the rendered message. */
  personCalling: string;

  why: string;
  waitingFor: string;
  expectedBetween: string;
  onThisDay: string;

  plan: string;
  done: string;
  waiting: string;
  ahead: string;
  nextVisit: string;
  noTravelNeeded: string;

  messages: string;
  planTab: string;
  you: string;
  ask: string;
  askPlaceholder: string;
  send: string;
  sending: string;
  speak: string;
  /** Shown while the message is being read aloud — not while listening. */
  reading: string;
  listening: string;
  transcribing: string;
  checkBeforeSending: string;
  aPersonWillReply: string;

  language: string;
  /** Shown as a divider in the thread at the point the language changed. */
  languageChanged: string;
  journey: string;
  kmAway: string;
  hoursEachWay: string;
  working: string;
  updated: string;
}

/**
 * Keys are identical across all four tables by construction — `Strings` is
 * required, so a missing key is a compile error rather than an English word
 * appearing in the middle of a Bengali screen.
 */
export const STRINGS: Record<Lang, Strings> = {
  hi: {
    come: "आइए",
    wait: "रुकिए",
    notYet: "अभी नहीं",
    travelOn: "यात्रा",
    noPlanYet: "योजना बन रही है…",
    personCalling: "हमारी टीम आपको फ़ोन करेगी।",

    why: "क्यों",
    waitingFor: "इसका इंतज़ार है",
    expectedBetween: "संभावित",
    onThisDay: "तय है",

    plan: "आपकी योजना",
    done: "हो गया",
    waiting: "इंतज़ार",
    ahead: "आगे",
    nextVisit: "अगली बार यही",
    noTravelNeeded: "आने की ज़रूरत नहीं",

    messages: "संदेश",
    planTab: "योजना",
    you: "आप",
    ask: "पूछिए",
    askPlaceholder: "अपना सवाल लिखिए",
    send: "भेजें",
    sending: "भेज रहे हैं…",
    speak: "बोलिए",
    reading: "पढ़ रहे हैं…",
    listening: "सुन रहे हैं…",
    transcribing: "लिख रहे हैं…",
    checkBeforeSending: "भेजने से पहले देख लीजिए",
    aPersonWillReply: "कोई व्यक्ति जवाब देगा",

    language: "भाषा",
    languageChanged: "भाषा बदली गई",
    journey: "सफ़र",
    kmAway: "किलोमीटर दूर",
    hoursEachWay: "घंटे एक तरफ़",
    working: "साथी देख रहा है…",
    updated: "अपडेट",
  },
  bn: {
    come: "আসুন",
    wait: "অপেক্ষা করুন",
    notYet: "এখনও নয়",
    travelOn: "যাত্রা",
    noPlanYet: "পরিকল্পনা তৈরি হচ্ছে…",
    personCalling: "আমাদের একজন আপনাকে ফোন করবেন।",

    why: "কেন",
    waitingFor: "এর জন্য অপেক্ষা",
    expectedBetween: "সম্ভাব্য",
    onThisDay: "নিশ্চিত",

    plan: "আপনার পরিকল্পনা",
    done: "হয়ে গেছে",
    waiting: "অপেক্ষা",
    ahead: "সামনে",
    nextVisit: "এবার এটির জন্য",
    noTravelNeeded: "আসতে হবে না",

    messages: "বার্তা",
    planTab: "পরিকল্পনা",
    you: "আপনি",
    ask: "জিজ্ঞাসা করুন",
    askPlaceholder: "আপনার প্রশ্ন লিখুন",
    send: "পাঠান",
    sending: "পাঠানো হচ্ছে…",
    speak: "বলুন",
    reading: "পড়ে শোনানো হচ্ছে…",
    listening: "শুনছি…",
    transcribing: "লেখা হচ্ছে…",
    checkBeforeSending: "পাঠানোর আগে দেখে নিন",
    aPersonWillReply: "একজন উত্তর দেবেন",

    language: "ভাষা",
    languageChanged: "ভাষা পরিবর্তন করা হয়েছে",
    journey: "যাত্রাপথ",
    kmAway: "কিলোমিটার দূরে",
    hoursEachWay: "ঘণ্টা একদিকে",
    working: "সাথী দেখছে…",
    updated: "আপডেট",
  },
  or: {
    come: "ଆସନ୍ତୁ",
    wait: "ଅପେକ୍ଷା କରନ୍ତୁ",
    notYet: "ଏବେ ନୁହେଁ",
    travelOn: "ଯାତ୍ରା",
    noPlanYet: "ଯୋଜନା ପ୍ରସ୍ତୁତ ହେଉଛି…",
    personCalling: "ଆମର ଜଣେ ଆପଣଙ୍କୁ ଫୋନ୍ କରିବେ।",

    why: "କାହିଁକି",
    waitingFor: "ଏହାର ଅପେକ୍ଷା",
    expectedBetween: "ସମ୍ଭାବ୍ୟ",
    onThisDay: "ନିଶ୍ଚିତ",

    plan: "ଆପଣଙ୍କ ଯୋଜନା",
    done: "ସରିଗଲା",
    waiting: "ଅପେକ୍ଷା",
    ahead: "ଆଗକୁ",
    nextVisit: "ଏଥର ଏହା ପାଇଁ",
    noTravelNeeded: "ଆସିବା ଦରକାର ନାହିଁ",

    messages: "ସନ୍ଦେଶ",
    planTab: "ଯୋଜନା",
    you: "ଆପଣ",
    ask: "ପଚାରନ୍ତୁ",
    askPlaceholder: "ଆପଣଙ୍କ ପ୍ରଶ୍ନ ଲେଖନ୍ତୁ",
    send: "ପଠାନ୍ତୁ",
    sending: "ପଠାଯାଉଛି…",
    speak: "କୁହନ୍ତୁ",
    reading: "ପଢ଼ି ଶୁଣାଉଛି…",
    listening: "ଶୁଣୁଛି…",
    transcribing: "ଲେଖାଯାଉଛି…",
    checkBeforeSending: "ପଠାଇବା ପୂର୍ବରୁ ଦେଖିନିଅନ୍ତୁ",
    aPersonWillReply: "ଜଣେ ଉତ୍ତର ଦେବେ",

    language: "ଭାଷା",
    languageChanged: "ଭାଷା ପରିବର୍ତ୍ତନ ହୋଇଛି",
    journey: "ଯାତ୍ରାପଥ",
    kmAway: "କିଲୋମିଟର ଦୂର",
    hoursEachWay: "ଘଣ୍ଟା ଗୋଟିଏ ଦିଗକୁ",
    working: "ସାଥୀ ଦେଖୁଛି…",
    updated: "ଅପଡେଟ୍",
  },
  en: {
    come: "Come",
    wait: "Wait",
    notYet: "Not yet",
    travelOn: "Travel",
    noPlanYet: "Working out your plan…",
    personCalling: "Someone from our team will call you.",

    why: "Why",
    waitingFor: "Waiting for",
    expectedBetween: "Expected",
    onThisDay: "Confirmed",

    plan: "Your plan",
    done: "Done",
    waiting: "Waiting",
    ahead: "Ahead",
    nextVisit: "This is the visit",
    noTravelNeeded: "No travel needed",

    messages: "Messages",
    planTab: "Plan",
    you: "You",
    ask: "Ask",
    askPlaceholder: "Type your question",
    send: "Send",
    sending: "Sending…",
    speak: "Speak",
    reading: "Reading aloud…",
    listening: "Listening…",
    transcribing: "Writing it down…",
    checkBeforeSending: "Check it before sending",
    aPersonWillReply: "A person will reply",

    language: "Language",
    languageChanged: "Language changed",
    journey: "Journey",
    kmAway: "km away",
    hoursEachWay: "hours each way",
    working: "Saathi is checking…",
    updated: "Updated",
  },
};

export const t = (lang: Lang): Strings => STRINGS[lang] ?? STRINGS.en;

/**
 * A date in the family's own script. `Intl` carries the Indic calendars and
 * numerals, so this is the browser's own locale data rather than a table of
 * month names we would have to keep correct ourselves.
 */
const DATE_LOCALE: Record<Lang, string> = {
  hi: "hi-IN",
  bn: "bn-IN",
  or: "or-IN",
  en: "en-IN",
};

export function localDate(iso: string | null, lang: Lang): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(DATE_LOCALE[lang], {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(y, (m ?? 1) - 1, d ?? 1));
}

export function localDateShort(iso: string | null, lang: Lang): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(DATE_LOCALE[lang], {
    day: "numeric",
    month: "short",
  }).format(new Date(y, (m ?? 1) - 1, d ?? 1));
}

/**
 * The names of the care steps, in each language.
 *
 * These are labels for `StepKind` — a closed enum of twelve values — in the
 * vocabulary of an appointment slip. Chrome, by the same reasoning as the
 * verdict word: the same twelve words appear on every family's screen whatever
 * their plan says, and none of them asserts anything about this family.
 *
 * The backend sends the kind and an English fallback, so a kind added to the
 * pathway later shows up in English rather than disappearing.
 */
export const STEP_WORDS: Record<Lang, Record<string, string>> = {
  hi: {
    consult: "डॉक्टर से मिलना",
    biopsy: "बायोप्सी",
    bloods: "खून की जाँच",
    scan: "स्कैन",
    pet_ct: "पेट-सीटी स्कैन",
    pathology_report: "लैब रिपोर्ट",
    radiology_report: "स्कैन रिपोर्ट",
    review_consult: "डॉक्टर से दोबारा मिलना",
    joint_clinic: "संयुक्त क्लिनिक",
    treatment: "इलाज",
    maintenance_dose: "अगली दवा",
    echo_review: "दिल की जाँच और मुलाक़ात",
  },
  bn: {
    consult: "ডাক্তারের সঙ্গে দেখা",
    biopsy: "বায়োপসি",
    bloods: "রক্ত পরীক্ষা",
    scan: "স্ক্যান",
    pet_ct: "পেট-সিটি স্ক্যান",
    pathology_report: "ল্যাব রিপোর্ট",
    radiology_report: "স্ক্যান রিপোর্ট",
    review_consult: "ডাক্তারের সঙ্গে আবার দেখা",
    joint_clinic: "যৌথ ক্লিনিক",
    treatment: "চিকিৎসা",
    maintenance_dose: "পরের ডোজ",
    echo_review: "হৃদযন্ত্র পরীক্ষা ও দেখা",
  },
  or: {
    consult: "ଡାକ୍ତରଙ୍କୁ ଦେଖା",
    biopsy: "ବାୟୋପ୍ସି",
    bloods: "ରକ୍ତ ପରୀକ୍ଷା",
    scan: "ସ୍କାନ୍",
    pet_ct: "ପେଟ୍-ସିଟି ସ୍କାନ୍",
    pathology_report: "ଲ୍ୟାବ୍ ରିପୋର୍ଟ",
    radiology_report: "ସ୍କାନ୍ ରିପୋର୍ଟ",
    review_consult: "ଡାକ୍ତରଙ୍କୁ ପୁଣି ଦେଖା",
    joint_clinic: "ମିଳିତ କ୍ଲିନିକ୍",
    treatment: "ଚିକିତ୍ସା",
    maintenance_dose: "ପରବର୍ତ୍ତୀ ଡୋଜ୍",
    echo_review: "ହୃଦୟ ପରୀକ୍ଷା ଓ ଦେଖା",
  },
  en: {},
};

/** The step's name in this family's language, falling back to what the
 *  backend sent rather than to a blank. */
export const stepWord = (kind: string, fallback: string, lang: Lang): string =>
  STEP_WORDS[lang]?.[kind] ?? fallback;
