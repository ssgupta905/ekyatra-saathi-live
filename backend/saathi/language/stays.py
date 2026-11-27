"""What a family is told about a room, and about who pays for a change.

Templated per language and never generated, for the same reason the questions
are (`language/questions.py`): a model that writes the sentence can invent a
premise, and a family cannot tell which half of a fluent sentence came from a
record. Every figure here is rendered by the caller from a partner's own quote.

The only date in any of these is the check-in day, so a caller can hand that
one date to `guard.check_question` as `dates_given`.
"""

# ruff: noqa: E501 - whole sentences in five scripts read better unbroken

from __future__ import annotations

from datetime import date

from ..domain.enums import Language
from .questions import written_day

_E, _H, _B, _T, _O = (
    Language.ENGLISH,
    Language.HINDI,
    Language.BENGALI,
    Language.TAMIL,
    Language.ODIA,
)

_OFFER = {
    _E: "{partner} can keep a room for {nights} from {day}, for {total}. "
    "Rest houses near the hospital often give patient families a better rate. "
    "Shall I ask them for you?",
    _H: "{partner} में {day} से {nights} के लिए कमरा मिल सकता है, {total} में। "
    "अस्पताल के पास के विश्राम गृह अक्सर मरीज़ों के परिवारों को कम दर देते हैं। "
    "क्या मैं आपकी ओर से पूछ लूँ?",
    _B: "{partner}-এ {day} থেকে {nights} জন্য ঘর পাওয়া যাবে, {total}-এ। "
    "হাসপাতালের কাছের বিশ্রামাগার প্রায়ই রোগীর পরিবারকে কম দামে দেয়। "
    "আমি কি আপনার হয়ে জিজ্ঞেস করব?",
    _T: "{partner}-இல் {day} முதல் {nights} அறை கிடைக்கும், {total}. "
    "மருத்துவமனை அருகிலுள்ள தங்குமிடங்கள் நோயாளி குடும்பங்களுக்கு அடிக்கடி குறைந்த கட்டணம் தருகின்றன. "
    "உங்களுக்காக நான் கேட்கட்டுமா?",
    _O: "{partner}ରେ {day}ରୁ {nights} ପାଇଁ ଘର ମିଳିପାରିବ, {total}ରେ। "
    "ହସ୍ପିଟାଲ ପାଖର ବିଶ୍ରାମଗୃହ ପ୍ରାୟତଃ ରୋଗୀ ପରିବାରକୁ କମ୍ ଦରରେ ଦିଅନ୍ତି। "
    "ମୁଁ ଆପଣଙ୍କ ପାଇଁ ପଚାରିବି କି?",
}

_AGREED = {
    _E: "{partner} agreed {total} for {nights} ({nightly} a night instead of {listed}){includes}. "
    "Nothing is booked yet. Shall I book it?",
    _H: "{partner} {nights} के लिए {total} पर मान गया (प्रति रात {listed} की जगह {nightly}){includes}। "
    "अभी कुछ बुक नहीं हुआ है। क्या मैं बुक कर दूँ?",
    _B: "{partner} {nights} জন্য {total}-এ রাজি হয়েছে (প্রতি রাত {listed}-এর বদলে {nightly}){includes}। "
    "এখনও কিছু বুক হয়নি। আমি কি বুক করে দেব?",
    _T: "{partner} {nights} க்கு {total} ஒப்புக்கொண்டது (ஒரு இரவுக்கு {listed} பதில் {nightly}){includes}. "
    "இன்னும் எதுவும் பதிவு செய்யப்படவில்லை. பதிவு செய்யட்டுமா?",
    _O: "{partner} {nights} ପାଇଁ {total}ରେ ରାଜି ହେଲେ (ରାତି ପିଛା {listed} ବଦଳରେ {nightly}){includes}। "
    "ଏପର୍ଯ୍ୟନ୍ତ କିଛି ବୁକ୍ ହୋଇନାହିଁ। ମୁଁ ବୁକ୍ କରିଦେବି କି?",
}

_NO_BETTER = {
    _E: "{partner} could not lower the price this time, so it stays {total} for {nights}. Shall I book it?",
    _H: "{partner} इस बार दाम कम नहीं कर सका, इसलिए {nights} के लिए {total} ही रहेगा। क्या मैं बुक कर दूँ?",
    _B: "{partner} এবার দাম কমাতে পারেনি, তাই {nights} জন্য {total}-ই থাকছে। আমি কি বুক করে দেব?",
    _T: "{partner} இம்முறை விலையைக் குறைக்க முடியவில்லை, {nights} க்கு {total} தான். பதிவு செய்யட்டுமா?",
    _O: "{partner} ଏଥର ଦର କମାଇପାରିଲେ ନାହିଁ, ତେଣୁ {nights} ପାଇଁ {total} ରହିବ। ମୁଁ ବୁକ୍ କରିଦେବି କି?",
}

_BOOKED = {
    _E: "Your room at {partner} is booked for {nights} from {day}. {paid}",
    _H: "{partner} में आपका कमरा {day} से {nights} के लिए बुक हो गया है। {paid}",
    _B: "{partner}-এ আপনার ঘর {day} থেকে {nights} জন্য বুক হয়ে গেছে। {paid}",
    _T: "{partner}-இல் உங்கள் அறை {day} முதல் {nights} க்கு பதிவு செய்யப்பட்டது. {paid}",
    _O: "{partner}ରେ ଆପଣଙ୍କ ଘର {day}ରୁ {nights} ପାଇଁ ବୁକ୍ ହୋଇଗଲା। {paid}",
}

