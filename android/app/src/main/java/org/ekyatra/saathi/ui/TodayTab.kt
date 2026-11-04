package org.ekyatra.saathi.ui

import android.content.Context
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.FamilyHome
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localDate
import org.ekyatra.saathi.i18n.localDateShort
import org.ekyatra.saathi.i18n.stepWord
import org.ekyatra.saathi.ui.theme.Tokens
import org.ekyatra.saathi.voice.Speaker

/**
 * The first thing a family sees, in the order they need it: the answer, then (only
 * if they ask) why, then the next visit and what to carry. One thumb, daylight,
 * and nothing on screen that does not help with "do we get on the bus".
 */
@Composable
fun TodayTab(home: FamilyHome?, lang: Lang, s: Strings, speaker: Speaker, patientId: String) {
    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        AnswerCard(home, lang, s, speaker)
        if (home == null || home.decision == null) return@Column

        DoNowCard(home.guide, lang, s)

        if (home.waitingFor.isNotEmpty()) {
            ExpandableCard(
                title = s.why,
                summary = "${s.waitingFor}: ${home.waitingFor.joinToString(", ") { stepWord(it.kind, it.what, lang) }}",
                glyph = Glyph.Clock,
                tint = Tokens.wait,
                background = Tokens.waitTint,
                tag = "why-card",
            ) {
                Why(home.waitingFor, lang, s, inCard = true)
            }
        }

        home.steps.firstOrNull { it.isNext }?.let { next ->
            SaathiCard(Modifier.testTag("next-card")) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    GlyphBadge(Glyph.Pin, Tokens.blue600, Tokens.blue100)
                    Column(Modifier.weight(1f)) {
                        Text(s.nextVisit, fontSize = 13.sp, color = Tokens.ink3)
                        Text(stepWord(next.kind, next.what, lang), fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
                    }
                    // Cleared to travel, the date that matters is the one they set out on;
                    // a step's older booked date beside it would read as a contradiction.
                    val shown = if (home.decision == "go" && home.travelOn != null) home.travelOn else next.on
                    if (shown != null) {
                        Text(
                            localDateShort(shown, lang),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            color = Tokens.blue700,
                            modifier = Modifier.background(Tokens.blue100, RoundedCornerShape(Tokens.radiusPill)).padding(10.dp, 5.dp),
                        )
                    }
                }
                home.whereToGoFirst?.let {
                    Text(
                        "${s.firstStop}: $it",
                        fontSize = 14.sp,
                        color = Tokens.ink2,
                        modifier = Modifier.padding(top = 10.dp, start = 48.dp),
                    )
                }
            }
        }

        if (home.whatToBring.isNotEmpty()) {
            BringCard(home.whatToBring, s, key = "$patientId:${home.travelOn ?: "-"}")
        }

        SaathiCard {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                GlyphBadge(Glyph.Route, Tokens.ink2, Tokens.fillQuiet)
                Column {
                    Text(s.journey, fontSize = 13.sp, color = Tokens.ink3)
                    val hours = home.patient.hoursEachWay?.let { " · ${"%.0f".format(it)} ${s.hoursEachWay}" } ?: ""
                    Text(
                        "${"%.0f".format(home.patient.distanceKm)} ${s.kmAway}$hours",
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium,
                        color = Tokens.ink,
                    )
                }
            }
        }
    }
}

private data class Mood(val top: Color, val ink: Color, val glyph: Glyph)

private fun mood(decision: String?): Mood = when (decision) {
    "go" -> Mood(Tokens.goTint, Tokens.go, Glyph.CheckCircle)
    "wait", "replan" -> Mood(Tokens.waitTint, Tokens.wait, Glyph.Clock)
    "uncertain" -> Mood(Tokens.uncertainTint, Tokens.uncertain, Glyph.Clock)
    else -> Mood(Tokens.sunken, Tokens.ink4, Glyph.Spark)
}

