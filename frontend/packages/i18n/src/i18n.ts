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
  /** The phone's first tab. */
  todayTab: string;
  bring: string;
  firstStop: string;
  tapForWhy: string;
  /** A ticked item on the what-to-bring list. */
  packed: string;

  /** The journey: every party between the first test and the doctor, in order. */
  journeyTab: string;
  doNow: string;
  progress: string; // "{done} of {total} steps done"
  noJourney: string;
  stageTests: string;
  stageReports: string;
  stageInsurance: string;
  stagePharmacy: string;
  stageAppointment: string;
  stageDoctor: string;
  stageBed: string;
  stageRide: string;
  stageStay: string;
  stageDocuments: string;
  stageVisit: string;
  stageNextSession: string;
  stateDone: string;
  stateNow: string;
  stateWaiting: string;
  stateProblem: string;
  stateNext: string;
  actionNothingYet: string;
  actionWaitForTeam: string;
  actionKeepDocuments: string;
  actionPickup: string;
  actionFirstStop: string;
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
    todayTab: "आज",
    bring: "साथ क्या लाएँ",
    firstStop: "सबसे पहले यहाँ जाएँ",
    tapForWhy: "क्यों? देखने के लिए छुएँ",
    packed: "रख लिया",
    journeyTab: "सफ़र",
    doNow: "अभी क्या करना है",
    progress: "{total} में से {done} कदम पूरे",
    noJourney: "आपका कदम-दर-कदम सफ़र यहाँ दिखेगा।",
    stageTests: "जाँच",
    stageReports: "रिपोर्ट",
    stageInsurance: "योजना की मंज़ूरी",
    stagePharmacy: "फार्मेसी",
    stageAppointment: "समय तय होना",
    stageDoctor: "डॉक्टर का उपलब्ध होना",
    stageBed: "बिस्तर",
    stageRide: "गाड़ी",
    stageStay: "ठहरने की जगह",
    stageDocuments: "कागज़ात",
    stageVisit: "डॉक्टर से मिलना",
    stageNextSession: "अगली बार",
    stateDone: "पूरा",
    stateNow: "अभी",
    stateWaiting: "जारी है",
    stateProblem: "दिक्कत",
    stateNext: "आगे",
    actionNothingYet: "हम इस पर काम कर रहे हैं। आपको कुछ करने की ज़रूरत नहीं है।",
    actionWaitForTeam: "दिक्कत आई है। हमारी टीम दूसरा रास्ता निकाल रही है। अभी यात्रा न करें।",
    actionKeepDocuments: "अपने कागज़ात तैयार रखें।",
    actionPickup: "गाड़ी तय हो गई है। लेने के समय तैयार रहें।",
    actionFirstStop: "आपकी मुलाक़ात पक्की हो गई है।",
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
    todayTab: "আজ",
    bring: "সঙ্গে কী আনবেন",
    firstStop: "প্রথমে এখানে যান",
    tapForWhy: "কেন? দেখতে ছুঁয়ে দিন",
    packed: "নেওয়া হয়েছে",
    journeyTab: "যাত্রা",
    doNow: "এখন কী করতে হবে",
    progress: "{total}টির মধ্যে {done}টি ধাপ সম্পূর্ণ",
    noJourney: "আপনার ধাপে ধাপে যাত্রা এখানে দেখা যাবে।",
    stageTests: "পরীক্ষা",
    stageReports: "রিপোর্ট",
    stageInsurance: "প্রকল্পের অনুমোদন",
    stagePharmacy: "ফার্মেসি",
    stageAppointment: "সময় ঠিক হওয়া",
    stageDoctor: "ডাক্তার উপস্থিত থাকা",
    stageBed: "বিছানা",
    stageRide: "গাড়ি",
    stageStay: "থাকার জায়গা",
    stageDocuments: "কাগজপত্র",
    stageVisit: "ডাক্তারের সঙ্গে দেখা",
    stageNextSession: "পরের বার",
    stateDone: "সম্পূর্ণ",
    stateNow: "এখন",
    stateWaiting: "চলছে",
    stateProblem: "সমস্যা",
    stateNext: "সামনে",
    actionNothingYet: "আমরা এটা নিয়ে কাজ করছি। আপনাকে কিছু করতে হবে না।",
    actionWaitForTeam: "সমস্যা হয়েছে। আমাদের দল অন্য উপায় ঠিক করছে। এখনই যাত্রা করবেন না।",
    actionKeepDocuments: "আপনার কাগজপত্র তৈরি রাখুন।",
    actionPickup: "গাড়ি ঠিক হয়েছে। নেওয়ার সময় তৈরি থাকুন।",
    actionFirstStop: "আপনার দেখা পাকা হয়েছে।",
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
    todayTab: "ଆଜି",
    bring: "ସାଙ୍ଗରେ କଣ ଆଣିବେ",
    firstStop: "ପ୍ରଥମେ ଏଠାକୁ ଯାଆନ୍ତୁ",
    tapForWhy: "କାହିଁକି? ଦେଖିବାକୁ ଛୁଅନ୍ତୁ",
    packed: "ନିଆଗଲା",
    journeyTab: "ଯାତ୍ରା",
    doNow: "ଏବେ କ'ଣ କରିବେ",
    progress: "{total}ଟିରୁ {done}ଟି ପଦକ୍ଷେପ ସମ୍ପୂର୍ଣ୍ଣ",
    noJourney: "ଆପଣଙ୍କ ପଦକ୍ଷେପ-ପଦକ୍ଷେପ ଯାତ୍ରା ଏଠାରେ ଦେଖାଯିବ।",
    stageTests: "ପରୀକ୍ଷା",
    stageReports: "ରିପୋର୍ଟ",
    stageInsurance: "ଯୋଜନା ଅନୁମୋଦନ",
    stagePharmacy: "ଫାର୍ମାସୀ",
    stageAppointment: "ସମୟ ଠିକ୍ ହେବା",
    stageDoctor: "ଡାକ୍ତର ଉପଲବ୍ଧ ହେବା",
    stageBed: "ଶଯ୍ୟା",
    stageRide: "ଗାଡ଼ି",
    stageStay: "ରହିବା ସ୍ଥାନ",
    stageDocuments: "କାଗଜପତ୍ର",
    stageVisit: "ଡାକ୍ତରଙ୍କ ସହ ଭେଟ",
    stageNextSession: "ପରବର୍ତ୍ତୀ ଥର",
    stateDone: "ସମ୍ପୂର୍ଣ୍ଣ",
    stateNow: "ଏବେ",
    stateWaiting: "ଚାଲିଛି",
    stateProblem: "ଅସୁବିଧା",
    stateNext: "ଆଗକୁ",
    actionNothingYet: "ଆମେ ଏହା ଉପରେ କାମ କରୁଛୁ। ଆପଣଙ୍କୁ କିଛି କରିବାକୁ ପଡ଼ିବ ନାହିଁ।",
    actionWaitForTeam: "ଅସୁବିଧା ହୋଇଛି। ଆମ ଦଳ ଅନ୍ୟ ଉପାୟ ଠିକ୍ କରୁଛି। ଏବେ ଯାତ୍ରା କରନ୍ତୁ ନାହିଁ।",
    actionKeepDocuments: "ଆପଣଙ୍କ କାଗଜପତ୍ର ପ୍ରସ୍ତୁତ ରଖନ୍ତୁ।",
    actionPickup: "ଗାଡ଼ି ଠିକ୍ ହୋଇଛି। ନେବା ସମୟରେ ପ୍ରସ୍ତୁତ ରୁହନ୍ତୁ।",
    actionFirstStop: "ଆପଣଙ୍କ ଭେଟ ପକ୍କା ହୋଇଛି।",
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
    todayTab: "Today",
    bring: "What to bring",
    firstStop: "Go first to",
    tapForWhy: "Why? Tap to see",
    packed: "packed",
    journeyTab: "Journey",
    doNow: "Do this now",
    progress: "{done} of {total} steps done",
    noJourney: "Your step-by-step journey will appear here.",
    stageTests: "Tests",
    stageReports: "Reports",
    stageInsurance: "Scheme approval",
    stagePharmacy: "Pharmacy",
    stageAppointment: "Appointment confirmed",
    stageDoctor: "Doctor available",
    stageBed: "Bed",
    stageRide: "Ride",
    stageStay: "Place to stay",
    stageDocuments: "Papers",
    stageVisit: "Doctor visit",
    stageNextSession: "Next session",
    stateDone: "Done",
    stateNow: "Now",
    stateWaiting: "In progress",
    stateProblem: "Problem",
    stateNext: "Next",
    actionNothingYet: "We are working on this. You do not need to do anything.",
    actionWaitForTeam: "There is a problem. Our team is arranging another way. Please do not travel yet.",
    actionKeepDocuments: "Please keep your papers ready.",
    actionPickup: "Your ride is arranged. Be ready at pickup time.",
    actionFirstStop: "Your visit is confirmed.",
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
    dialysis_session: "डायलिसिस",
    nephrology_review: "गुर्दे के डॉक्टर से मिलना",
    discharge_review: "अस्पताल से लौटने के बाद जाँच",
    wound_check: "पट्टी की जाँच",
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
    dialysis_session: "ডায়ালিসিস",
    nephrology_review: "কিডনির ডাক্তারের সঙ্গে দেখা",
    discharge_review: "হাসপাতাল থেকে ফেরার পর পরীক্ষা",
    wound_check: "ব্যান্ডেজ পরীক্ষা",
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
    dialysis_session: "ଡାୟଲିସିସ୍",
    nephrology_review: "ବୃକକ୍ ଡାକ୍ତରଙ୍କୁ ଦେଖା",
    discharge_review: "ଡାକ୍ତରଖାନା ପରେ ଯାଞ୍ଚ",
    wound_check: "ପଟି ଯାଞ୍ଚ",
  },
  en: {},
};

/** The step's name in this family's language, falling back to what the
 *  backend sent rather than to a blank. */
export const stepWord = (kind: string, fallback: string, lang: Lang): string =>
  STEP_WORDS[lang]?.[kind] ?? fallback;
