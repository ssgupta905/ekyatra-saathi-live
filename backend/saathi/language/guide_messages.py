"""The journey's step-by-step updates, in the family's own language.

Fixed sentences, not a model call: an update is a status ("the reports are done,
we are waiting on the scheme desk"), never a finding or advice, and it names no
date. The date is the plan message's business, and that message is the one the
guard checks. Wording here is a first draft for a native speaker to review.
"""

from __future__ import annotations

from ..domain.enums import Language
from ..domain.guide import FamilyAction, StageKind
from ..guide.update import GuideUpdate

_LABELS: dict[Language, dict[StageKind, str]] = {
    Language.ENGLISH: {
        StageKind.TESTS: "Tests", StageKind.REPORTS: "Reports",
        StageKind.INSURANCE: "Scheme approval", StageKind.PHARMACY: "Pharmacy",
        StageKind.RIDE: "Ride", StageKind.STAY: "Place to stay",
        StageKind.DOCUMENTS: "Papers", StageKind.VISIT: "Doctor visit",
        StageKind.NEXT_SESSION: "Next session",
    },
    Language.HINDI: {
        StageKind.TESTS: "जाँच", StageKind.REPORTS: "रिपोर्ट",
        StageKind.INSURANCE: "योजना की मंज़ूरी", StageKind.PHARMACY: "फार्मेसी",
        StageKind.RIDE: "गाड़ी", StageKind.STAY: "ठहरने की जगह",
        StageKind.DOCUMENTS: "कागज़ात", StageKind.VISIT: "डॉक्टर से मिलना",
        StageKind.NEXT_SESSION: "अगली बार",
    },
    Language.BENGALI: {
        StageKind.TESTS: "পরীক্ষা", StageKind.REPORTS: "রিপোর্ট",
        StageKind.INSURANCE: "প্রকল্পের অনুমোদন", StageKind.PHARMACY: "ফার্মেসি",
        StageKind.RIDE: "গাড়ি", StageKind.STAY: "থাকার জায়গা",
        StageKind.DOCUMENTS: "কাগজপত্র", StageKind.VISIT: "ডাক্তারের সঙ্গে দেখা",
        StageKind.NEXT_SESSION: "পরের বার",
    },
    Language.ODIA: {
        StageKind.TESTS: "ପରୀକ୍ଷା", StageKind.REPORTS: "ରିପୋର୍ଟ",
        StageKind.INSURANCE: "ଯୋଜନା ଅନୁମୋଦନ", StageKind.PHARMACY: "ଫାର୍ମାସୀ",
        StageKind.RIDE: "ଗାଡ଼ି", StageKind.STAY: "ରହିବା ସ୍ଥାନ",
        StageKind.DOCUMENTS: "କାଗଜପତ୍ର", StageKind.VISIT: "ଡାକ୍ତରଙ୍କ ସହ ଭେଟ",
        StageKind.NEXT_SESSION: "ପରବର୍ତ୍ତୀ ଥର",
    },
}  # fmt: skip

_DONE: dict[Language, str] = {
    Language.ENGLISH: "{label}: done ({done} of {total}).",
    Language.HINDI: "{label}: पूरा ({done}/{total})।",
    Language.BENGALI: "{label}: সম্পূর্ণ ({done}/{total})।",
    Language.ODIA: "{label}: ସମ୍ପୂର୍ଣ୍ଣ ({done}/{total})।",
}