_PAY_AT_DESK = {
    _E: "Pay {total} at their desk.",
    _H: "{total} उनके काउंटर पर दें।",
    _B: "{total} ওদের কাউন্টারে দেবেন।",
    _T: "{total} அவர்களின் கவுண்டரில் செலுத்துங்கள்.",
    _O: "{total} ସେମାନଙ୍କ କାଉଣ୍ଟରରେ ଦିଅନ୍ତୁ।",
}

_HOSPITAL_PAYS = {
    _E: "The hospital is paying for it, so there is no cost to you.",
    _H: "इसका खर्च अस्पताल उठा रहा है, आपको कुछ नहीं देना है।",
    _B: "এর খরচ হাসপাতাল দিচ্ছে, আপনাকে কিছু দিতে হবে না।",
    _T: "இதன் செலவை மருத்துவமனை ஏற்கிறது, நீங்கள் எதுவும் செலுத்த வேண்டாம்.",
    _O: "ଏହାର ଖର୍ଚ୍ଚ ହସ୍ପିଟାଲ ଦେଉଛି, ଆପଣଙ୍କୁ କିଛି ଦେବାକୁ ପଡ଼ିବ ନାହିଁ।",
}

#: Appended to the approval message when the desk covered a hospital-caused change.
_NO_EXTRA_COST = {
    _E: "We are sorry for the change. The hospital will cover the extra cost of it — "
    "there is no extra cost to you.",
    _H: "इस बदलाव के लिए हमें खेद है। इसका अतिरिक्त खर्च अस्पताल उठाएगा — आपको कुछ अतिरिक्त नहीं देना है।",
    _B: "এই পরিবর্তনের জন্য আমরা দুঃখিত। এর বাড়তি খরচ হাসপাতাল দেবে — আপনাকে বাড়তি কিছু দিতে হবে না।",
    _T: "இந்த மாற்றத்திற்கு வருந்துகிறோம். இதன் கூடுதல் செலவை மருத்துவமனை ஏற்கும் — "
    "உங்களுக்குக் கூடுதல் செலவு இல்லை.",
    _O: "ଏହି ପରିବର୍ତ୍ତନ ପାଇଁ ଆମେ ଦୁଃଖିତ। ଏହାର ଅତିରିକ୍ତ ଖର୍ଚ୍ଚ ହସ୍ପିଟାଲ ଦେବ — ଆପଣଙ୍କୁ ଅତିରିକ୍ତ କିଛି ଦେବାକୁ ପଡ଼ିବ ନାହିଁ।",
}

_NIGHTS = {
    _E: ("1 night", "{n} nights"),
    _H: ("1 रात", "{n} रातों"),
    _B: ("1 রাতের", "{n} রাতের"),
    _T: ("1 இரவு", "{n} இரவுகள்"),
    _O: ("1 ରାତି", "{n} ରାତି"),
}

_INCLUDES = {
    _E: ", {what} included",
    _H: ", {what} सहित",
    _B: ", {what} সহ",
    _T: ", {what} உட்பட",
    _O: ", {what} ସହିତ",
}

_INCLUDED_THING = {
    "breakfast": {_E: "breakfast", _H: "नाश्ता", _B: "জলখাবার", _T: "காலை உணவு", _O: "ଜଳଖିଆ"},
    "one attendant's bed": {
        _E: "a bed for one attendant",
        _H: "एक साथी के लिए बिस्तर",
        _B: "একজন সঙ্গীর বিছানা",
        _T: "ஒரு உதவியாளருக்கு படுக்கை",
        _O: "ଜଣେ ସାଥୀଙ୍କ ପାଇଁ ଶଯ୍ୟା",
    },
}


def _pick(table: dict[Language, str], language: Language) -> str:
    return table.get(language) or table[Language.ENGLISH]


def rupees(paise: int) -> str:
    return f"₹{paise // 100:,}"


def nights(n: int, language: Language) -> str:
    one, many = _NIGHTS.get(language) or _NIGHTS[Language.ENGLISH]
    return one if n == 1 else many.format(n=n)


def stay_offer(
    *, language: Language, partner: str, n_nights: int, check_in: date, total_paise: int
) -> str:
    return _pick(_OFFER, language).format(
        partner=partner,
        nights=nights(n_nights, language),
        day=written_day(check_in, language),
        total=rupees(total_paise),
    )


def stay_agreed(
    *,
    language: Language,
    partner: str,
    n_nights: int,
    total_paise: int,
    nightly_paise: int,
    listed_paise: int,
    includes: tuple[str, ...] = (),
) -> str:
    things = [
        (_INCLUDED_THING.get(i) or {}).get(language) or (_INCLUDED_THING.get(i) or {}).get(_E) or i
        for i in includes
    ]
    extra = _pick(_INCLUDES, language).format(what=", ".join(things)) if things else ""
    return _pick(_AGREED, language).format(
        partner=partner,
        nights=nights(n_nights, language),
        total=rupees(total_paise),
        nightly=rupees(nightly_paise),
        listed=rupees(listed_paise),
        includes=extra,
    )


def stay_no_better(*, language: Language, partner: str, n_nights: int, total_paise: int) -> str:
    return _pick(_NO_BETTER, language).format(
        partner=partner, nights=nights(n_nights, language), total=rupees(total_paise)
    )


def stay_booked(
    *,
    language: Language,
    partner: str,
    n_nights: int,
    check_in: date,
    total_paise: int,
    hospital_pays: bool,
) -> str:
    paid = (
        _pick(_HOSPITAL_PAYS, language)
        if hospital_pays
        else _pick(_PAY_AT_DESK, language).format(total=rupees(total_paise))
    )
    return _pick(_BOOKED, language).format(
        partner=partner,
        nights=nights(n_nights, language),
        day=written_day(check_in, language),
        paid=paid,
    )


def no_extra_cost(language: Language) -> str:
    return _pick(_NO_EXTRA_COST, language)
