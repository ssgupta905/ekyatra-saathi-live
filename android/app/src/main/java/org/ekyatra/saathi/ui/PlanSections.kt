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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.FamilyStep
import org.ekyatra.saathi.data.FamilyWait
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localDateShort
import org.ekyatra.saathi.i18n.stepWord
import org.ekyatra.saathi.ui.theme.Tokens

@Composable
private fun SectionTitle(text: String) {
    Text(
        text.uppercase(),
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = 1.sp,
        color = Tokens.ink3,
        modifier = Modifier.padding(bottom = 12.dp),
    )
}

/**
 * Why the answer is the answer, in the only form that is useful to a family:
 * *what* is being waited for, and *when* it is expected.
 *
 * No probability, no coverage level, no score. A booked date is shown as one date
 * and called confirmed; a forecast is shown as a range and never dressed up as a
 * promise. The difference the family sees is the backend's `certain` flag, true
 * only when the window came from a booking rather than the predictor.
 */
@Composable
fun Why(waits: List<FamilyWait>, lang: Lang, s: Strings) {
    if (waits.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(16.dp, 20.dp, 16.dp, 4.dp)) {
        SectionTitle(s.why)
        Column(Modifier.padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (wait in waits) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SaathiIcon(
                        if (wait.certain) Glyph.CheckCircle else Glyph.Clock,
                        if (wait.certain) Tokens.go else Tokens.wait,
                        18.dp,
                        Modifier.padding(top = 2.dp),
                    )
                    Column {
                        Text(stepWord(wait.kind, wait.what, lang), fontSize = 16.sp, color = Tokens.ink)
                        val whenText = when {
                            wait.certain -> "${s.onThisDay} · ${localDateShort(wait.earliest, lang)}"
                            wait.earliest != null && wait.latest != null ->
                                "${s.expectedBetween} ${localDateShort(wait.earliest, lang)} – " +
                                    localDateShort(wait.latest, lang)
                            else -> "—"
                        }
                        Text(whenText, fontSize = 14.sp, color = Tokens.ink3)
                    }
                }
            }
        }
    }
}

/**
 * The journey as a single vertical line, oldest at the top.
 *
 * The hospital's own board draws this as a branching graph, because a navigator
 * needs to see what is waiting on what. A family needs three things: what is
 * behind them, what is being waited for, and what is next. A step nobody
 * travels for is marked as such: a family that packs a bag for a report has lost
 * two days and a fare for nothing, which is exactly the mistake this project
 * exists to stop.
 */
@Composable
fun PlanStrip(steps: List<FamilyStep>, lang: Lang, s: Strings) {
    if (steps.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(16.dp, 20.dp, 16.dp, 4.dp)) {
        SectionTitle(s.plan)
        Column(Modifier.padding(bottom = 16.dp)) {
            steps.forEachIndexed { index, step ->
                StepRow(step, lang, s, last = index == steps.lastIndex)
            }
        }
    }
}

@Composable
private fun StepRow(step: FamilyStep, lang: Lang, s: Strings, last: Boolean) {
    val (fill, edge, ink) = when {
        step.isNext -> Triple(Tokens.blue500, Tokens.blue500, Color.White)
        step.state == "done" -> Triple(Tokens.goTint, Tokens.go, Tokens.go)
        step.state == "waiting" -> Triple(Tokens.waitTint, Tokens.wait, Tokens.wait)
        else -> Triple(Tokens.surface, Tokens.line, Tokens.ink4)
    }
    val glyph = when {
        step.state == "done" -> Glyph.CheckCircle
        step.state == "waiting" -> Glyph.Clock
        step.travels -> Glyph.Pin
        else -> Glyph.Doc
    }
    val stateLabel = when (step.state) {
        "done" -> s.done
        "waiting" -> s.waiting
        else -> s.ahead
    }

    Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.width(26.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier.size(24.dp).clip(CircleShape).background(fill).border(1.dp, edge, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                SaathiIcon(glyph, ink, 14.dp)
            }
            // The connecting line, drawn between dots rather than under them, so the
            // journey reads as one thread and not a list of bullets.
            if (!last) Box(Modifier.width(2.dp).weight(1f).background(Tokens.line))
        }

        Row(
            Modifier.weight(1f).padding(bottom = 14.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    stepWord(step.kind, step.what, lang),
                    fontSize = 16.sp,
                    color = if (step.state == "done") Tokens.ink3 else Tokens.ink,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (step.on != null) localDateShort(step.on, lang) else "—",
                        fontSize = 13.sp,
                        color = Tokens.ink3,
                    )
                    Text(stateLabel, fontSize = 13.sp, color = Tokens.ink4)
                }
                if (!step.travels) {
                    Text(
                        s.noTravelNeeded,
                        fontSize = 12.sp,
                        color = Tokens.ink3,
                        modifier = Modifier
                            .padding(top = 3.dp)
                            .clip(RoundedCornerShape(Tokens.radiusPill))
                            .background(Tokens.fillQuiet)
                            .padding(7.dp, 1.dp),
                    )
                }
            }
            if (step.isNext) {
                Text(
                    s.nextVisit,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Tokens.blue700,
                    modifier = Modifier
                        .clip(RoundedCornerShape(Tokens.radiusPill))
                        .background(Tokens.blue100)
                        .padding(9.dp, 3.dp),
                )
            }
        }
    }
}