/** One word, one date, one sentence, and a way to hear it. */
@Composable
fun AnswerCard(home: FamilyHome?, lang: Lang, s: Strings, speaker: Speaker) {
    val decision = home?.decision
    val m = mood(decision)
    val top by animateColorAsState(m.top, label = "mood")
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = Tokens.surface,
        border = BorderStroke(1.dp, Tokens.lineSoft),
        shadowElevation = 2.dp,
        modifier = Modifier.fillMaxWidth().testTag("answer"),
    ) {
        Column(
            Modifier
                .background(Brush.verticalGradient(listOf(top, Tokens.surface)))
                .padding(22.dp, 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (home == null || decision == null) {
                Text("…", fontSize = 40.sp, color = Tokens.ink4)
                Text(s.noPlanYet, fontSize = 17.sp, color = Tokens.ink2, textAlign = TextAlign.Center)
                return@Column
            }
            Box(
                Modifier.size(64.dp).background(Tokens.surface, CircleShape),
                contentAlignment = Alignment.Center,
            ) { SaathiIcon(m.glyph, m.ink, 36.dp) }
            Text(
                when (decision) {
                    "go" -> s.come
                    "wait" -> s.wait
                    else -> s.notYet
                },
                fontSize = 42.sp,
                lineHeight = 46.sp,
                fontWeight = FontWeight.Bold,
                color = m.ink,
                modifier = Modifier.testTag("answer-word"),
            )
            if (decision == "go" && home.travelOn != null) {
                Text(
                    "${s.travelOn} · ${localDate(home.travelOn, lang)}",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Tokens.go,
                    modifier = Modifier.background(Tokens.surface, RoundedCornerShape(Tokens.radiusPill)).padding(14.dp, 7.dp),
                )
            }
            val held = home.message?.held ?: false
            val sentence = if (held) s.personCalling else home.message?.body
            if (sentence != null) {
                Text(
                    sentence,
                    fontSize = 17.sp,
                    lineHeight = 25.sp,
                    color = if (held) Tokens.ink3 else Tokens.ink2,
                    fontStyle = if (held) FontStyle.Italic else FontStyle.Normal,
                    textAlign = TextAlign.Center,
                )
                ReadAloud(sentence, lang, s, speaker)
            }
        }
    }
}

/**
 * What to carry, ticked off as it goes in the bag. The ticks stay on this phone
 * for this trip only, so the next journey starts with an empty list.
 */
@Composable
private fun BringCard(items: List<String>, s: Strings, key: String) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("saathi-bring", Context.MODE_PRIVATE) }
    var packed by remember(key) { mutableStateOf(prefs.getStringSet(key, emptySet())!!.toSet()) }
    val done = items.count { it in packed }
    ExpandableCard(
        title = s.bring,
        summary = "$done / ${items.size} ${s.packed}",
        glyph = Glyph.Bag,
        tint = Tokens.blue600,
        background = Tokens.blue100,
        tag = "bring-card",
        initiallyOpen = true,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (item in items) {
                val ticked = item in packed
                Row(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 44.dp)
                        .clickable {
                            packed = if (ticked) packed - item else packed + item
                            prefs.edit().putStringSet(key, packed).apply()
                        }
                        .testTag("bring-item"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(
                        Modifier
                            .size(24.dp)
                            .background(if (ticked) Tokens.go else Tokens.surface, RoundedCornerShape(7.dp))
                            .then(if (ticked) Modifier else Modifier.background(Tokens.fillQuiet, RoundedCornerShape(7.dp))),
                        contentAlignment = Alignment.Center,
                    ) { if (ticked) SaathiIcon(Glyph.Check, Color.White, 16.dp) }
                    Text(
                        item.replaceFirstChar { it.uppercase() },
                        fontSize = 15.sp,
                        color = if (ticked) Tokens.ink4 else Tokens.ink,
                        textDecoration = if (ticked) TextDecoration.LineThrough else TextDecoration.None,
                    )
                }
            }
        }
    }
}
