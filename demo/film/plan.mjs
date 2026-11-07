/**
 * The edit decision list for the end-to-end film.
 *
 * One source of truth, read by all three stages: `cards.mjs` renders the
 * still art, `narrate.py` speaks the voice-over, `build.sh` assembles. They
 * disagree the moment the plan lives in more than one file, and a film whose
 * narration is a beat out of step with its picture is worse than no narration.
 *
 * Some segments carry a `hindi` block. The source recordings have no audio at
 * all — `adb screenrecord` does not capture any — so the read-aloud the phone
 * actually played was never recorded. It is re-spoken here by the same service
 * (Sarvam `bulbul:v3`, hi-IN) saying the exact words on the screen at that
 * moment, transcribed from the frames. Where one is present the English
 * narration waits for it rather than talking over it: the point of that
 * chapter is the voice, and a narrator explaining a voice you cannot hear is
 * the wrong way round.
 *
 * Every `in`/`out` below was chosen by looking at the footage, not guessed.
 * The burned-in captions in the control-centre clips change at known seconds,
 * so each cut lands on a caption boundary; what is trimmed is hold time, which
 * is where all the dead air in these recordings lives.
 */

export const CANVAS = { w: 1920, h: 1080, fps: 30 };
export const INK = "#0b1220";

/** Where the footage is. */
export const SRC = "clips";

