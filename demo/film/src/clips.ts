// Written by demo/stage-clips.mjs. Which clips exist, so the composition
// can drop a section whose clip was never shot — picture and narration
// together, rather than leaving a voice over a black screen.
export type Clip = { file: string; seconds: number };
export const CLIPS: Record<string, Clip> = {
  "01-hospital-leave": {
    "file": "01-hospital-leave.mp4",
    "seconds": 31.17
  },
  "02-appointments-untouched": {
    "file": "02-appointments-untouched.mp4",
    "seconds": 9.97
  },
  "03-board": {
    "file": "03-board.mp4",
    "seconds": 16.03
  },
  "04-board-opened": {
    "file": "04-board-opened.mp4",
    "seconds": 17.97
  },
  "05-question-arrives": {
    "file": "05-question-arrives.mp4",
    "seconds": 31.8
  },
  "06-she-answers": {
    "file": "06-she-answers.mp4",
    "seconds": 38.23
  },
  "07-a-person-agrees": {
    "file": "07-a-person-agrees.mp4",
    "seconds": 22.77
  },
  "08-planner-search": {
    "file": "08-planner-search.mp4",
    "seconds": 20.97
  },
  "09-saathi-proposes": {
    "file": "09-saathi-proposes.mp4",
    "seconds": 31.3
  },
  "10-whose-number": {
    "file": "10-whose-number.mp4",
    "seconds": 34.88
  },
  "11-navigator-approves": {
    "file": "11-navigator-approves.mp4",
    "seconds": 21.6
  },
  "12-written-back": {
    "file": "12-written-back.mp4",
    "seconds": 20
  },
  "13-will-not-pretend": {
    "file": "13-will-not-pretend.mp4",
    "seconds": 11.87
  },
  "14-read-aloud": {
    "file": "14-read-aloud.mp4",
    "seconds": 49.75
  },
  "15-the-journey": {
    "file": "15-the-journey.mp4",
    "seconds": 60.53
  },
  "16-a-second-family": {
    "file": "16-a-second-family.mp4",
    "seconds": 42.09
  },
  "17-what-a-partner-sees": {
    "file": "17-what-a-partner-sees.mp4",
    "seconds": 13.93
  },
  "18-without-a-smartphone": {
    "file": "18-without-a-smartphone.mp4",
    "seconds": 13.47
  },
  "19-what-it-is-worth": {
    "file": "19-what-it-is-worth.mp4",
    "seconds": 13
  },
  "20-the-navigators-day": {
    "file": "20-the-navigators-day.mp4",
    "seconds": 18.33
  },
  "21-the-network": {
    "file": "21-the-network.mp4",
    "seconds": 27.8
  },
  "22-who-is-registered": {
    "file": "22-who-is-registered.mp4",
    "seconds": 28.37
  },
  "23-what-can-break": {
    "file": "23-what-can-break.mp4",
    "seconds": 25.87
  },
  "24-what-it-was-built-from": {
    "file": "24-what-it-was-built-from.mp4",
    "seconds": 69.13
  },
  "25-the-ledger": {
    "file": "25-the-ledger.mp4",
    "seconds": 23.6
  },
  "26-one-family-whole": {
    "file": "26-one-family-whole.mp4",
    "seconds": 25.27
  },
  "27-her-own-books": {
    "file": "27-her-own-books.mp4",
    "seconds": 43
  },
  "28-the-map": {
    "file": "28-the-map.mp4",
    "seconds": 58.79
  },
  "29-five-languages": {
    "file": "29-five-languages.mp4",
    "seconds": 34.98
  },
  "30-how-a-partner-joins": {
    "file": "30-how-a-partner-joins.mp4",
    "seconds": 25.43
  },
  "31-the-plan-boards": {
    "file": "31-the-plan-boards.mp4",
    "seconds": 22.57
  },
  "32-what-it-adds-up-to": {
    "file": "32-what-it-adds-up-to.mp4",
    "seconds": 24.73
  },
  "33-a-vendor-applies": {
    "file": "33-a-vendor-applies.mp4",
    "seconds": 25
  },
  "34-in-the-directory-switched-off": {
    "file": "34-in-the-directory-switched-off.mp4",
    "seconds": 21.93
  },
  "35-the-review-queue": {
    "file": "35-the-review-queue.mp4",
    "seconds": 20.47
  },
  "36-letting-them-in": {
    "file": "36-letting-them-in.mp4",
    "seconds": 38.33
  },
  "37-no-consent-is-not-no-tests": {
    "file": "37-no-consent-is-not-no-tests.mp4",
    "seconds": 24.17
  },
  "38-its-own-consent": {
    "file": "38-its-own-consent.mp4",
    "seconds": 26.6
  },
  "39-what-was-already-done": {
    "file": "39-what-was-already-done.mp4",
    "seconds": 50.37
  },
  "40-it-will-not-hold-a-finding": {
    "file": "40-it-will-not-hold-a-finding.mp4",
    "seconds": 33.57
  }
};
