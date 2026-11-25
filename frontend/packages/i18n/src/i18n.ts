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

export type Lang = "hi" | "bn" | "or" | "ta" | "en";

export const LANGS: { code: Lang; label: string; endonym: string }[] = [
  { code: "hi", label: "Hindi", endonym: "हिन्दी" },
  { code: "bn", label: "Bengali", endonym: "বাংলা" },
  { code: "or", label: "Odia", endonym: "ଓଡ଼ିଆ" },
  { code: "ta", label: "Tamil", endonym: "தமிழ்" },
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

  /** What the family can manage. Asked, never assumed — the planner can work
   *  out that a journey needs a ride, and cannot work out whether this
   *  household can pay for the one it picked. No string here is an amount. */
  budgetTitle: string;
  budgetWhy: string;
  budgetTravel: string;
  budgetStay: string;
  budgetMedicine: string;
  budgetChoose: string;
  budgetCannotManage: string;
  budgetSuggested: string;
  // Kharcha: a family's own spends. Machine-drafted; for native-speaker review.
  kharchaTab: string;
  kharchaThisMonth: string;
  kharchaNextMonth: string;
  kharchaSpent: string;
  kharchaBooked: string;
  kharchaExpected: string;
  kharchaCannotSayYet: string;
  kharchaBasedOnVisits: string;
  kharchaVisitsAhead: string;
  kharchaNoVisitsAhead: string;
  kharchaAdd: string;
  kharchaAddHint: string;
  kharchaAmount: string;
  kharchaKind: string;
  kharchaSave: string;
  kharchaIsThisRight: string;
  kharchaYes: string;
  kharchaNo: string;
  kharchaLimit: string;
  kharchaLimitHint: string;
  kharchaLimitSave: string;
  kharchaNothingYet: string;
  kharchaWhy: string;
  kharchaYourWords: string;
  kharchaCouldNotRead: string;
  kharchaReadyToBook: string;
  kharchaBook: string;
  kharchaShareContact: string;
  kharchaToPay: string;
  kharchaPay: string;
  openInApp: string;
  openApp: string;
  handoffWhere: string;
  handoffCopied: string;
  routeTitle: string;
  routeFar: string;
  routeNear: string;
  routeNote: string;
  modeTransit: string;
  modeDrive: string;
  modeWalk: string;
  wayShow: string;
  wayFrom: string;
  wayBest: string;
  wayBoard: string;
  wayOff: string;
  wayTowards: string;
  wayWalk: string;
  wayStops: string;
  wayNoChange: string;
  wayChanges: string;
  wayCostNone: string;
  wayFareService: string;
  wayFareQuote: string;
  wayLeaveBy: string;
  wayDemo: string;
  wayCantLoad: string;
  tagCheapest: string;
  tagFastest: string;
  tagFewest: string;
  tagLeastWalk: string;
  reasonFits: string;
  reasonSomeOver: string;
  reasonAllOver: string;
  wayOver: string;
  modeBus: string;
  modeMetro: string;
  modeTrain: string;
  modeTaxi: string;
  modeStep: string;
  wayNoLimit: string;
  nearTitle: string;
  nearMedicine: string;
  nearTests: string;
  nearEquipment: string;
  nearClinic: string;
  nearHospital: string;
  nearHome: string;
  nearCall: string;
  nearDirections: string;
  nearOpenThen: string;
  nearShutThen: string;
  nearHoursUnknown: string;
  nearRoundClock: string;
  nearGovPrice: string;
  nearConfirm: string;
  nearRough: string;
  nearPowered: string;
  nearDemo: string;
  nearCantLoad: string;
  nearNone: string;
  nearOsm: string;
  mapOpen: string;
  mapAllow: string;
  mapWalk: string;
  mapCar: string;
  mapNavigate: string;
  mapRoute: string;
  mapClose: string;
  mapNoRoute: string;
  mapPick: string;
  mapHospital: string;
  mapYou: string;
  catTravel: string;
  catStay: string;
  catFood: string;
  catMedicine: string;
  catHospital: string;
  catOther: string;
  nudgeStay: string;
  nudgeScheme: string;
  nudgeRail: string;
  nudgeOver: string;
  budgetSent: string;
  /** The three kinds of thing on offer, as words rather than prices. */
  tierSubsidised: string;
  tierModest: string;
  tierStandard: string;

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
    budgetTitle: "खर्च के बारे में",
    budgetWhy: "हम पूछ रहे हैं ताकि आपके लिए ऐसा कुछ तय न हो जो आप वहन न कर सकें।",
    budgetTravel: "आना-जाना",
    budgetStay: "ठहरने की जगह",
    budgetMedicine: "दवाई",
    budgetChoose: "एक चुनें",
    budgetCannotManage: "इनमें से कोई भी मैं नहीं कर पाऊँगा",
    budgetSuggested: "आपके लिए सुझाव",
    kharchaTab: "खर्चा",
    kharchaThisMonth: "इस महीने",
    kharchaNextMonth: "अगले महीने",
    kharchaSpent: "खर्च हुआ",
    kharchaBooked: "बुक हुआ",
    kharchaExpected: "आगे होगा",
    kharchaCannotSayYet: "अभी नहीं बता सकते: पिछली यात्राओं का कोई खर्च दर्ज नहीं है।",
    kharchaBasedOnVisits: "आपकी पिछली {n} यात्राओं के हिसाब से",
    kharchaVisitsAhead: "आगे {n} यात्राएँ",
    kharchaNoVisitsAhead: "आगे कोई यात्रा नहीं",
    kharchaAdd: "खर्च जोड़ें",
    kharchaAddHint: "बोलिए या लिखिए, जैसे “ऑटो 450”",
    kharchaAmount: "रकम (₹)",
    kharchaKind: "किस पर",
    kharchaSave: "जोड़ें",
    kharchaIsThisRight: "क्या यह सही है?",
    kharchaYes: "हाँ, सही है",
    kharchaNo: "नहीं, हटाइए",
    kharchaLimit: "आप महीने में कितना कर सकते हैं",
    kharchaLimitHint: "यह सिर्फ़ आप देखते हैं। अगर किसी महीने ज़्यादा लगे, तो मदद के लिए कोई फ़ोन करेगा।",
    kharchaLimitSave: "सहेजें",
    kharchaNothingYet: "अभी कुछ दर्ज नहीं है। यात्रा का खर्च जोड़िए, तो अगली का हिसाब लग जाएगा।",
    kharchaWhy: "यह रकम क्यों",
    kharchaYourWords: "आपके शब्दों में",
    kharchaCouldNotRead: "रकम पढ़ी नहीं जा सकी। कृपया लिखिए।",
    kharchaReadyToBook: "बुक करने के लिए तैयार",
    kharchaBook: "यह गाड़ी बुक करें",
    kharchaShareContact: "मेरा पहला नाम और फ़ोन ड्राइवर को दें",
    kharchaToPay: "भुगतान करना है",
    kharchaPay: "{vendor} को भुगतान करें",
    openInApp: "ऐप में खोलें",
    openApp: "{app} खोलें",
    handoffWhere: "अस्पताल का पता",
    handoffCopied: "किसी ऐप पर दबाने से यह पता कॉपी हो जाता है। ऐप जहाँ पूछे कि कहाँ जाना है, वहाँ इसे चिपका दें।",
    routeTitle: "रास्ता चुनें",
    routeFar: "घर से {city} तक",
    routeNear: "अभी की जगह से अस्पताल तक",
    routeNote: "नक्शे में खुलेगा। हर साधन का समय और रास्ता वहाँ दिखेगा।",
    modeTransit: "ट्रेन / बस",
    modeDrive: "टैक्सी / कार",
    modeWalk: "पैदल",
    wayShow: "रास्ते दिखाएँ",
    wayFrom: "आप कहाँ से चल रहे हैं? (स्टेशन या जगह)",
    wayBest: "आपके लिए सुझाया",
    wayBoard: "चढ़ें",
    wayOff: "उतरें",
    wayTowards: "की ओर",
    wayWalk: "{n} मिनट पैदल",
    wayStops: "{n} स्टॉप",
    wayNoChange: "कोई बदलाव नहीं",
    wayChanges: "{n} बार बदलना",
    wayCostNone: "खर्च पता नहीं",
    wayFareService: "सेवा का किराया",
    wayFareQuote: "विक्रेता का बताया दाम",
    wayLeaveBy: "{t} तक निकलें",
    wayDemo: "नमूना समय-सारणी — असली नहीं",
    wayCantLoad: "रास्ते अभी नहीं मिल सके। नक्शे में खोलें।",
    tagCheapest: "सबसे सस्ता",
    tagFastest: "सबसे तेज़",
    tagFewest: "सबसे कम बदलाव",
    tagLeastWalk: "सबसे कम पैदल",
    reasonFits: "आपके बताए खर्च में बैठता है",
    reasonSomeOver: "जो रास्ते आपके बताए खर्च से ज़्यादा हैं, उन्हें हटा दिया गया है",
    reasonAllOver: "सभी रास्ते आपके बताए खर्च से ऊपर हैं; यह सबसे कम है",
    wayOver: "आपकी सीमा से ऊपर",
    modeBus: "बस",
    modeMetro: "मेट्रो",
    modeTrain: "ट्रेन",
    modeTaxi: "टैक्सी",
    modeStep: "पैदल",
    wayNoLimit: "आप महीने में कितना संभाल सकते हैं, खर्चा टैब में बताएँ — तब हम खर्च के हिसाब से चुनेंगे",
    nearTitle: "आसपास क्या मिलेगा",
    nearMedicine: "दवाइयाँ",
    nearTests: "जाँच",
    nearEquipment: "उपकरण",
    nearClinic: "क्लिनिक",
    nearHospital: "अस्पताल के पास",
    nearHome: "घर के पास",
    nearCall: "फ़ोन करें",
    nearDirections: "रास्ता",
    nearOpenThen: "अभी खुला है",
    nearShutThen: "अभी बंद है",
    nearHoursUnknown: "समय पता नहीं",
    nearRoundClock: "24 घंटे खुला",
    nearGovPrice: "सरकारी दाम पर जेनेरिक दवाइयाँ",
    nearConfirm: "फ़ोन करके पूछ लें कि चीज़ मिलेगी — हम नहीं जानते कि दुकान में क्या है",
    nearRough: "दूरी सीधी रेखा में है; असली रास्ता नक्शे में दिखेगा",
    nearPowered: "जगहें Google से",
    nearDemo: "नमूना जगह — असली नहीं",
    nearCantLoad: "आसपास की जगहें अभी नहीं मिल सकीं",
    nearNone: "पास में कुछ नहीं मिला",
    nearOsm: "© OpenStreetMap contributors",
    mapOpen: "नक्शे में देखें",
    mapAllow: "अपनी जगह देखने के लिए लोकेशन की अनुमति दें",
    mapWalk: "पैदल",
    mapCar: "गाड़ी",
    mapNavigate: "Maps में रास्ता शुरू करें",
    mapRoute: "{d} · {t} मिनट",
    mapClose: "बंद करें",
    mapNoRoute: "इस समय रास्ता नहीं मिला",
    mapPick: "नक्शे पर किसी जगह को छूएँ",
    mapHospital: "अस्पताल",
    mapYou: "आप",
    catTravel: "आना-जाना",
    catStay: "ठहरना",
    catFood: "खाना",
    catMedicine: "दवाई",
    catHospital: "अस्पताल",
    catOther: "और कुछ",
    nudgeStay: "रुकने का खर्च आने-जाने से ज़्यादा है। {org} अस्पताल के पास है और सस्ता है।",
    nudgeScheme: "योजना कार्ड से अस्पताल और दवा का खर्च कवर हो सकता है। हेल्प डेस्क पर पूछिए।",
    nudgeRail: "कैंसर मरीज़ों के लिए रेल किराए में छूट के बारे में स्टेशन पर पूछिए। अस्पताल का प्रमाणपत्र चाहिए होगा।",
    nudgeOver: "इस महीने का खर्च आपकी बताई सीमा से ज़्यादा लग रहा है। अस्पताल से कोई मदद के लिए फ़ोन करेगा।",
    budgetSent: "धन्यवाद। कोई व्यक्ति इसकी पुष्टि करेगा।",
    tierSubsidised: "रियायती",
    tierModest: "कम खर्च",
    tierStandard: "सामान्य दर",
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
    budgetTitle: "খরচের বিষয়ে",
    budgetWhy: "আমরা জিজ্ঞাসা করছি যাতে এমন কিছু ঠিক না হয় যা আপনি বহন করতে পারবেন না।",
    budgetTravel: "যাতায়াত",
    budgetStay: "থাকার জায়গা",
    budgetMedicine: "ওষুধ",
    budgetChoose: "একটি বেছে নিন",
    budgetCannotManage: "এর কোনোটিই আমি পারব না",
    budgetSuggested: "আপনার জন্য প্রস্তাব",
    kharchaTab: "খরচ",
    kharchaThisMonth: "এই মাসে",
    kharchaNextMonth: "পরের মাসে",
    kharchaSpent: "খরচ হয়েছে",
    kharchaBooked: "বুক হয়েছে",
    kharchaExpected: "আরও হবে",
    kharchaCannotSayYet: "এখনও বলা যাচ্ছে না: আগের কোনো যাত্রার খরচ লেখা নেই।",
    kharchaBasedOnVisits: "আপনার শেষ {n}টি যাত্রার হিসেবে",
    kharchaVisitsAhead: "সামনে {n}টি যাত্রা",
    kharchaNoVisitsAhead: "সামনে কোনো যাত্রা নেই",
    kharchaAdd: "খরচ যোগ করুন",
    kharchaAddHint: "বলুন বা লিখুন, যেমন “অটো 450”",
    kharchaAmount: "টাকা (₹)",
    kharchaKind: "কীসের জন্য",
    kharchaSave: "যোগ করুন",
    kharchaIsThisRight: "এটা কি ঠিক?",
    kharchaYes: "হ্যাঁ, ঠিক",
    kharchaNo: "না, মুছে দিন",
    kharchaLimit: "মাসে কত পারবেন",
    kharchaLimitHint: "এটা শুধু আপনি দেখেন। কোনো মাসে বেশি মনে হলে সাহায্যের জন্য কেউ ফোন করবেন।",
    kharchaLimitSave: "সংরক্ষণ করুন",
    kharchaNothingYet: "এখনও কিছু লেখা নেই। যাত্রার খরচ যোগ করুন, পরেরটার হিসেব হয়ে যাবে।",
    kharchaWhy: "এই টাকা কেন",
    kharchaYourWords: "আপনার কথায়",
    kharchaCouldNotRead: "টাকার অঙ্ক পড়া যায়নি। দয়া করে লিখুন।",
    kharchaReadyToBook: "বুক করার জন্য তৈরি",
    kharchaBook: "এই গাড়ি বুক করুন",
    kharchaShareContact: "আমার নাম ও ফোন চালককে দিন",
    kharchaToPay: "পেমেন্ট বাকি",
    kharchaPay: "{vendor}-কে টাকা দিন",
    openInApp: "অ্যাপে খুলুন",
    openApp: "{app} খুলুন",
    handoffWhere: "হাসপাতালের ঠিকানা",
    handoffCopied: "কোনো অ্যাপে চাপলে এই ঠিকানা কপি হয়। অ্যাপ কোথায় যাবেন জিজ্ঞাসা করলে এটি পেস্ট করুন।",
    routeTitle: "যাত্রাপথ বেছে নিন",
    routeFar: "বাড়ি থেকে {city} পর্যন্ত",
    routeNear: "এখনকার জায়গা থেকে হাসপাতাল পর্যন্ত",
    routeNote: "মানচিত্রে খুলবে। প্রতিটি যানবাহনের সময় ও পথ সেখানে দেখা যাবে।",
    modeTransit: "ট্রেন / বাস",
    modeDrive: "ট্যাক্সি / গাড়ি",
    modeWalk: "হেঁটে",
    wayShow: "পথ দেখান",
    wayFrom: "আপনি কোথা থেকে যাচ্ছেন? (স্টেশন বা জায়গা)",
    wayBest: "আপনার জন্য প্রস্তাবিত",
    wayBoard: "উঠুন",
    wayOff: "নামুন",
    wayTowards: "অভিমুখে",
    wayWalk: "{n} মিনিট হাঁটুন",
    wayStops: "{n} স্টপ",
    wayNoChange: "বদল নেই",
    wayChanges: "{n} বার বদল",
    wayCostNone: "খরচ জানা নেই",
    wayFareService: "পরিষেবার ভাড়া",
    wayFareQuote: "বিক্রেতার বলা দাম",
    wayLeaveBy: "{t}-এর মধ্যে রওনা দিন",
    wayDemo: "নমুনা সময়সূচি — আসল নয়",
    wayCantLoad: "এখন পথ পাওয়া গেল না। মানচিত্রে খুলুন।",
    tagCheapest: "সবচেয়ে সস্তা",
    tagFastest: "সবচেয়ে দ্রুত",
    tagFewest: "সবচেয়ে কম বদল",
    tagLeastWalk: "সবচেয়ে কম হাঁটা",
    reasonFits: "আপনার বলা খরচের মধ্যে",
    reasonSomeOver: "আপনার বলা খরচের বেশি পথগুলো বাদ দেওয়া হয়েছে",
    reasonAllOver: "সব পথই আপনার বলা খরচের বেশি; এটি সবচেয়ে কম",
    wayOver: "আপনার সীমার বেশি",
    modeBus: "বাস",
    modeMetro: "মেট্রো",
    modeTrain: "ট্রেন",
    modeTaxi: "ট্যাক্সি",
    modeStep: "হাঁটা",
    wayNoLimit: "মাসে কত সামলাতে পারবেন তা খরচা ট্যাবে জানান — তখন আমরা খরচ দেখে বেছে দেব",
    nearTitle: "আশেপাশে কী পাবেন",
    nearMedicine: "ওষুধ",
    nearTests: "পরীক্ষা",
    nearEquipment: "সরঞ্জাম",
    nearClinic: "ক্লিনিক",
    nearHospital: "হাসপাতালের কাছে",
    nearHome: "বাড়ির কাছে",
    nearCall: "ফোন করুন",
    nearDirections: "পথ",
    nearOpenThen: "এখন খোলা",
    nearShutThen: "এখন বন্ধ",
    nearHoursUnknown: "সময় জানা নেই",
    nearRoundClock: "২৪ ঘণ্টা খোলা",
    nearGovPrice: "সরকারি দামে জেনেরিক ওষুধ",
    nearConfirm: "ফোন করে জেনে নিন জিনিসটি আছে কি না — দোকানে কী আছে আমরা জানি না",
    nearRough: "দূরত্ব সরলরেখায়; আসল পথ মানচিত্রে দেখা যাবে",
    nearPowered: "স্থানগুলি Google থেকে",
    nearDemo: "নমুনা স্থান — আসল নয়",
    nearCantLoad: "আশেপাশের জায়গা এখন পাওয়া গেল না",
    nearNone: "কাছাকাছি কিছু পাওয়া যায়নি",
    nearOsm: "© OpenStreetMap contributors",
    mapOpen: "মানচিত্রে দেখুন",
    mapAllow: "নিজের অবস্থান দেখতে লোকেশনের অনুমতি দিন",
    mapWalk: "হেঁটে",
    mapCar: "গাড়ি",
    mapNavigate: "Maps-এ পথ শুরু করুন",
    mapRoute: "{d} · {t} মিনিট",
    mapClose: "বন্ধ করুন",
    mapNoRoute: "এখন পথ পাওয়া গেল না",
    mapPick: "মানচিত্রে কোনো জায়গা ছুঁয়ে দেখুন",
    mapHospital: "হাসপাতাল",
    mapYou: "আপনি",
    catTravel: "যাতায়াত",
    catStay: "থাকা",
    catFood: "খাবার",
    catMedicine: "ওষুধ",
    catHospital: "হাসপাতাল",
    catOther: "অন্যান্য",
    nudgeStay: "থাকার খরচ যাতায়াতের চেয়ে বেশি। {org} হাসপাতালের কাছে এবং কম খরচের।",
    nudgeScheme: "স্কিম কার্ডে হাসপাতাল ও ওষুধের খরচ ঢাকা হতে পারে। হেল্প ডেস্কে জিজ্ঞাসা করুন।",
    nudgeRail: "ক্যান্সার রোগীদের রেল ভাড়ায় ছাড়ের কথা স্টেশনে জিজ্ঞাসা করুন। হাসপাতালের সার্টিফিকেট লাগবে।",
    nudgeOver: "এই মাসের খরচ আপনার বলা সীমার চেয়ে বেশি মনে হচ্ছে। হাসপাতাল থেকে কেউ সাহায্যের জন্য ফোন করবেন।",
    budgetSent: "ধন্যবাদ। একজন ব্যক্তি এটি নিশ্চিত করবেন।",
    tierSubsidised: "ছাড়যুক্ত",
    tierModest: "কম খরচ",
    tierStandard: "সাধারণ দর",
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
    budgetTitle: "ଖର୍ଚ୍ଚ ବିଷୟରେ",
    budgetWhy: "ଆମେ ପଚାରୁଛୁ ଯେପରି ଆପଣ ବହନ କରିପାରିବେ ନାହିଁ ଏପରି କିଛି ଠିକ୍ ନହୁଏ।",
    budgetTravel: "ଯିବା ଆସିବା",
    budgetStay: "ରହିବା ସ୍ଥାନ",
    budgetMedicine: "ଔଷଧ",
    budgetChoose: "ଗୋଟିଏ ବାଛନ୍ତୁ",
    budgetCannotManage: "ଏଥିମଧ୍ୟରୁ କୌଣସିଟି ମୁଁ ପାରିବି ନାହିଁ",
    budgetSuggested: "ଆପଣଙ୍କ ପାଇଁ ପରାମର୍ଶ",
    kharchaTab: "ଖର୍ଚ୍ଚ",
    kharchaThisMonth: "ଏହି ମାସ",
    kharchaNextMonth: "ଆସନ୍ତା ମାସ",
    kharchaSpent: "ଖର୍ଚ୍ଚ ହୋଇଛି",
    kharchaBooked: "ବୁକ୍ ହୋଇଛି",
    kharchaExpected: "ଆଗକୁ ହେବ",
    kharchaCannotSayYet: "ଏବେ କହି ହେବ ନାହିଁ: ପୂର୍ବ ଯାତ୍ରାର ଖର୍ଚ୍ଚ ଲେଖା ନାହିଁ।",
    kharchaBasedOnVisits: "ଆପଣଙ୍କ ଶେଷ {n}ଟି ଯାତ୍ରା ଅନୁସାରେ",
    kharchaVisitsAhead: "ଆଗକୁ {n}ଟି ଯାତ୍ରା",
    kharchaNoVisitsAhead: "ଆଗକୁ କୌଣସି ଯାତ୍ରା ନାହିଁ",
    kharchaAdd: "ଖର୍ଚ୍ଚ ଯୋଡ଼ନ୍ତୁ",
    kharchaAddHint: "କୁହନ୍ତୁ ବା ଲେଖନ୍ତୁ, ଯେପରି “ଅଟୋ 450”",
    kharchaAmount: "ଟଙ୍କା (₹)",
    kharchaKind: "କାହା ପାଇଁ",
    kharchaSave: "ଯୋଡ଼ନ୍ତୁ",
    kharchaIsThisRight: "ଏହା ଠିକ୍ କି?",
    kharchaYes: "ହଁ, ଠିକ୍",
    kharchaNo: "ନା, ହଟାନ୍ତୁ",
    kharchaLimit: "ମାସକୁ କେତେ କରିପାରିବେ",
    kharchaLimitHint: "ଏହା କେବଳ ଆପଣ ଦେଖନ୍ତି। କୌଣସି ମାସ ଅଧିକ ଲାଗିଲେ ସାହାଯ୍ୟ ପାଇଁ କେହି ଫୋନ୍ କରିବେ।",
    kharchaLimitSave: "ସଞ୍ଚୟ କରନ୍ତୁ",
    kharchaNothingYet: "ଏବେ କିଛି ଲେଖା ନାହିଁ। ଯାତ୍ରାର ଖର୍ଚ୍ଚ ଯୋଡ଼ନ୍ତୁ, ପରବର୍ତ୍ତୀର ହିସାବ ହୋଇଯିବ।",
    kharchaWhy: "ଏହି ଟଙ୍କା କାହିଁକି",
    kharchaYourWords: "ଆପଣଙ୍କ ଶବ୍ଦରେ",
    kharchaCouldNotRead: "ଟଙ୍କା ପଢ଼ି ହେଲା ନାହିଁ। ଦୟାକରି ଲେଖନ୍ତୁ।",
    kharchaReadyToBook: "ବୁକ୍ କରିବାକୁ ପ୍ରସ୍ତୁତ",
    kharchaBook: "ଏହି ଗାଡ଼ି ବୁକ୍ କରନ୍ତୁ",
    kharchaShareContact: "ମୋ ନାମ ଓ ଫୋନ୍ ଡ୍ରାଇଭରଙ୍କୁ ଦିଅନ୍ତୁ",
    kharchaToPay: "ଦେୟ ବାକି",
    kharchaPay: "{vendor}ଙ୍କୁ ଟଙ୍କା ଦିଅନ୍ତୁ",
    openInApp: "ଆପ୍‌ରେ ଖୋଲନ୍ତୁ",
    openApp: "{app} ଖୋଲନ୍ତୁ",
    handoffWhere: "ଡାକ୍ତରଖାନାର ଠିକଣା",
    handoffCopied: "କୌଣସି ଆପ୍‌ ଦବାଇଲେ ଏହି ଠିକଣା କପି ହୁଏ। ଆପ୍‌ କେଉଁଠି ଯିବେ ପଚାରିଲେ ଏହାକୁ ପେଷ୍ଟ କରନ୍ତୁ।",
    routeTitle: "ରାସ୍ତା ବାଛନ୍ତୁ",
    routeFar: "ଘରୁ {city} ପର୍ଯ୍ୟନ୍ତ",
    routeNear: "ଏବେର ସ୍ଥାନରୁ ଡାକ୍ତରଖାନା ପର୍ଯ୍ୟନ୍ତ",
    routeNote: "ମାନଚିତ୍ରରେ ଖୁଲିବ। ପ୍ରତ୍ୟେକ ସାଧନର ସମୟ ଓ ରାସ୍ତା ସେଠି ଦେଖାଯିବ।",
    modeTransit: "ଟ୍ରେନ୍ / ବସ୍",
    modeDrive: "ଟ୍ୟାକ୍ସି / ଗାଡ଼ି",
    modeWalk: "ଚାଲି",
    wayShow: "ରାସ୍ତା ଦେଖାନ୍ତୁ",
    wayFrom: "ଆପଣ କେଉଁଠୁ ଯାଉଛନ୍ତି? (ଷ୍ଟେସନ୍ କିମ୍ବା ସ୍ଥାନ)",
    wayBest: "ଆପଣଙ୍କ ପାଇଁ ପରାମର୍ଶ",
    wayBoard: "ଚଢ଼ନ୍ତୁ",
    wayOff: "ଓହ୍ଲାନ୍ତୁ",
    wayTowards: "ଦିଗକୁ",
    wayWalk: "{n} ମିନିଟ୍ ଚାଲନ୍ତୁ",
    wayStops: "{n} ଷ୍ଟପ୍",
    wayNoChange: "ବଦଳ ନାହିଁ",
    wayChanges: "{n} ଥର ବଦଳାନ୍ତୁ",
    wayCostNone: "ଖର୍ଚ୍ଚ ଜଣା ନାହିଁ",
    wayFareService: "ସେବାର ଭଡ଼ା",
    wayFareQuote: "ବିକ୍ରେତାଙ୍କ କହିଥିବା ଦାମ୍",
    wayLeaveBy: "{t} ସୁଦ୍ଧା ବାହାରନ୍ତୁ",
    wayDemo: "ନମୁନା ସମୟସୂଚୀ — ପ୍ରକୃତ ନୁହେଁ",
    wayCantLoad: "ଏବେ ରାସ୍ତା ମିଳିଲା ନାହିଁ। ମାନଚିତ୍ରରେ ଖୋଲନ୍ତୁ।",
    tagCheapest: "ସବୁଠୁ ସସ୍ତା",
    tagFastest: "ସବୁଠୁ ତ୍ୱରିତ",
    tagFewest: "ସବୁଠୁ କମ୍ ବଦଳ",
    tagLeastWalk: "ସବୁଠୁ କମ୍ ଚାଲିବା",
    reasonFits: "ଆପଣଙ୍କ କହିଥିବା ଖର୍ଚ୍ଚ ମଧ୍ୟରେ",
    reasonSomeOver: "ଆପଣଙ୍କ କହିଥିବା ଖର୍ଚ୍ଚଠୁ ଅଧିକ ରାସ୍ତାକୁ ହଟାଯାଇଛି",
    reasonAllOver: "ସବୁ ରାସ୍ତା ଆପଣଙ୍କ କହିଥିବା ଖର୍ଚ୍ଚଠୁ ଅଧିକ; ଏହା ସବୁଠୁ କମ୍",
    wayOver: "ଆପଣଙ୍କ ସୀମାଠୁ ଅଧିକ",
    modeBus: "ବସ୍",
    modeMetro: "ମେଟ୍ରୋ",
    modeTrain: "ଟ୍ରେନ୍",
    modeTaxi: "ଟ୍ୟାକ୍ସି",
    modeStep: "ଚାଲି",
    wayNoLimit: "ମାସକୁ କେତେ ସମ୍ଭାଳି ପାରିବେ ଖର୍ଚ୍ଚା ଟାବ୍‌ରେ କହନ୍ତୁ — ତା'ପରେ ଆମେ ଖର୍ଚ୍ଚ ଦେଖି ବାଛିବୁ",
    nearTitle: "ଆଖପାଖରେ କ'ଣ ମିଳିବ",
    nearMedicine: "ଔଷଧ",
    nearTests: "ପରୀକ୍ଷା",
    nearEquipment: "ଉପକରଣ",
    nearClinic: "କ୍ଲିନିକ୍",
    nearHospital: "ଡାକ୍ତରଖାନା ପାଖରେ",
    nearHome: "ଘର ପାଖରେ",
    nearCall: "ଫୋନ୍ କରନ୍ତୁ",
    nearDirections: "ରାସ୍ତା",
    nearOpenThen: "ଏବେ ଖୋଲା",
    nearShutThen: "ଏବେ ବନ୍ଦ",
    nearHoursUnknown: "ସମୟ ଜଣା ନାହିଁ",
    nearRoundClock: "୨୪ ଘଣ୍ଟା ଖୋଲା",
    nearGovPrice: "ସରକାରୀ ଦରରେ ଜେନେରିକ୍ ଔଷଧ",
    nearConfirm: "ଫୋନ୍ କରି ପଚାରନ୍ତୁ ଜିନିଷ ମିଳିବ କି ନାହିଁ — ଦୋକାନରେ କ'ଣ ଅଛି ଆମେ ଜାଣୁନାହୁଁ",
    nearRough: "ଦୂରତା ସିଧା ରେଖାରେ; ପ୍ରକୃତ ରାସ୍ତା ମାନଚିତ୍ରରେ ଦେଖାଯିବ",
    nearPowered: "ସ୍ଥାନଗୁଡ଼ିକ Google ରୁ",
    nearDemo: "ନମୁନା ସ୍ଥାନ — ପ୍ରକୃତ ନୁହେଁ",
    nearCantLoad: "ଆଖପାଖ ସ୍ଥାନ ଏବେ ମିଳିଲା ନାହିଁ",
    nearNone: "ପାଖରେ କିଛି ମିଳିଲା ନାହିଁ",
    nearOsm: "© OpenStreetMap contributors",
    mapOpen: "ମାନଚିତ୍ରରେ ଦେଖନ୍ତୁ",
    mapAllow: "ନିଜ ସ୍ଥାନ ଦେଖିବାକୁ ଲୋକେସନ୍ ଅନୁମତି ଦିଅନ୍ତୁ",
    mapWalk: "ଚାଲି",
    mapCar: "ଗାଡ଼ି",
    mapNavigate: "Maps ରେ ରାସ୍ତା ଆରମ୍ଭ କରନ୍ତୁ",
    mapRoute: "{d} · {t} ମିନିଟ୍",
    mapClose: "ବନ୍ଦ କରନ୍ତୁ",
    mapNoRoute: "ଏବେ ରାସ୍ତା ମିଳିଲା ନାହିଁ",
    mapPick: "ମାନଚିତ୍ରରେ କୌଣସି ସ୍ଥାନ ଛୁଅନ୍ତୁ",
    mapHospital: "ଡାକ୍ତରଖାନା",
    mapYou: "ଆପଣ",
    catTravel: "ଯିବା-ଆସିବା",
    catStay: "ରହିବା",
    catFood: "ଖାଦ୍ୟ",
    catMedicine: "ଔଷଧ",
    catHospital: "ଡାକ୍ତରଖାନା",
    catOther: "ଅନ୍ୟାନ୍ୟ",
    nudgeStay: "ରହିବା ଖର୍ଚ୍ଚ ଯିବା-ଆସିବାଠାରୁ ଅଧିକ। {org} ଡାକ୍ତରଖାନା ପାଖରେ ଏବଂ କମ୍ ଖର୍ଚ୍ଚ।",
    nudgeScheme: "ଯୋଜନା କାର୍ଡରେ ଡାକ୍ତରଖାନା ଓ ଔଷଧ ଖର୍ଚ୍ଚ କଭର୍ ହୋଇପାରେ। ହେଲ୍ପ ଡେସ୍କରେ ପଚାରନ୍ତୁ।",
    nudgeRail: "କର୍କଟ ରୋଗୀଙ୍କ ପାଇଁ ରେଳ ଭଡ଼ା ରିହାତି ବିଷୟରେ ଷ୍ଟେସନରେ ପଚାରନ୍ତୁ। ଡାକ୍ତରଖାନାର ପ୍ରମାଣପତ୍ର ଲାଗିବ।",
    nudgeOver: "ଏହି ମାସର ଖର୍ଚ୍ଚ ଆପଣ କହିଥିବା ସୀମାଠାରୁ ଅଧିକ ଲାଗୁଛି। ଡାକ୍ତରଖାନାରୁ କେହି ସାହାଯ୍ୟ ପାଇଁ ଫୋନ୍ କରିବେ।",
    budgetSent: "ଧନ୍ୟବାଦ। ଜଣେ ବ୍ୟକ୍ତି ଏହା ନିଶ୍ଚିତ କରିବେ।",
    tierSubsidised: "ରିହାତି",
    tierModest: "କମ୍ ଖର୍ଚ୍ଚ",
    tierStandard: "ସାଧାରଣ ଦର",
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
  ta: {
    come: "வாருங்கள்",
    wait: "காத்திருங்கள்",
    notYet: "இன்னும் இல்லை",
    travelOn: "பயணம்",
    noPlanYet: "உங்கள் திட்டம் தயாராகிறது…",
    personCalling: "எங்கள் குழுவில் ஒருவர் உங்களை அழைப்பார்.",
    why: "ஏன்",
    waitingFor: "எதற்கு காத்திருக்கிறோம்",
    expectedBetween: "எதிர்பார்க்கப்படுகிறது",
    onThisDay: "உறுதி",
    plan: "உங்கள் திட்டம்",
    done: "முடிந்தது",
    waiting: "காத்திருக்கிறது",
    ahead: "வரவிருப்பது",
    nextVisit: "இதுவே சந்திப்பு",
    noTravelNeeded: "பயணம் தேவையில்லை",
    messages: "செய்திகள்",
    planTab: "திட்டம்",
    you: "நீங்கள்",
    ask: "கேளுங்கள்",
    askPlaceholder: "உங்கள் கேள்வியை எழுதுங்கள்",
    send: "அனுப்பு",
    sending: "அனுப்புகிறது…",
    speak: "பேசுங்கள்",
    reading: "வாசிக்கிறது…",
    listening: "கேட்கிறது…",
    transcribing: "எழுதுகிறது…",
    checkBeforeSending: "அனுப்பும் முன் சரிபாருங்கள்",
    aPersonWillReply: "ஒருவர் பதிலளிப்பார்",
    language: "மொழி",
    languageChanged: "மொழி மாற்றப்பட்டது",
    journey: "பயணம்",
    kmAway: "கி.மீ. தொலைவில்",
    hoursEachWay: "மணி நேரம் ஒரு பக்கம்",
    working: "சாத்தி சரிபார்க்கிறது…",
    updated: "புதுப்பிக்கப்பட்டது",
    todayTab: "இன்று",
    bring: "எடுத்து வர வேண்டியவை",
    firstStop: "முதலில் செல்ல வேண்டிய இடம்",
    tapForWhy: "ஏன்? பார்க்க தொடுங்கள்",
    packed: "எடுத்துவிட்டேன்",
    journeyTab: "பயணம்",
    budgetTitle: "செலவு பற்றி",
    budgetWhy: "உங்களால் முடியாத ஏற்பாடு எதுவும் செய்யப்படாமல் இருக்க இதைக் கேட்கிறோம்.",
    budgetTravel: "அங்கு செல்வது",
    budgetStay: "தங்குவதற்கு இடம்",
    budgetMedicine: "மருந்துகள்",
    budgetChoose: "ஒன்றைத் தேர்ந்தெடுங்கள்",
    budgetCannotManage: "இவற்றில் எதுவும் என்னால் முடியாது",
    budgetSuggested: "உங்களுக்கு பரிந்துரைக்கப்பட்டது",
    kharchaTab: "செலவு",
    kharchaThisMonth: "இந்த மாதம்",
    kharchaNextMonth: "அடுத்த மாதம்",
    kharchaSpent: "செலவானது",
    kharchaBooked: "முன்பதிவு",
    kharchaExpected: "இனி வரும்",
    kharchaCannotSayYet: "இப்போது சொல்ல முடியாது: முந்தைய பயணச் செலவு பதிவில்லை.",
    kharchaBasedOnVisits: "உங்கள் கடைசி {n} பயணங்களின் அடிப்படையில்",
    kharchaVisitsAhead: "இனி {n} பயணங்கள்",
    kharchaNoVisitsAhead: "இனி பயணம் இல்லை",
    kharchaAdd: "செலவைச் சேர்",
    kharchaAddHint: "சொல்லுங்கள் அல்லது எழுதுங்கள், எ.கா. “ஆட்டோ 450”",
    kharchaAmount: "தொகை (₹)",
    kharchaKind: "எதற்கு",
    kharchaSave: "சேர்",
    kharchaIsThisRight: "இது சரியா?",
    kharchaYes: "ஆம், சரி",
    kharchaNo: "இல்லை, நீக்கு",
    kharchaLimit: "மாதம் எவ்வளவு சமாளிக்க முடியும்",
    kharchaLimitHint: "இதை நீங்கள் மட்டுமே பார்க்கிறீர்கள். ஒரு மாதம் அதிகமாகத் தோன்றினால், உதவ ஒருவர் அழைப்பார்.",
    kharchaLimitSave: "சேமி",
    kharchaNothingYet: "இன்னும் எதுவும் பதிவில்லை. பயணச் செலவைச் சேர்த்தால் அடுத்ததைக் கணக்கிடலாம்.",
    kharchaWhy: "இந்தத் தொகை ஏன்",
    kharchaYourWords: "உங்கள் வார்த்தைகளில்",
    kharchaCouldNotRead: "தொகையைப் படிக்க முடியவில்லை. தயவுசெய்து எழுதுங்கள்.",
    kharchaReadyToBook: "முன்பதிவுக்குத் தயார்",
    kharchaBook: "இந்தப் பயணத்தை முன்பதிவு செய்",
    kharchaShareContact: "என் பெயர், தொலைபேசியை ஓட்டுநருடன் பகிர்",
    kharchaToPay: "செலுத்த வேண்டியது",
    kharchaPay: "{vendor}-க்குச் செலுத்து",
    openInApp: "செயலியில் திற",
    openApp: "{app} திற",
    handoffWhere: "மருத்துவமனை முகவரி",
    handoffCopied: "ஒரு செயலியைத் தொட்டால் இந்த முகவரி நகலெடுக்கப்படும். எங்கே செல்ல வேண்டும் என்று கேட்கும் இடத்தில் ஒட்டவும்.",
    routeTitle: "பயண வழியைத் தேர்ந்தெடுக்கவும்",
    routeFar: "வீட்டிலிருந்து {city} வரை",
    routeNear: "இப்போதைய இடத்திலிருந்து மருத்துவமனை வரை",
    routeNote: "வரைபடத்தில் திறக்கும். ஒவ்வொரு வழியின் நேரமும் பாதையும் அங்கே தெரியும்.",
    modeTransit: "ரயில் / பேருந்து",
    modeDrive: "டாக்சி / கார்",
    modeWalk: "நடந்து",
    wayShow: "வழிகளைக் காட்டு",
    wayFrom: "எங்கிருந்து புறப்படுகிறீர்கள்? (நிலையம் அல்லது இடம்)",
    wayBest: "உங்களுக்குப் பரிந்துரை",
    wayBoard: "ஏறுங்கள்",
    wayOff: "இறங்குங்கள்",
    wayTowards: "நோக்கி",
    wayWalk: "{n} நிமிடம் நடக்கவும்",
    wayStops: "{n} நிறுத்தங்கள்",
    wayNoChange: "மாற்றம் இல்லை",
    wayChanges: "{n} முறை மாற்றம்",
    wayCostNone: "செலவு தெரியவில்லை",
    wayFareService: "சேவையின் கட்டணம்",
    wayFareQuote: "விற்பனையாளர் சொன்ன விலை",
    wayLeaveBy: "{t}-க்குள் புறப்படுங்கள்",
    wayDemo: "மாதிரி நேரப்பட்டியல் — உண்மையல்ல",
    wayCantLoad: "இப்போது வழிகள் கிடைக்கவில்லை. வரைபடத்தில் திறக்கவும்.",
    tagCheapest: "மிகவும் மலிவு",
    tagFastest: "மிக வேகம்",
    tagFewest: "குறைந்த மாற்றம்",
    tagLeastWalk: "குறைந்த நடை",
    reasonFits: "நீங்கள் சொன்ன செலவுக்குள்",
    reasonSomeOver: "நீங்கள் சொன்ன செலவை விட அதிகமான வழிகள் நீக்கப்பட்டன",
    reasonAllOver: "எல்லா வழிகளும் நீங்கள் சொன்ன செலவை விட அதிகம்; இது குறைவானது",
    wayOver: "உங்கள் வரம்புக்கு மேல்",
    modeBus: "பேருந்து",
    modeMetro: "மெட்ரோ",
    modeTrain: "ரயில்",
    modeTaxi: "டாக்சி",
    modeStep: "நடை",
    wayNoLimit: "மாதம் எவ்வளவு சமாளிக்க முடியும் என்பதை செலவு தாவலில் சொல்லுங்கள் — அப்போது செலவைப் பார்த்துத் தேர்ந்தெடுப்போம்",
    nearTitle: "அருகில் என்ன கிடைக்கும்",
    nearMedicine: "மருந்துகள்",
    nearTests: "பரிசோதனை",
    nearEquipment: "உபகரணங்கள்",
    nearClinic: "கிளினிக்",
    nearHospital: "மருத்துவமனை அருகில்",
    nearHome: "வீட்டின் அருகில்",
    nearCall: "அழைக்கவும்",
    nearDirections: "வழி",
    nearOpenThen: "இப்போது திறந்துள்ளது",
    nearShutThen: "இப்போது மூடியுள்ளது",
    nearHoursUnknown: "நேரம் தெரியவில்லை",
    nearRoundClock: "24 மணி நேரமும் திறந்திருக்கும்",
    nearGovPrice: "அரசு விலையில் ஜெனரிக் மருந்துகள்",
    nearConfirm: "அழைத்து உறுதி செய்யுங்கள் — கடையில் என்ன உள்ளது என்பது எங்களுக்குத் தெரியாது",
    nearRough: "தூரம் நேர்கோட்டில்; உண்மையான வழி வரைபடத்தில் தெரியும்",
    nearPowered: "இடங்கள் Google-இலிருந்து",
    nearDemo: "மாதிரி இடம் — உண்மையல்ல",
    nearCantLoad: "அருகிலுள்ள இடங்கள் இப்போது கிடைக்கவில்லை",
    nearNone: "அருகில் எதுவும் கிடைக்கவில்லை",
    nearOsm: "© OpenStreetMap contributors",
    mapOpen: "வரைபடத்தில் பார்க்க",
    mapAllow: "உங்கள் இடத்தைக் காண இருப்பிட அனுமதி தரவும்",
    mapWalk: "நடந்து",
    mapCar: "கார்",
    mapNavigate: "Maps-இல் வழியைத் தொடங்கவும்",
    mapRoute: "{d} · {t} நிமிடம்",
    mapClose: "மூடு",
    mapNoRoute: "இப்போது வழி கிடைக்கவில்லை",
    mapPick: "வரைபடத்தில் ஒரு இடத்தைத் தொடவும்",
    mapHospital: "மருத்துவமனை",
    mapYou: "நீங்கள்",
    catTravel: "போக்குவரத்து",
    catStay: "தங்குமிடம்",
    catFood: "உணவு",
    catMedicine: "மருந்துகள்",
    catHospital: "மருத்துவமனை",
    catOther: "மற்றவை",
    nudgeStay: "தங்கும் செலவு பயணத்தை விட அதிகம். {org} மருத்துவமனை அருகில் உள்ளது, குறைந்த செலவு.",
    nudgeScheme: "திட்ட அட்டை மருத்துவமனை மற்றும் மருந்தகச் செலவை ஈடுகட்டலாம். உதவி மையத்தில் கேளுங்கள்.",
    nudgeRail: "புற்றுநோயாளிகளுக்கான ரயில் கட்டணச் சலுகை பற்றி நிலையத்தில் கேளுங்கள். மருத்துவமனைச் சான்றிதழ் தேவை.",
    nudgeOver: "இந்த மாதச் செலவு நீங்கள் சொன்ன வரம்பை விட அதிகமாகத் தெரிகிறது. மருத்துவமனையிலிருந்து ஒருவர் உதவ அழைப்பார்.",
    budgetSent: "நன்றி. ஒருவர் இதை உறுதிப்படுத்துவார்.",
    tierSubsidised: "சலுகை",
    tierModest: "குறைந்த செலவு",
    tierStandard: "வழக்கமான விலை",
    doNow: "இதை இப்போது செய்யுங்கள்",
    progress: "{total} படிகளில் {done} முடிந்தது",
    noJourney: "உங்கள் படிப்படியான பயணம் இங்கே தெரியும்.",
    stageTests: "பரிசோதனை",
    stageReports: "அறிக்கை",
    stageInsurance: "திட்ட ஒப்புதல்",
    stagePharmacy: "மருந்தகம்",
    stageAppointment: "நேரம் உறுதி",
    stageDoctor: "மருத்துவர் வருகை",
    stageBed: "படுக்கை",
    stageRide: "வாகனம்",
    stageStay: "தங்கும் இடம்",
    stageDocuments: "ஆவணங்கள்",
    stageVisit: "மருத்துவரை சந்திப்பு",
    stageNextSession: "அடுத்த முறை",
    stateDone: "முடிந்தது",
    stateNow: "இப்போது",
    stateWaiting: "நடந்து கொண்டிருக்கிறது",
    stateProblem: "சிக்கல்",
    stateNext: "அடுத்து",
    actionNothingYet: "நாங்கள் இதில் வேலை செய்கிறோம். நீங்கள் எதுவும் செய்ய வேண்டாம்.",
    actionWaitForTeam: "ஒரு சிக்கல் உள்ளது. எங்கள் குழு வேறு வழி ஏற்பாடு செய்கிறது. இப்போது பயணம் செய்ய வேண்டாம்.",
    actionKeepDocuments: "தயவுசெய்து உங்கள் ஆவணங்களை தயாராக வைத்திருங்கள்.",
    actionPickup: "உங்கள் வாகனம் ஏற்பாடு செய்யப்பட்டுள்ளது. அழைத்துச் செல்லும் நேரத்தில் தயாராக இருங்கள்.",
    actionFirstStop: "உங்கள் சந்திப்பு உறுதியாகிவிட்டது.",
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
    budgetTitle: "About the cost",
    budgetWhy: "We ask so that nothing is arranged for you that you cannot afford.",
    budgetTravel: "Getting there",
    budgetStay: "Somewhere to stay",
    budgetMedicine: "Medicines",
    budgetChoose: "Choose one",
    budgetCannotManage: "I cannot manage any of these",
    budgetSuggested: "Suggested for you",
    kharchaTab: "Spends",
    kharchaThisMonth: "This month",
    kharchaNextMonth: "Next month",
    kharchaSpent: "Spent",
    kharchaBooked: "Booked",
    kharchaExpected: "Still to come",
    kharchaCannotSayYet: "We cannot say yet: no trips recorded to go on.",
    kharchaBasedOnVisits: "Based on your last {n} visits",
    kharchaVisitsAhead: "{n} visits ahead",
    kharchaNoVisitsAhead: "No visits ahead",
    kharchaAdd: "Add a spend",
    kharchaAddHint: "Say or type it, like “auto 450”",
    kharchaAmount: "Amount (₹)",
    kharchaKind: "What for",
    kharchaSave: "Add",
    kharchaIsThisRight: "Is this right?",
    kharchaYes: "Yes, that's right",
    kharchaNo: "No, remove it",
    kharchaLimit: "What you can manage in a month",
    kharchaLimitHint: "Only you see this. If a month looks like more, someone will call to help.",
    kharchaLimitSave: "Save",
    kharchaNothingYet: "Nothing recorded yet. Add what the trip cost, and the next one can be worked out.",
    kharchaWhy: "Why this number",
    kharchaYourWords: "In your words",
    kharchaCouldNotRead: "We could not read the amount. Please type it.",
    kharchaReadyToBook: "Ready to book",
    kharchaBook: "Book this ride",
    kharchaShareContact: "Share my first name and phone with the driver",
    kharchaToPay: "To pay",
    kharchaPay: "Pay {vendor}",
    openInApp: "Open in an app",
    openApp: "Open {app}",
    handoffWhere: "Hospital address",
    handoffCopied: "Tapping an app copies this address. Paste it where the app asks where you are going.",
    routeTitle: "Choose how to get there",
    routeFar: "From home to {city}",
    routeNear: "From where you are to the hospital",
    routeNote: "Opens in Maps, which shows the time and the route for each way of travelling.",
    modeTransit: "Train / bus",
    modeDrive: "Taxi / car",
    modeWalk: "Walk",
    wayShow: "Show ways to go",
    wayFrom: "Where are you starting from? (a station or place)",
    wayBest: "Suggested for you",
    wayBoard: "Board",
    wayOff: "Get off at",
    wayTowards: "towards",
    wayWalk: "Walk {n} min",
    wayStops: "{n} stops",
    wayNoChange: "No change",
    wayChanges: "{n} changes",
    wayCostNone: "Cost not known",
    wayFareService: "Fare from the route service",
    wayFareQuote: "Price the seller quoted",
    wayLeaveBy: "Leave by {t}",
    wayDemo: "Sample timetable — not real",
    wayCantLoad: "Could not get routes just now. Open in Maps.",
    tagCheapest: "Cheapest",
    tagFastest: "Fastest",
    tagFewest: "Fewest changes",
    tagLeastWalk: "Least walking",
    reasonFits: "Fits what you said you can manage",
    reasonSomeOver: "Ways over what you said you can manage are left out",
    reasonAllOver: "Every way is over what you said you can manage; this is the lowest",
    wayOver: "Over your limit",
    modeBus: "Bus",
    modeMetro: "Metro",
    modeTrain: "Train",
    modeTaxi: "Taxi",
    modeStep: "Walk",
    wayNoLimit: "Tell us what you can manage each month (Kharcha tab) and we will weigh the cost for you",
    nearTitle: "Near you",
    nearMedicine: "Medicines",
    nearTests: "Tests",
    nearEquipment: "Equipment",
    nearClinic: "Clinics",
    nearHospital: "Near the hospital",
    nearHome: "Near home",
    nearCall: "Call",
    nearDirections: "Directions",
    nearOpenThen: "Open then",
    nearShutThen: "Shut then",
    nearHoursUnknown: "Hours not known",
    nearRoundClock: "Open 24 hours",
    nearGovPrice: "Generic medicines at government prices",
    nearConfirm: "Call to check they have it — we cannot tell what a shop has in stock",
    nearRough: "Distances are in a straight line; Maps shows the real way",
    nearPowered: "Places from Google",
    nearDemo: "Sample place — not real",
    nearCantLoad: "Could not find places just now",
    nearNone: "Nothing found nearby",
    nearOsm: "© OpenStreetMap contributors",
    mapOpen: "Show on map",
    mapAllow: "Allow location to see where you are",
    mapWalk: "Walk",
    mapCar: "Car",
    mapNavigate: "Start directions in Maps",
    mapRoute: "{d} · {t} min",
    mapClose: "Close",
    mapNoRoute: "No route just now",
    mapPick: "Tap a place on the map",
    mapHospital: "Hospital",
    mapYou: "You",
    catTravel: "Getting there",
    catStay: "Somewhere to stay",
    catFood: "Food",
    catMedicine: "Medicines",
    catHospital: "Hospital",
    catOther: "Other",
    nudgeStay: "Nights are costing more than travel. {org} is near the hospital and costs less.",
    nudgeScheme: "A scheme card may cover hospital and pharmacy costs. Ask at the help desk.",
    nudgeRail: "Ask at the station about the railway concession for cancer patients. You will need a certificate from the hospital.",
    nudgeOver: "This month looks like more than you said you can manage. Someone from the hospital will call to help.",
    budgetSent: "Thank you. A person will confirm this.",
    tierSubsidised: "Concession",
    tierModest: "Low cost",
    tierStandard: "Standard rate",
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
  ta: "ta-IN",
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
  ta: {
    consult: "மருத்துவரை சந்திப்பு",
    biopsy: "பயாப்ஸி",
    bloods: "இரத்த பரிசோதனை",
    scan: "ஸ்கேன்",
    pet_ct: "பெட்-சிடி ஸ்கேன்",
    pathology_report: "ஆய்வக அறிக்கை",
    radiology_report: "ஸ்கேன் அறிக்கை",
    review_consult: "மருத்துவரை மீண்டும் சந்திப்பு",
    joint_clinic: "கூட்டு கிளினிக்",
    treatment: "சிகிச்சை",
    maintenance_dose: "அடுத்த மருந்து",
    echo_review: "இதய பரிசோதனை மற்றும் சந்திப்பு",
    dialysis_session: "டயாலிசிஸ்",
    nephrology_review: "சிறுநீரக மருத்துவரை சந்திப்பு",
    discharge_review: "வீடு திரும்பிய பின் பரிசோதனை",
    wound_check: "காயம் பரிசோதனை",
  },
  en: {},
};

/** The step's name in this family's language, falling back to what the
 *  backend sent rather than to a blank. */
export const stepWord = (kind: string, fallback: string, lang: Lang): string =>
  STEP_WORDS[lang]?.[kind] ?? fallback;