#: What to say about where things stand now. `{label}` is the stage being worked on.
_NOW: dict[Language, dict[FamilyAction, str]] = {
    Language.ENGLISH: {
        FamilyAction.NOTHING_YET: "Now we are waiting on: {label}. You do not need to do anything.",
        FamilyAction.WAIT_FOR_TEAM: (
            "There is a problem with: {label}. Our team is arranging another way. "
            "Please do not travel yet."
        ),
        FamilyAction.KEEP_DOCUMENTS_READY: "Please keep your papers ready.",
        FamilyAction.BE_READY_FOR_PICKUP: "Your ride is arranged. Please be ready at pickup time.",
        FamilyAction.GO_TO_FIRST_STOP: (
            "Your visit is confirmed. Open the app to see the day and where to go first."
        ),
    },
    Language.HINDI: {
        FamilyAction.NOTHING_YET: "अब हम इसका इंतज़ार कर रहे हैं: {label}। आपको कुछ करने की ज़रूरत नहीं है।",
        FamilyAction.WAIT_FOR_TEAM: (
            "इसमें दिक्कत आई है: {label}। हमारी टीम दूसरा रास्ता निकाल रही है। अभी यात्रा न करें।"
        ),
        FamilyAction.KEEP_DOCUMENTS_READY: "कृपया अपने कागज़ात तैयार रखें।",
        FamilyAction.BE_READY_FOR_PICKUP: "आपकी गाड़ी तय हो गई है। कृपया लेने के समय तैयार रहें।",
        FamilyAction.GO_TO_FIRST_STOP: (
            "आपकी मुलाक़ात पक्की हो गई है। दिन और पहले कहाँ जाना है, ऐप में देखें।"
        ),
    },
    Language.BENGALI: {
        FamilyAction.NOTHING_YET: "এখন আমরা এর জন্য অপেক্ষা করছি: {label}। আপনাকে কিছু করতে হবে না।",
        FamilyAction.WAIT_FOR_TEAM: (
            "এতে সমস্যা হয়েছে: {label}। আমাদের দল অন্য উপায় ঠিক করছে। এখনই যাত্রা করবেন না।"
        ),
        FamilyAction.KEEP_DOCUMENTS_READY: "অনুগ্রহ করে আপনার কাগজপত্র তৈরি রাখুন।",
        FamilyAction.BE_READY_FOR_PICKUP: "আপনার গাড়ি ঠিক হয়েছে। নেওয়ার সময় তৈরি থাকুন।",
        FamilyAction.GO_TO_FIRST_STOP: (
            "আপনার দেখা পাকা হয়েছে। কোন দিন এবং আগে কোথায় যাবেন, অ্যাপে দেখুন।"
        ),
    },
    Language.ODIA: {
        FamilyAction.NOTHING_YET: (
            "ବର୍ତ୍ତମାନ ଆମେ ଏହା ପାଇଁ ଅପେକ୍ଷା କରୁଛୁ: {label}। ଆପଣଙ୍କୁ କିଛି କରିବାକୁ ପଡ଼ିବ ନାହିଁ।"
        ),
        FamilyAction.WAIT_FOR_TEAM: (
            "ଏଥିରେ ଅସୁବିଧା ହୋଇଛି: {label}। ଆମ ଦଳ ଅନ୍ୟ ଉପାୟ ଠିକ୍ କରୁଛି। ଏବେ ଯାତ୍ରା କରନ୍ତୁ ନାହିଁ।"
        ),
        FamilyAction.KEEP_DOCUMENTS_READY: "ଦୟାକରି ଆପଣଙ୍କ କାଗଜପତ୍ର ପ୍ରସ୍ତୁତ ରଖନ୍ତୁ।",
        FamilyAction.BE_READY_FOR_PICKUP: "ଆପଣଙ୍କ ଗାଡ଼ି ଠିକ୍ ହୋଇଛି। ନେବା ସମୟରେ ପ୍ରସ୍ତୁତ ରୁହନ୍ତୁ।",
        FamilyAction.GO_TO_FIRST_STOP: (
            "ଆପଣଙ୍କ ଭେଟ ପକ୍କା ହୋଇଛି। କେଉଁ ଦିନ ଏବଂ ପ୍ରଥମେ କେଉଁଠି ଯିବେ, ଆପରେ ଦେଖନ୍ତୁ।"
        ),
    },
}  # fmt: skip


def render_guide_message(language: Language, update: GuideUpdate) -> str | None:
    """One short update, or None when there is nothing to say beyond what was said."""
    labels = _LABELS.get(language, _LABELS[Language.ENGLISH])
    parts = [
        _DONE.get(language, _DONE[Language.ENGLISH]).format(
            label=labels[kind], done=update.done, total=update.total
        )
        for kind in update.finished
    ]
    phrases = _NOW.get(language, _NOW[Language.ENGLISH])
    if update.now is not None and update.action in phrases:
        parts.append(phrases[update.action].format(label=labels[update.now]))
    return " ".join(parts) or None
