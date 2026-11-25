"""The questions Saathi asks a family, and the reason none of them is generated.

Everything else in `language/` either renders a decision that already exists
(`rendering.py`) or states a fixed fact (`holding.py`, `guide_messages.py`,
`process_answers.py`). This module is the first thing that *asks*, which is a
different risk and worth being explicit about.

**Why these are templates and not a model call.** A generated question can
introduce a premise. "Since the doctor will be away all week, when can you
come?" is a fluent sentence containing a claim nobody made, and a family
cannot tell which half of it came from a record. The parts of a question that
vary — what changed, and which day it changed on — are structured values the
caller already holds, so they go in slots. There is nothing left for a model
to contribute except the risk.

**Why the question says why.** A bare "how many people will travel?" arriving
on a phone with no reason attached is a worse message, not a safer one: the
family's next move is to call someone and ask what happened. So each question
opens with the reason it is being asked, drawn from a closed vocabulary of
reasons (`AskReason`) with the date filled in from the record. That is the
whole of what Saathi volunteers.

**What it never does.** It never states a date that was not handed to it, never
names a clinical fact, and never says what will happen next — because at the
moment a question is asked, nothing has been decided. `guard.check_question`
enforces the first two against the composed text, so a bad template is caught
by the same machinery as a bad model.

The model's job is the other direction: reading the *answer*. That is
`live/actors.py:extract_request`, and it is a reading, never a decision.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from enum import StrEnum

from ..domain.enums import Language


class AskReason(StrEnum):
    """Why Saathi is asking. A closed list, because it fills a sentence.

    Each of these is something a hospital system actually published, not an
    inference: a provider marked unavailable, an order still open, arrival
    timestamps running behind, a slot moved. Anything that does not fit one of
    these is not asked about by Saathi — a person is told instead.
    """

    #: A provider is marked away on the day the family was coming.
    DOCTOR_AWAY = "doctor_away"
    #: An order or report the visit depends on is not finished.
    REPORT_PENDING = "report_pending"
    #: The clinic is behind today, derived from arrival times.
    CLINIC_BEHIND = "clinic_behind"
    #: The hospital moved or cancelled the slot.
    SLOT_CHANGED = "slot_changed"


class AskTopic(StrEnum):
    """What a question is trying to find out.

    One topic, one sentence. A question may carry several, and the sentences
    are joined — which keeps this table at five languages by four topics
    rather than five by every combination of them.
    """

    #: Which days they can and cannot travel.
    TIMING = "timing"
    #: How many people are coming.
    COMPANIONS = "companions"
    #: What the journey costs them, in their own figure.
    COST = "cost"
    #: Whether travel they have already booked can be changed.
    BOOKING = "booking"


#: Which `TravelFacts` / `RequestConstraint` fields each topic is trying to
#: fill. The dialogue layer reads this to decide whether an answer answered
#: the question, so a topic with no fields would be a question that can never
#: be satisfied.
TOPIC_FILLS: dict[AskTopic, tuple[str, ...]] = {
    AskTopic.TIMING: ("not_before", "not_after", "excluded_dates"),
    AskTopic.COMPANIONS: ("companions",),
    AskTopic.COST: ("stated_cost_inr",),
    AskTopic.BOOKING: ("refundable",),
}

#: The reason, with `{day}` filled from the record. Deliberately states what
#: happened and not what it means — "the doctor is not available" is a fact a
#: hospital published; "your treatment will be delayed" would be a claim.
_LEAD: dict[AskReason, dict[Language, str]] = {
    AskReason.DOCTOR_AWAY: {
        Language.ENGLISH: "The doctor is not available on {day}.",
        Language.HINDI: "{day} ko doctor uplabdh nahi hain.",
        Language.BENGALI: "{day} তারিখে ডাক্তার উপস্থিত থাকবেন না।",
        Language.ODIA: "{day} ତାରିଖରେ ଡାକ୍ତର ଉପଲବ୍ଧ ନାହାନ୍ତି।",
        Language.TAMIL: "{day} அன்று மருத்துவர் வர மாட்டார்.",
    },
    AskReason.REPORT_PENDING: {
        Language.ENGLISH: "A report your visit on {day} needs is not ready yet.",
        Language.HINDI: "{day} ki visit ke liye zaroori ek report abhi taiyar nahi hai.",
        Language.BENGALI: "{day} তারিখের দেখার জন্য দরকারি একটি রিপোর্ট এখনো তৈরি হয়নি।",
        Language.ODIA: "{day} ତାରିଖର ଭେଟ ପାଇଁ ଦରକାରୀ ଏକ ରିପୋର୍ଟ ଏଯାଏଁ ପ୍ରସ୍ତୁତ ନାହିଁ।",
        Language.TAMIL: "{day} சந்திப்புக்கு தேவையான ஒரு அறிக்கை இன்னும் தயாராகவில்லை.",
    },
    AskReason.CLINIC_BEHIND: {
        Language.ENGLISH: "The clinic is running behind on {day}.",
        Language.HINDI: "{day} ko clinic mein der chal rahi hai.",
        Language.BENGALI: "{day} তারিখে ক্লিনিকে দেরি হচ্ছে।",
        Language.ODIA: "{day} ତାରିଖରେ କ୍ଲିନିକରେ ଦେରି ହେଉଛି।",
        Language.TAMIL: "{day} அன்று கிளினிக்கில் தாமதம் உள்ளது.",
    },
    AskReason.SLOT_CHANGED: {
        Language.ENGLISH: "The hospital has changed the time of your visit on {day}.",
        Language.HINDI: "Aspataal ne {day} ki aapki visit ka samay badal diya hai.",
        Language.BENGALI: "হাসপাতাল {day} তারিখের আপনার দেখার সময় বদলেছে।",
        Language.ODIA: "ଡାକ୍ତରଖାନା {day} ତାରିଖର ଆପଣଙ୍କ ଭେଟର ସମୟ ବଦଳାଇଛି।",
        Language.TAMIL: "{day} அன்றைய உங்கள் சந்திப்பு நேரத்தை மருத்துவமனை மாற்றியுள்ளது.",
    },
}

#: One sentence per topic. Note what is absent from all of them: any figure.
#: `COST` asks and offers nothing, because there is no fare source behind this
#: system and a suggested amount would be an invention — see
#: `domain/requests.py:TravelFacts`.
_TOPIC: dict[AskTopic, dict[Language, str]] = {
    AskTopic.TIMING: {
        Language.ENGLISH: "Which days can you travel, and which days can you not?",
        Language.HINDI: "Aap kin dino aa sakte hain, aur kin dino nahi?",
        Language.BENGALI: "আপনি কোন কোন দিন আসতে পারবেন, আর কোন দিন পারবেন না?",
        Language.ODIA: "ଆପଣ କେଉଁ କେଉଁ ଦିନ ଆସିପାରିବେ, ଆଉ କେଉଁ ଦିନ ପାରିବେ ନାହିଁ?",
        Language.TAMIL: "நீங்கள் எந்த நாட்களில் வர முடியும், எந்த நாட்களில் முடியாது?",
    },
    AskTopic.COMPANIONS: {
        Language.ENGLISH: "How many people will travel?",
        Language.HINDI: "Kitne log aa rahe hain?",
        Language.BENGALI: "কতজন আসছেন?",
        Language.ODIA: "କେତେ ଜଣ ଆସୁଛନ୍ତି?",
        Language.TAMIL: "எத்தனை பேர் வருகிறீர்கள்?",
    },
    AskTopic.COST: {
        Language.ENGLISH: "What would the journey cost you?",
        Language.HINDI: "Aane-jaane mein aapka kitna kharch hoga?",
        Language.BENGALI: "যাওয়া-আসায় আপনার কত খরচ হবে?",
        Language.ODIA: "ଯାଇବା-ଆସିବାରେ ଆପଣଙ୍କର କେତେ ଖର୍ଚ୍ଚ ହେବ?",
        Language.TAMIL: "போய் வர உங்களுக்கு எவ்வளவு செலவாகும்?",
    },
    AskTopic.BOOKING: {
        Language.ENGLISH: "Have you already booked travel, and can it be changed?",
        Language.HINDI: "Kya aapne ticket le liya hai, aur kya wo badla ja sakta hai?",
        Language.BENGALI: "আপনি কি টিকিট কেটে ফেলেছেন, আর তা বদলানো যাবে?",
        Language.ODIA: "ଆପଣ ଟିକେଟ୍ କାଟି ସାରିଛନ୍ତି କି, ଆଉ ତାହା ବଦଳାଯାଇ ପାରିବ କି?",
        Language.TAMIL: "நீங்கள் டிக்கெட் எடுத்துவிட்டீர்களா, அதை மாற்ற முடியுமா?",
    },
}

#: Said after the questions, so a family is not left wondering whether their
#: reply matters. It promises a person, which is true, and not a date, which
#: is not known.
_CLOSE: dict[Language, str] = {
    Language.ENGLISH: "Tell us and we will work out the new day. Please do not travel yet.",
    Language.HINDI: "Bata dijiye, hum naya din nikaal lenge. Abhi yatra na karein.",
    Language.BENGALI: "জানালে আমরা নতুন দিন ঠিক করে নেব। এখনই যাত্রা করবেন না।",
    Language.ODIA: "ଜଣାଇଦେଲେ ଆମେ ନୂଆ ଦିନ ଠିକ୍ କରିନେବୁ। ଏବେ ଯାତ୍ରା କରନ୍ତୁ ନାହିଁ।",
    Language.TAMIL: (
        "சொன்னால் நாங்கள் புதிய நாளை ஏற்பாடு செய்கிறோம். இப்போது பயணம் செய்ய வேண்டாம்."
    ),
}

#: Month names, in the family's own script. `rendering.py` rule 6 pins exactly
#: this for plan messages — "3 October", "3 अक्टूबर", "৩ অক্টোবর" — so a family
#: sees one date format from this system however the sentence was produced.
#:
#: Every name here must also be one `guard.MONTH_NAMES` can read, or the guard
#: would be unable to verify a date this module wrote. That is not left to
#: inspection: `tests/test_questions.py` round-trips all twelve months in all
#: five languages through `guard.stated_dates`.
_MONTHS: dict[Language, tuple[str, ...]] = {
    Language.ENGLISH: (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
    Language.HINDI: (
        "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
        "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
    ),
    Language.BENGALI: (
        "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
        "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
    ),
    Language.ODIA: (
        "ଜାନୁଆରୀ", "ଫେବୃଆରୀ", "ମାର୍ଚ୍ଚ", "ଅପ୍ରେଲ", "ମଇ", "ଜୁନ",
        "ଜୁଲାଇ", "ଅଗଷ୍ଟ", "ସେପ୍ଟେମ୍ବର", "ଅକ୍ଟୋବର", "ନଭେମ୍ବର", "ଡିସେମ୍ବର",
    ),
    Language.TAMIL: (
        "ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்",
        "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்",
    ),
}


def _language(table: dict[Language, str], language: Language) -> str:
    """The family's own wording, or English — never a blank."""
    return table.get(language) or table[Language.ENGLISH]


