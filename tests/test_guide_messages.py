"""Journey updates to the family: only what changed, in their language, never a date."""

from __future__ import annotations

import re

import pytest
from saathi.domain.enums import Language
from saathi.domain.guide import (
    FamilyAction,
    GuideStage,
    JourneyGuide,
    StageKind,
    StageState,
)
from saathi.guide.update import GuideUpdate, guide_update
from saathi.language.guard import CLINICAL_TERMS, stated_dates
from saathi.language.guide_messages import _LABELS, _NOW, render_guide_message


def _guide(*states, now=None, decision="wait") -> JourneyGuide:
    kinds = (StageKind.REPORTS, StageKind.INSURANCE, StageKind.RIDE, StageKind.VISIT)
    stages = tuple(
        GuideStage(id=k.value, kind=k, state=s, is_now=(k.value == now))
        for k, s in zip(kinds, states, strict=False)
    )
    return JourneyGuide(
        patient_id="P", decision=decision, stages=stages, now_stage_id=now,
        done=sum(1 for s in stages if s.state is StageState.DONE), total=len(stages),
    )


D, W, P, U = StageState.DONE, StageState.WAITING, StageState.PROBLEM, StageState.UPCOMING


def test_nothing_new_means_nothing_to_say():
    same = _guide(D, W, U, U, now="insurance")

    assert guide_update(same, same) is None


def test_a_stage_finishing_is_news_and_names_what_is_next():
    before = _guide(W, U, U, U, now="reports")
    after = _guide(D, W, U, U, now="insurance")

    update = guide_update(before, after)

    assert update.finished == (StageKind.REPORTS,)
    assert update.now is StageKind.INSURANCE and update.done == 1 and update.total == 4


def test_a_new_problem_is_news_even_when_nothing_finished():
    before = _guide(D, D, W, U, now="ride")
    after = _guide(D, D, P, U, now="ride")

    update = guide_update(before, after)

    assert update is not None and update.finished == ()


@pytest.mark.parametrize("language", list(Language))
def test_every_update_reads_in_the_family_s_language_and_names_the_stage(language):
    update = GuideUpdate(
        finished=(StageKind.REPORTS,), now=StageKind.INSURANCE,
        action=FamilyAction.NOTHING_YET, done=2, total=7,
    )

    body = render_guide_message(language, update)

    assert _LABELS[language][StageKind.REPORTS] in body
    assert _LABELS[language][StageKind.INSURANCE] in body
    assert "2" in body and "7" in body
    if language is not Language.ENGLISH:
        assert not re.search(r"[a-zA-Z]{4,}", body), "no English left in a translated update"


def test_an_update_with_no_news_to_tell_says_nothing():
    update = GuideUpdate(
        finished=(), now=StageKind.VISIT, action=FamilyAction.NONE, done=1, total=4
    )

    assert render_guide_message(Language.ENGLISH, update) is None


@pytest.mark.parametrize("language", list(Language))
def test_no_wording_in_any_language_gives_a_date_or_medical_talk(language):
    texts = list(_NOW[language].values()) + list(_LABELS[language].values())
    for text in texts:
        low = text.lower()
        assert not [t for t in CLINICAL_TERMS if t in low], text
        assert not stated_dates(text), text
        assert not re.search(r"\b(20\d\d|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b", low), text


def test_a_failed_party_tells_the_family_not_to_travel_and_that_the_team_has_it():
    update = GuideUpdate(
        finished=(), now=StageKind.RIDE, action=FamilyAction.WAIT_FOR_TEAM, done=2, total=7
    )

    body = render_guide_message(Language.ENGLISH, update)

    assert "do not travel" in body and "team" in body
