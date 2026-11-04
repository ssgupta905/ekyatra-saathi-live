package org.ekyatra.saathi.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.GuideStage
import org.ekyatra.saathi.data.JourneyGuide
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localDate
import org.ekyatra.saathi.i18n.localDateShort
import org.ekyatra.saathi.ui.theme.Tokens

/**
 * The whole journey, from the first test to the doctor, in the order it happens.
 *
 * A date appears only on the visit, and only when the hospital has promised one.
 * A link that has gone wrong says so in words as well as colour, and says the
 * team has it: a family should never have to guess whether to wait or to act.
 */

private fun label(kind: String, s: Strings): String = when (kind) {
    "tests" -> s.stageTests
    "reports" -> s.stageReports
    "insurance" -> s.stageInsurance
    "pharmacy" -> s.stagePharmacy
    "ride" -> s.stageRide
    "stay" -> s.stageStay
    "documents" -> s.stageDocuments
    "visit" -> s.stageVisit
    "next_session" -> s.stageNextSession
    else -> kind.replace('_', ' ')
}

private fun action(action: String, s: Strings): String? = when (action) {
    "nothing_yet" -> s.actionNothingYet
    "wait_for_team" -> s.actionWaitForTeam
    "keep_documents_ready" -> s.actionKeepDocuments
    "be_ready_for_pickup" -> s.actionPickup
    "go_to_first_stop" -> s.actionFirstStop
    else -> null
}

private fun stateWord(stage: GuideStage, s: Strings): String = when {
    stage.state == "done" -> s.stateDone
    stage.state == "problem" -> s.stateProblem
    stage.isNow -> s.stateNow
    stage.state == "waiting" -> s.stateWaiting
    else -> s.stateNext
}

private fun glyph(stage: GuideStage): Glyph = when {
    stage.state == "done" -> Glyph.CheckCircle
    stage.state == "waiting" -> Glyph.Clock
    stage.state == "problem" -> Glyph.Spark
    stage.kind == "visit" -> Glyph.Pin
    else -> Glyph.Doc
}

private fun progress(guide: JourneyGuide, s: Strings): String =
    s.progress.replace("{done}", guide.done.toString()).replace("{total}", guide.total.toString())

/** What to do right now, at the top of Today. Often the answer is "nothing, we are on it". */
@Composable
fun DoNowCard(guide: JourneyGuide?, lang: Lang, s: Strings) {
    val now = guide?.stages?.firstOrNull { it.id == guide.nowStageId } ?: return
    val problem = now.state == "problem"
    SaathiCard(Modifier.testTag("do-now-card")) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            GlyphBadge(glyph(now), if (problem) Tokens.critical else Tokens.blue600, if (problem) Tokens.criticalTint else Tokens.blue100)
            Column(Modifier.weight(1f)) {
                Text(s.doNow, fontSize = 13.sp, color = Tokens.ink3)
                Text(label(now.kind, s), fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
            }
            StatePill(stateWord(now, s), now.state)
        }
        action(now.action, s)?.let {
            Text(it, fontSize = 16.sp, color = Tokens.ink, modifier = Modifier.padding(top = 10.dp))
        }
        if (now.party != null) {
            Text(
                now.party + if (now.detail.isNotBlank()) " · ${now.detail}" else "",
                fontSize = 14.sp,
                color = Tokens.ink3,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
        now.window?.takeIf { it.size == 2 }?.let {
            Text(
                "${s.expectedBetween} ${localDateShort(it[0], lang)} – ${localDateShort(it[1], lang)}",
                fontSize = 14.sp,
                color = Tokens.ink3,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun StatePill(text: String, state: String) {
    val (fill, ink) = when (state) {
        "done" -> Tokens.goTint to Tokens.go
        "problem" -> Tokens.criticalTint to Tokens.critical
        "waiting" -> Tokens.waitTint to Tokens.wait
        else -> Tokens.fillQuiet to Tokens.ink2
    }
    Text(
        text,
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        color = ink,
        modifier = Modifier.clip(RoundedCornerShape(Tokens.radiusPill)).background(fill).padding(10.dp, 3.dp),
    )
}

/** The chain: every stage in order, who has it, and how far along. */
@Composable
fun JourneyChain(guide: JourneyGuide?, lang: Lang, s: Strings) {
    if (guide == null || guide.stages.isEmpty()) {
        Text(s.noJourney, fontSize = 15.sp, color = Tokens.ink3, modifier = Modifier.padding(4.dp))
        return
    }
    Text(progress(guide, s), fontSize = 14.sp, color = Tokens.ink3, modifier = Modifier.padding(bottom = 6.dp))
    Box(
        Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(Tokens.fillQuiet),
    ) {
        val fraction = guide.done.toFloat() / maxOf(guide.total, 1)
        Box(Modifier.fillMaxWidth(fraction).height(6.dp).background(Tokens.go))
    }
    Box(Modifier.height(14.dp))
    guide.stages.forEachIndexed { index, stage ->
        StageRow(index + 1, stage, lang, s, last = index == guide.stages.lastIndex)
    }
}

@Composable
private fun StageRow(number: Int, stage: GuideStage, lang: Lang, s: Strings, last: Boolean) {
    val (fill, edge, ink) = when {
        stage.isNow && stage.state != "problem" -> Triple(Tokens.blue500, Tokens.blue500, Color.White)
        stage.state == "done" -> Triple(Tokens.goTint, Tokens.go, Tokens.go)
        stage.state == "problem" -> Triple(Tokens.criticalTint, Tokens.critical, Tokens.critical)
        stage.state == "waiting" -> Triple(Tokens.waitTint, Tokens.wait, Tokens.wait)
        else -> Triple(Tokens.surface, Tokens.line, Tokens.ink4)
    }
    Row(Modifier.height(IntrinsicSize.Min).testTag("stage-${stage.id}"), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.width(26.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier.size(24.dp).clip(CircleShape).background(fill).border(1.dp, edge, CircleShape),
                contentAlignment = Alignment.Center,
            ) { SaathiIcon(glyph(stage), ink, 14.dp) }
            if (!last) Box(Modifier.width(2.dp).weight(1f).background(Tokens.line))
        }
        Column(Modifier.weight(1f).padding(bottom = 14.dp)) {
            Text(
                "$number. ${label(stage.kind, s)}",
                fontSize = 16.sp,
                color = if (stage.state == "done") Tokens.ink3 else Tokens.ink,
                fontWeight = if (stage.isNow) FontWeight.SemiBold else FontWeight.Normal,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                if (stage.on != null) Text(localDate(stage.on, lang), fontSize = 13.sp, color = Tokens.ink3)
                StatePill(stateWord(stage, s), stage.state)
                stage.party?.let { Text(it, fontSize = 13.sp, color = Tokens.ink3) }
            }
            if (stage.state == "problem") {
                action(stage.action, s)?.let { Text(it, fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 3.dp)) }
            }
            if (stage.kind == "visit" && stage.firstStop != null) {
                Text("${s.firstStop}: ${stage.firstStop}", fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 3.dp))
            }
            if (stage.kind == "documents" && stage.bring.isNotEmpty()) {
                Text(stage.bring.joinToString(" · "), fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 3.dp))
            }
        }
    }
}