def written_day(day: date, language: Language) -> str:
    """A date as a family in this language should read it.

    ASCII digits deliberately, in every script. `guard._DIGIT_TABLE`
    normalises Devanagari, Bengali, Odia and Tamil numerals so either would be
    readable, but a number a family may need to repeat to a bus conductor or
    type into a phone is safer in the digits every keypad has.
    """
    months = _MONTHS.get(language) or _MONTHS[Language.ENGLISH]
    return f"{day.day} {months[day.month - 1]}"


def compose_question(
    *,
    reason: AskReason,
    topics: Sequence[AskTopic],
    language: Language,
    on_day: date,
) -> str:
    """The text of one question, in the family's language.

    `on_day` is the day the *disruption* is about, taken from the record. It is
    the only date this may contain, and the caller passes the same value to
    `guard.check_question` as `dates_given`, so an accidental second date in a
    template is caught rather than sent.

    Topics are rendered in the order of `AskTopic` rather than the order the
    caller listed them, so the same set of questions always reads the same way
    to a family who gets asked twice.
    """
    ordered = [topic for topic in AskTopic if topic in set(topics)]
    if not ordered:
        raise ValueError("a question with no topic would ask a family nothing")

    day = written_day(on_day, language)
    parts = [_language(_LEAD[reason], language).format(day=day)]
    parts.extend(_language(_TOPIC[topic], language) for topic in ordered)
    parts.append(_language(_CLOSE, language))
    return " ".join(parts)


def fills_for(topics: Iterable[AskTopic]) -> tuple[str, ...]:
    """Every field the given topics are trying to fill, de-duplicated."""
    seen: dict[str, None] = {}
    for topic in topics:
        for field in TOPIC_FILLS[topic]:
            seen[field] = None
    return tuple(seen)


__all__ = [
    "TOPIC_FILLS",
    "AskReason",
    "AskTopic",
    "compose_question",
    "fills_for",
    "written_day",
]