export const PLAN = [
  {
    id: "a-title", kind: "card", seconds: 9,
    card: { heading: "EKYATRA Saathi", sub: "A readiness-driven visit planner", kicker: "End to end, on the deployed system" },
    vo: "EKYATRA Saathi. A readiness driven visit planner, for families who travel a long way for cancer care. This is the whole system, end to end.",
  },
  {
    id: "b-question", kind: "card", seconds: 19,
    card: { heading: "One question", sub: "Is this trip worth making?", kicker: "Asked every day, for every family" },
    vo: "A family in Gaya is six hundred kilometres from the hospital. They travel, and the report is not ready. Or the doctor is not free. Or the cab never came. Saathi asks one question every day, for every family: is this trip worth making?",
  },

  { id: "c-chapter", kind: "card", seconds: 3, card: { chapter: "1", heading: "Taking a family on" }, vo: "" },
  {
    //: Starts at 12.5s. The clip opens with a load, then its own burned-in
    //: title card reading "Taking a family on" — which the chapter card now
    //: says, three seconds earlier. Two title cards in a row reads as a
    //: mistake, so the clip's one goes and the chapter card keeps the job.
    id: "c-onboarding", kind: "browser", seconds: 45.9,
    file: "16-onboarding-medical-background.webm", in: 12.5,
    vo: "A family is taken on in seven stages, and nothing is rushed into one sitting at a counter. Each stage saves on its own, so a navigator can stop and come back tomorrow. Anita Sharma's outstanding stage is the agreement to share, which only the family can answer. And this is the medical background stage: what the family itself reports. Known conditions, allergies, medicines, past hospital stays, an emergency contact. There is no place here to upload a report, and that is not an oversight. Nothing a pathologist wrote ever enters Saathi at all. Only doctors and administrators can see this stage. A navigator cannot, the planner never reads it, and it is never written into a message to the family.",
  },

  { id: "d-chapter", kind: "card", seconds: 3, card: { chapter: "2", heading: "The hospital's desk" }, vo: "" },
  {
    id: "d-walk1", kind: "browser", seconds: 47.5, file: "11-control-centre-walkthrough.mp4", in: 0,
    vo: "This is the control centre, what a hospital navigator sees. Today: what needs attention right now, the audit trail, hospitals on time, families on record. Families, grouped by what each one needs next. Open one and you see the verdict, the journey, and every party it leans on. The network board: every journey laid against every party that holds it up. The lab, the insurer, the pharmacy, the cab, the hotel. Approvals, where a re-plan that touches treatment timing waits for a doctor to agree. Report an issue, for when a machine goes down or a vendor fails. And releases: the lab desk marking a report released, which is what unblocks a family's journey.",
  },
  {
    //: 47.5-54.6 is the Onboarding section showing "Nobody to take on yet" — an
    //: empty state that was true for ten minutes in October and is wrong now.
    //: Chapter 1 shows the real thing, so this is cut rather than contradicted.
    id: "d-walk2", kind: "browser", seconds: 39.4, file: "11-control-centre-walkthrough.mp4", in: 54.6,
    vo: "Reports: every lab and imaging report, whether it has been released, and how long each queue usually takes. Plan boards, by pathway. Entering records by hand, or importing them from another system. The cohort view: who needs a person, and what the desk has queued. The directory of every lab, pharmacy, distributor, cab firm, hotel and insurer a journey runs through, and how each one answers. The registries. Configuration: the rules, the languages, and what is switched on. And the audit log. Every decision and every change, hash chained, so that it cannot be quietly edited later.",
  },

  { id: "f-chapter", kind: "card", seconds: 3, card: { chapter: "3", heading: "Three families, one morning" }, vo: "" },
  { id: "f1", kind: "browser", seconds: 17, file: "09-live-demo-control-centre.mp4", in: 2,
    vo: "Three families are loaded back to the start of their stories. Anita in Gaya, Ravi in Patna, and Meena in Varanasi. All three are real records in the deployed database, and everything that follows happens live, at the speed the system actually runs." },
  { id: "f2", kind: "browser", seconds: 14, file: "09-live-demo-control-centre.mp4", in: 20,
    vo: "The network board. Every journey, laid against every party that holds it up. Green is ready. Amber means asked, but not yet answered. A dash means that party has not been asked at all." },
  { id: "f3", kind: "browser", seconds: 36, file: "09-live-demo-control-centre.mp4", in: 36,
    vo: "Meena is on dialysis. Her verdict is Wait, because the visit depends on something that is not settled yet. Saathi asks the cab firm, and the cab firm answers by itself. Nothing here was typed by a person. Watch the verdict: when the last party answers, Wait becomes Go, and only then does a date appear. The date is a consequence of readiness. It is never a guess, and it is never shown early." },
  { id: "f4", kind: "browser", seconds: 19, file: "09-live-demo-control-centre.mp4", in: 91,
    vo: "Ravi's cab firm says it cannot do the journey. The journey stops. No date is promised, because there is nothing to promise. The system does not quietly substitute another vendor, and it does not pretend the problem away. It waits for a person." },
  { id: "f5", kind: "browser", seconds: 30, file: "09-live-demo-control-centre.mp4", in: 110,
    vo: "A navigator presses Book another. A second firm, Ola, is asked, and the journey now waits on Ola. This is the important part. The system did not choose that vendor. A person did, from the directory, and the ledger recorded who asked, which firm, and when. Saathi puts the question; a human makes the call." },
  { id: "f6", kind: "browser", seconds: 15, file: "09-live-demo-control-centre.mp4", in: 170,
    vo: "Ola says ready. Everything else was ready already, so Ravi goes straight back to Go, with a date. One vendor failing cost him a few minutes, rather than a wasted six hundred kilometre journey." },
  { id: "f7", kind: "browser", seconds: 12, file: "09-live-demo-control-centre.mp4", in: 186,
    vo: "Now Anita. Her report is still sitting with the lab, which is the one thing her whole journey waits on. The lab desk marks it released. One click, by one person." },
  { id: "f8", kind: "browser", seconds: 27, file: "09-live-demo-control-centre.mp4", in: 198,
    vo: "That one fact unblocks the chain. Saathi now asks each remaining party in turn, the way a navigator would, except in seconds rather than over a morning of phone calls. The insurer, the pharmacy, the ride, the stay. And the family's phone updates by itself. Nobody sends them anything." },
  { id: "f9", kind: "browser", seconds: 19, file: "09-live-demo-control-centre.mp4", in: 266,
    vo: "The chain is complete. Anita is on Go, and all three families are ready to travel. Two of them began this morning blocked, one by a lab and one by a cab firm, and neither family had to telephone anybody to find that out." },

  { id: "i-chapter", kind: "card", seconds: 3, card: { chapter: "4", heading: "The vendor's own screen" }, vo: "" },
  //: Same again: a loading screen and a burned-in "The vendor's own screen"
  //: title, both already covered by the chapter card before it.
  { id: "i-partner", kind: "browser", seconds: 20.8, file: "12-partner-app.webm", in: 10.5,
    vo: "Everyone a journey leans on gets a screen of their own, and this is the cab firm's. Ola sees only the jobs its own organisation was asked to do: a first name, a district, and a day when the plan promises one. The phone number is missing on purpose — this family has not agreed to share it." },

  { id: "j-chapter", kind: "card", seconds: 3, card: { chapter: "5", heading: "The family's phone" }, vo: "" },
  { id: "j1", kind: "phone", seconds: 5.5, file: "01-sign-in-email-otp.mp4", in: 0,
    panel: { heading: "Signing in", lines: ["An email address, not a password", "A code arrives; nothing to remember"] },
    vo: "Now the other side of the same system: the phone in the family's hand." },
  //: 5.5-15 is the emulator's own Gboard contacts prompt, and 30-44 is a
  //: second attempt after the first code lapsed. Neither is the product.
  { id: "j2", kind: "phone", seconds: 18, file: "01-sign-in-email-otp.mp4", in: 15,
    panel: { heading: "Signing in", lines: ["An email address, not a password", "A code arrives; nothing to remember"] },
    vo: "The family has an Android app, and they sign in with the email address the hospital already holds. A code arrives. There is no password to remember, which matters when the person holding the phone is a carer who may not use apps often." },
  { id: "j3", kind: "phone", seconds: 24, file: "01-sign-in-email-otp.mp4", in: 44,
    panel: { heading: "Signing in", lines: ["The code is typed by the family", "Then Saathi works out the plan"] },
    vo: "The code is typed in, and Saathi works out their plan. Everything from here is the real deployed service, on a real phone, in Hindi. And note what this app does not contain. There is no clinical information in it anywhere. It carries travel and appointments only, and it says so on the sign-in screen." },
  { id: "k-waiting", kind: "phone", seconds: 15.6, file: "02-anita-before-the-report.mp4", in: 18,
    panel: { heading: "Before the report", lines: ["रुकिए — Wait", "No date, because there is no date yet", "One of ten steps done"] },
    vo: "Anita, before her report is ready. Rukiye: wait. Stay at home, and you will be told when the report is ready. The plan tab shows one of ten steps done, and what each one waits on." },

  { id: "r-chapter", kind: "card", seconds: 3, card: { chapter: "6", heading: "What the family can manage" }, vo: "" },
  {
    //: The one chapter recorded against a *local* stack rather than the
    //: deployed one, because the deployed service does not have this yet —
    //: `/budget` is a 404 there. The closing card says so. A film that implied
    //: otherwise would be the single dishonest thing in it.
    id: "r-budget", kind: "browser", seconds: 64.1,
    file: "17-what-the-family-can-manage.webm", in: 0,
    vo: "One thing the planner cannot work out on its own. It knows this journey needs a ride and a bed. It does not know whether this household can pay for the ones it picked, and guessing is how a family ends up with a confirmed app cab they quietly cannot afford. So Saathi asks. Three real organisations from the directory, one of each kind: a railway patient quota, a shared jeep, a taxi. This family's ration card is AAY, so the concession is offered first and marked — and not ticked, because a default nobody changed is not an answer. There is no price here. Saathi has none to give. Last on every list, and deliberately not one of the things to buy: we cannot manage any of this. That one rebooks nothing. It raises a person, because the answer to a family with no fare is a scheme and a social worker. The family chooses, a navigator agrees it is what they meant, and only then does the ride move from a taxi to the railway desk.",
  },

  { id: "l-chapter", kind: "card", seconds: 3, card: { chapter: "7", heading: "A voice, because reading is not universal" }, vo: "" },
  { id: "l-meena", kind: "phone", seconds: 48, file: "13-meena-phone-sarvam.mp4", in: 0,
    panel: { heading: "Meena · Varanasi", lines: ["आइए — Come, with a date", "बोलिए reads it aloud", "The voice is Sarvam"] },
    //: Starts at the clip's first frame, because that is where the tap is.
    //: Measured at a tenth of a second: the button reads "बोलिए" on frame one
    //: and "पढ़ रहे हैं…" from 0.1s, holding past 26s. Beginning this segment
    //: three seconds in — as it first did — cut the tap out entirely and left
    //: a voice arriving with nothing on screen to have caused it.
    hindi: { at: 0.5, text: "8 नवंबर को डायलिसिस यूनिट रिसेप्शन जाएँ। अस्पताल फ़ाइल, रोगी आईडी कार्ड, ABHA नंबर या आयुष्मान कार्ड, पिछले अपॉइंटमेंट स्लिप, डायलिसिस कार्ड, भुगतान या योजना दस्तावेज़ साथ लाएँ।" },
    vo: "That is Sarvam, reading Meena's own plan back to her in Hindi. It was chosen for one reason that is not marketing: almost no phone ships an Odia voice, so this button used to do nothing at all, silently, for an Odia family. The plan tab shows four of seven steps done. The messages tab holds the whole conversation, also in Hindi, and every line in it has a source." },

  { id: "m-chapter", kind: "card", seconds: 3, card: { chapter: "8", heading: "When a vendor fails" }, vo: "" },
  { id: "m-ravi", kind: "phone", seconds: 46, file: "14-ravi-phone-vendor-failure.mp4", in: 0,
    //: The button holds "बोलिए" until 0.6s and flips there, so the voice
    //: starts on the frame the screen changes. This is the one clip that
    //: caught the tap itself.
    hindi: { at: 0.6, text: "अभी घर पर रहें। जब यात्रा का समय तय हो जाएगा, आपको सूचित किया जाएगा।" },
    panel: { heading: "Ravi · Patna", lines: ["रुकिए — Wait", "गाड़ी · Ola, asked at 08:44", "600 किलोमीटर दूर"] },
    vo: "Ravi, on the same morning. His verdict is Wait, and the app says exactly what it is waiting on: the cab. Ola, asked at eight forty four. Six hundred kilometres away. Look at what is not on this screen. There is no date. The app will not promise a day it does not have, even though a date would feel more reassuring, because a family that travels on a date the system invented has lost a day's wages and a day's travel for nothing. The plan tab shows seven of ten steps done, and the cab is step seven. The family is told the truth, told who is being chased, and asked to do nothing." },

  { id: "n-chapter", kind: "card", seconds: 3, card: { chapter: "9", heading: "The moment it changes" }, vo: "" },
  { id: "n-flip", kind: "phone", seconds: 30, file: "10-live-demo-anita-phone-hindi.mp4", in: 104,
    panel: { heading: "Nobody touches the phone", lines: ["The lab desk releases the report", "रुकिए becomes आइए", "A date appears with it"] },
    vo: "This is Anita's phone while the control centre releases her report. Nobody touches the phone. Nobody sends a message. The lab desk clicks once, four hundred kilometres away, and the chain fills in behind it. Wait becomes Come. A date appears, Sunday the eighth of November. And with the date comes the list of papers to carry, because a journey that arrives without the right papers is still a wasted journey." },
  { id: "o-come", kind: "phone", seconds: 50, file: "15-anita-phone-go.mp4", in: 0,
    hindi: { at: 0.5, text: "8 नवंबर को यात्रा करें। पहले पंजीकरण काउंटर पर जाएँ। हॉस्पिटल फ़ाइल, रोगी पहचान कार्ड, ABHA नंबर या आयुष्मान कार्ड, पूर्व अपॉइंटमेंट स्लिप्स, सभी रिपोर्ट स्लिप्स लाएँ।" },
    panel: { heading: "Anita · Gaya", lines: ["आइए — Come", "यात्रा · रविवार 8 नवंबर", "Nine of ten steps done"] },
    vo: "Anita's, in her own language, with the date and the papers to carry. That list is not generic advice: it is assembled from this hospital's own rules and this family's own scheme, which is why it names Ayushman and not something else. Nine of ten steps are done; the last one is the visit itself. Nothing on this screen was typed by a person. The date came from the chain clearing, the list from the hospital's rules, and the language from the family's own choice." },

  {
    id: "p-invariants", kind: "card", seconds: 20,
    card: { heading: "What never enters", sub: "Four of the rules this is built on", kicker: "No report content · the model never decides · nothing without a source · the ledger grows only on change" },
    vo: "No report content is ever stored. The model never decides anything; it only puts a decision the planner made into the family's own language. Nothing reaches a family without a source. And the ledger only grows when a fact actually changes.",
  },
  {
    id: "q-close", kind: "card", seconds: 17,
    card: { heading: "EKYATRA Saathi", sub: "The console reflects the world. It never causes it.", kicker: "Chapter 6 on a local build · everything else on the deployed service" },
    vo: "Everything here runs against the real service, with real records and a real phone. Chapter six runs on a local build, because that part is not deployed yet; the rest is. The console reflects the world. It never causes it.",
  },
];

export const TOTAL = PLAN.reduce((n, s) => n + s.seconds, 0);
