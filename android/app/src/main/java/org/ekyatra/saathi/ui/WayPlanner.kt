package org.ekyatra.saathi.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.WayGuidance
import org.ekyatra.saathi.data.WayStep
import org.ekyatra.saathi.data.WeighedWay
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.ui.theme.Tokens
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** A time on the phone's own clock, "09:10". Blank when the service gave none. */
internal fun clock(iso: String?): String = runCatching {
    OffsetDateTime.parse(iso!!).atZoneSameInstant(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("HH:mm"))
}.getOrDefault("")

private fun modeWord(mode: String, s: Strings) = when (mode) {
    "bus" -> s.modeBus
    "metro" -> s.modeMetro
    "train" -> s.modeTrain
    "taxi" -> s.modeTaxi
    "walk" -> s.modeStep
    else -> mode
}

private fun tagWord(tag: String, s: Strings) = when (tag) {
    "cheapest" -> s.tagCheapest
    "fastest" -> s.tagFastest
    "fewest_changes" -> s.tagFewest
    "least_walking" -> s.tagLeastWalk
    else -> null
}

private fun reasonWord(code: String, s: Strings) = when (code) {
    "fits_budget" -> s.reasonFits
    "some_over_budget" -> s.reasonSomeOver
    "all_over_budget" -> s.reasonAllOver
    "cost_unknown" -> s.wayCostNone
    "say_what_you_can_manage" -> s.wayNoLimit
    else -> null
}

private fun changes(n: Int, s: Strings) = if (n == 0) s.wayNoChange else s.wayChanges.replace("{n}", n.toString())

/**
 * The step a person follows: "Board 5A towards Parel at Station Road · 09:10 …
 * get off at Hospital Gate after 11 stops". Walking and taxis say how long.
 */
@Composable
private fun StepLine(step: WayStep, s: Strings) {
    val text = when (step.mode) {
        "walk" -> s.wayWalk.replace("{n}", step.minutes.toString()) + (step.note?.let { " · $it" } ?: "")
        "taxi" -> "${s.modeTaxi} · ${step.minutes} min"
        else -> buildString {
            append("${s.wayBoard} ${modeWord(step.mode, s)} ${step.line.orEmpty()}")
            step.towards?.let { append(" ${s.wayTowards} $it") }
            step.boardAt?.let { append(" · $it") }
            clock(step.departs).takeIf { it.isNotBlank() }?.let { append(" · $it") }
            step.getOffAt?.let { append("\n${s.wayOff} $it") }
            step.stops?.let { append(" · ${s.wayStops.replace("{n}", it.toString())}") }
        }
    }
    Text(text, fontSize = 14.sp, color = Tokens.ink, modifier = Modifier.padding(top = 6.dp))
}

@Composable
private fun WayCard(w: WeighedWay, best: Boolean, s: Strings) {
    val o = w.option
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 10.dp)
            .clip(RoundedCornerShape(Tokens.radiusMd))
            .border(if (best) 2.dp else 1.dp, if (best) Tokens.blue500 else Tokens.line, RoundedCornerShape(Tokens.radiusMd))
            .padding(12.dp)
            .testTag("way-${o.id}"),
    ) {
        if (best) Text(s.wayBest, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Tokens.blue600)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("${o.minutes} min", fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
            Text(
                o.farePaise?.let(::rupees) ?: s.wayCostNone,
                fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
                color = if (o.farePaise == null) Tokens.ink3 else if (w.fit == "over") Tokens.critical else Tokens.ink,
            )
        }
        Text(
            listOfNotNull(
                changes(o.steps.count { it.mode != "walk" }.minus(1).coerceAtLeast(0), s),
                when (o.fareBasis) {
                    "service" -> s.wayFareService
                    "quote" -> s.wayFareQuote
                    else -> null
                },
                if (w.fit == "over") s.wayOver else null,
                w.extraOverCheapestPaise?.takeIf { it > 0 }?.let { "+${rupees(it)}" },
            ).joinToString(" · "),
            fontSize = 12.sp, color = Tokens.ink3,
        )
        val tags = w.tags.mapNotNull { tagWord(it, s) }
        if (tags.isNotEmpty()) Text(tags.joinToString(" · "), fontSize = 12.sp, color = Tokens.go, modifier = Modifier.padding(top = 2.dp))
        w.leaveBy?.let { clock(it).takeIf { t -> t.isNotBlank() } }?.let {
            Text(s.wayLeaveBy.replace("{t}", it), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Tokens.wait, modifier = Modifier.padding(top = 4.dp))
        }
        o.steps.forEach { StepLine(it, s) }
        if (o.source == "demo") Text(s.wayDemo, fontSize = 11.sp, color = Tokens.critical, modifier = Modifier.padding(top = 6.dp))
    }
}

/**
 * Ask for the ways, then show them: the one we suggest first, why, and the
 * rest with what each costs and gives up. Nothing here invents a fare; with
 * none given it says "cost not known".
 */
@Composable
fun WayPlanner(api: SaathiApi, patientId: String, leg: String, s: Strings) {
    var origin by remember { mutableStateOf("") }
    var guidance by remember { mutableStateOf<WayGuidance?>(null) }
    var source by remember { mutableStateOf("") }
    var failed by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(Modifier.padding(top = 8.dp)) {
        if (leg == "near") {
            OutlinedTextField(
                origin, { origin = it }, singleLine = true, label = { Text(s.wayFrom) },
                modifier = Modifier.fillMaxWidth().testTag("way-origin"),
            )
        }
        Text(
            s.wayShow,
            fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Tokens.surface,
            modifier = Modifier
                .padding(top = 8.dp)
                .testTag("way-show-$leg")
                .clip(RoundedCornerShape(Tokens.radiusPill))
                .background(Tokens.blue600)
                .clickable(enabled = !busy && (leg == "far" || origin.isNotBlank())) {
                    busy = true; failed = false
                    scope.launch {
                        try {
                            val got = api.wayOptions(patientId, leg, origin)
                            guidance = got.guidance; source = got.source
                        } catch (e: CancellationException) {
                            throw e
                        } catch (_: Exception) {
                            guidance = null; failed = true
                        } finally {
                            busy = false
                        }
                    }
                }
                .padding(16.dp, 10.dp),
        )
        if (failed) Text(s.wayCantLoad, fontSize = 13.sp, color = Tokens.critical, modifier = Modifier.padding(top = 6.dp))
        guidance?.let { g ->
            g.reasons.mapNotNull { reasonWord(it, s) }.takeIf { it.isNotEmpty() }?.let {
                Text(it.joinToString(" · "), fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 8.dp))
            }
            g.options.forEach { WayCard(it, it.option.id == g.recommendedId, s) }
        }
    }
}
