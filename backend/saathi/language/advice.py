"""Telling a family to leave later, because the clinic is behind.

This is the only message in the system that changes what a family does *today*
rather than on a planned day, and it is the one with the clearest value: three
hours not spent standing in a corridor, and an auto fare not paid twice.

**Why it is a message and not a re-plan.** The visit is going ahead. Nothing
is cancelled, no slot is lost, no date moves. Treating a late clinic as a
disruption would cancel and re-plan a visit that is simply running behind,
which is worse for the family than the delay. So this says one thing — leave
later — and touches no plan.

**Why there is a floor on it.** `WORTH_SAYING` exists because a message about
eight minutes teaches a family to ignore messages, and the message they then
ignore is the one that mattered. A clinic running normally is not news.

**Why the new time is computed, never estimated.** The hour given is their own
appointment time plus the delay the clinic's own timestamps show, rounded down
to five minutes so it reads like something a person would say. If either
number is missing the message is not sent at all — "leave a bit later" is not
advice, it is an invitation to guess.

**What it never says.** Why the clinic is behind. We do not know, the
timestamps do not say, and a reason invented here would be a claim about a
hospital's working day that nobody made.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..domain.enums import Language
from .questions import written_day

#: How far behind the clinic must be before a family is told. Below this, the
#: clinic is running normally and the message costs more attention than it
#: saves. Matches the connector's own threshold.
WORTH_SAYING = timedelta(minutes=45)

#: Round the suggested time down to this, so the advice reads like a person
#: saying it. "Leave at 1:30" is advice; "leave at 1:37" is a calculation
#: somebody has to think about.
_ROUND_TO = timedelta(minutes=5)

#: `{was}` is when they were going to leave, `{now}` when they should instead,
#: `{hours}` how far behind the clinic is. No reason is given for the delay,
#: because none is known.
_LATER: dict[Language, str] = {
    Language.ENGLISH: (
        "The clinic is running about {hours} behind today. Your visit is still on. "
        "If you have not left yet, leave at {now} instead of {was}."
    ),
    Language.HINDI: (
        "Aaj clinic mein takreeban {hours} ki der chal rahi hai. Aapki visit ho gi. "
        "Agar aap abhi tak nikle nahi hain, to {was} ke bajaye {now} par niklein."
    ),
    Language.BENGALI: (
        "আজ ক্লিনিকে প্রায় {hours} দেরি চলছে। আপনার দেখা হবেই। "
        "এখনো না বেরিয়ে থাকলে {was} এর বদলে {now} টায় বেরোন।"
    ),
    Language.ODIA: (
        "ଆଜି କ୍ଲିନିକରେ ପ୍ରାୟ {hours} ଡେରି ଚାଲିଛି। ଆପଣଙ୍କ ଭେଟ ହେବ। "
        "ଏପର୍ଯ୍ୟନ୍ତ ବାହାରି ନଥିଲେ {was} ବଦଳରେ {now} ରେ ବାହାରନ୍ତୁ।"
    ),
    Language.TAMIL: (
        "இன்று கிளினிக்கில் சுமார் {hours} தாமதம். உங்கள் சந்திப்பு நடக்கும். "
        "இன்னும் புறப்படவில்லை என்றால், {was} மணிக்கு பதிலாக {now} மணிக்கு புறப்படுங்கள்."
    ),
}

#: "about two hours", "about 90 minutes" — in the family's own words, and
#: deliberately coarse. The clinic's delay is not a figure anybody should plan
#: to the minute, and stating it to the minute would imply it is.
_HOURS: dict[Language, str] = {
    Language.ENGLISH: "{n} hours",
    Language.HINDI: "{n} ghante",
    Language.BENGALI: "{n} ঘণ্টা",
    Language.ODIA: "{n} ଘଣ୍ଟା",
    Language.TAMIL: "{n} மணி நேரம்",
}

_MINUTES: dict[Language, str] = {
    Language.ENGLISH: "{n} minutes",
    Language.HINDI: "{n} minute",
    Language.BENGALI: "{n} মিনিট",
    Language.ODIA: "{n} ମିନିଟ୍",
    Language.TAMIL: "{n} நிமிடம்",
}


def _pick(table: dict[Language, str], language: Language) -> str:
    return table.get(language) or table[Language.ENGLISH]


def _clock(moment: datetime, language: Language) -> str:
    """A time of day, in a form the guard can read and a family can act on.

    24-hour, because "1:30" without am/pm has sent people to a clinic twelve
    hours out, and the languages here do not all carry an unambiguous short
    form for the distinction.
    """
    del language  # one format for everyone, on purpose
    return f"{moment.hour:02d}:{moment.minute:02d}"


def how_far_behind(delay: timedelta, language: Language) -> str:
    """The delay in round terms: "2 hours", "90 minutes"."""
    minutes = int(delay.total_seconds() // 60)
    if minutes >= 90:
        hours = round(minutes / 60)
        return _pick(_HOURS, language).format(n=hours)
    return _pick(_MINUTES, language).format(n=minutes)


def leave_later(
    *,
    language: Language,
    leaving_at: datetime,
    delay: timedelta,
) -> tuple[str, datetime] | None:
    """Advice to set out later, and the time it names. None when there is none.

    `None` covers every case where there is nothing worth saying: a delay below
    the floor, or one so large that it is no longer a delay but a different
    day's problem and belongs with a person. Returning a message for those
    would be worse than silence.
    """
    if delay < WORTH_SAYING:
        return None
    # Beyond this the clinic is not "running late", something has gone wrong,
    # and a family should hear from a person rather than from a template.
    if delay > timedelta(hours=6):
        return None

    rounded = timedelta(
        seconds=(int(delay.total_seconds()) // int(_ROUND_TO.total_seconds()))
        * int(_ROUND_TO.total_seconds())
    )
    now_leave = leaving_at + rounded
    if now_leave.date() != leaving_at.date():
        # Leaving tomorrow is not advice about today.
        return None

    body = _pick(_LATER, language).format(
        hours=how_far_behind(delay, language),
        was=_clock(leaving_at, language),
        now=_clock(now_leave, language),
    )
    return body, now_leave


#: For a family already on their way. "Leave later" is useless to somebody on
#: a train, and worse than useless — it reads as a system that does not know
#: where they are. What helps them is knowing not to panic when they arrive to
#: a full corridor, and roughly how long it will be.
_ALREADY_TRAVELLING: dict[Language, str] = {
    Language.ENGLISH: (
        "The clinic is running about {hours} behind today. Your visit is still on. "
        "You may wait about that long after you arrive — you have not missed anything."
    ),
    Language.HINDI: (
        "Aaj clinic mein takreeban {hours} ki der chal rahi hai. Aapki visit ho gi. "
        "Pahunchne ke baad itna intezaar karna pad sakta hai — aapka kuch chhuta nahi hai."
    ),
    Language.BENGALI: (
        "আজ ক্লিনিকে প্রায় {hours} দেরি চলছে। আপনার দেখা হবেই। "
        "পৌঁছে অতটা অপেক্ষা করতে হতে পারে — আপনার কিছু বাদ যায়নি।"
    ),
    Language.ODIA: (
        "ଆଜି କ୍ଲିନିକରେ ପ୍ରାୟ {hours} ଡେରି ଚାଲିଛି। ଆପଣଙ୍କ ଭେଟ ହେବ। "
        "ପହଞ୍ଚିବା ପରେ ସେତିକି ଅପେକ୍ଷା କରିବାକୁ ପଡ଼ିପାରେ — ଆପଣଙ୍କର କିଛି ଛାଡ଼ି ଯାଇନାହିଁ।"
    ),
    Language.TAMIL: (
        "இன்று கிளினிக்கில் சுமார் {hours} தாமதம். உங்கள் சந்திப்பு நடக்கும். "
        "வந்த பிறகு அவ்வளவு நேரம் காத்திருக்க நேரலாம் — நீங்கள் எதையும் தவறவிடவில்லை."
    ),
}


def already_travelling(*, language: Language, delay: timedelta) -> str | None:
    """What to tell a family who has already set out.

    Most of this project's families live six to twelve hours away, so by the
    time a morning clinic is visibly behind they are on a bus. Telling them to
    leave later would be absurd; telling them nothing leaves them to discover
    a full corridor and assume they have missed their turn.
    """
    if delay < WORTH_SAYING or delay > timedelta(hours=6):
        return None
    return _pick(_ALREADY_TRAVELLING, language).format(hours=how_far_behind(delay, language))


def hours_saved(delay: timedelta) -> str:
    """What the family is spared, for the Console. Never shown to the family.

    Saathi tells a family what to do, not how clever it was being.
    """
    minutes = int(delay.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m not spent waiting"


__all__ = [
    "WORTH_SAYING",
    "already_travelling",
    "how_far_behind",
    "hours_saved",
    "leave_later",
    "written_day",
]
