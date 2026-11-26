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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.RailGuide
import org.ekyatra.saathi.data.WayBudget
import org.ekyatra.saathi.data.WayGuidance
import org.ekyatra.saathi.data.WayOptions
import org.ekyatra.saathi.data.WayStep
import org.ekyatra.saathi.data.WeighedWay
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localDateShort
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
        o.steps.filterNot { it.mode == "walk" && it.minutes == 0 }.forEach { StepLine(it, s) }
        if (o.source == "demo") Text(s.wayDemo, fontSize = 11.sp, color = Tokens.critical, modifier = Modifier.padding(top = 6.dp))
    }
}

/** "1 Dec, 08:00" on this phone's clock, in the family's own script. Null when there is no time. */
private fun visitWhen(iso: String?, lang: Lang): String? = runCatching {
    val local = OffsetDateTime.parse(iso!!).atZoneSameInstant(ZoneId.systemDefault())
    "${localDateShort(local.toLocalDate().toString(), lang)}, ${local.format(DateTimeFormatter.ofPattern("HH:mm"))}"
}.getOrNull()

/** "32 h" or "40 min": enough to compare ways, and digits read the same in every language. */
private fun duration(minutes: Int): String = if (minutes >= 90) "${(minutes + 30) / 60} h" else "$minutes min"

@Composable
private fun PillButton(text: String, primary: Boolean, tag: String, onClick: () -> Unit) {
    Text(
        text,
        fontSize = 14.sp,
        fontWeight = FontWeight.SemiBold,
        color = if (primary) Tokens.surface else Tokens.blue700,
        modifier = Modifier
            .padding(top = 8.dp)
            .testTag(tag)
            .clip(RoundedCornerShape(Tokens.radiusPill))
            .then(if (primary) Modifier.background(Tokens.blue600) else Modifier.border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusPill)))
            .clickable(onClick = onClick)
            .padding(16.dp, 10.dp),
    )
}

/**
 * The train, when a train is the realistic way. Both stations come with the
 * codes IRCTC asks for, because IRCTC takes no station or date from an outside
 * app: the family types them. It never names a train, a time or a fare, and says
 * why: Saathi cannot see them.
 */
@Composable
private fun RailCard(r: RailGuide, budget: WayBudget?, api: SaathiApi, patientId: String, s: Strings) {
    val context = LocalContext.current
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 10.dp)
            .clip(RoundedCornerShape(Tokens.radiusMd))
            .border(2.dp, Tokens.blue500, RoundedCornerShape(Tokens.radiusMd))
            .padding(12.dp)
            .testTag("rail-card"),
    ) {
        Text(s.trainBest, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Tokens.blue600)
        Text(
            "${r.origin.name} (${r.origin.code}) → ${r.to.name} (${r.to.code})",
            fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink,
            modifier = Modifier.padding(top = 4.dp),
        )
        r.allowDays?.let {
            Text(s.trainAllow.replace("{n}", it.toString()), fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 4.dp))
        }
        if (r.also.isNotEmpty()) {
            Text(
                s.trainAlso.replace("{list}", r.also.joinToString(", ") { "${it.name} (${it.code})" }),
                fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 2.dp),
            )
        }
        PillButton(s.openApp.replace("{app}", IRCTC_APP.name), primary = true, tag = "rail-irctc") {
            openPartnerApp(context, IRCTC_APP, "train")
        }
        if (r.statusUrl.isNotBlank()) {
            PillButton(s.trainStatus, primary = false, tag = "rail-status") { openWeb(context, r.statusUrl) }
        }
        Text(s.trainNote, fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 8.dp))
        FareCheck(budget, api, patientId, s)
    }
}

/** The monthly limit the family set, and what is left of it for the month they travel in. */
@Composable
private fun BudgetLine(b: WayBudget?, s: Strings) {
    val limit = b?.limitPaise
    if (b == null || limit == null) {
        Text(s.budgetNone, fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 6.dp).testTag("budget-none"))
        return
    }
    Text(
        s.budgetLine.replace("{limit}", rupees(limit)).replace("{left}", rupees(b.roomPaise ?: 0)),
        fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Tokens.ink2,
        modifier = Modifier.padding(top = 6.dp).testTag("budget-line"),
    )
}

/**
 * Whether the fare a family found fits what they said they can manage.
 *
 * The figure is theirs: typed from what they see in IRCTC, or one they already
 * told us, quoted back. Saathi has no fare of its own and does not make one up.
 * Over the limit it says so plainly and sends them to their navigator before
 * they book, with the railway-concession tip. A fare can be added to their
 * spends, where the family confirms it before it counts.
 */
@Composable
private fun FareCheck(budget: WayBudget?, api: SaathiApi, patientId: String, s: Strings) {
    val said = budget?.statedFarePaise
    var typed by remember(said) { mutableStateOf(said?.let { (it / 100).toString() }.orEmpty()) }
    var checked by remember(said) { mutableStateOf(said != null) }
    var added by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val fare = typed.toLongOrNull()?.takeIf { it > 0 }?.times(100)

    Column(Modifier.padding(top = 12.dp)) {
        said?.let { Text(s.fareSaid.replace("{fare}", rupees(it)), fontSize = 12.sp, color = Tokens.ink3) }
        OutlinedTextField(
            typed, { typed = it.filter(Char::isDigit).take(6); checked = false; added = false },
            singleLine = true, label = { Text(s.fareLabel) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp).testTag("fare-amount"),
        )
        if (fare != null && !checked) PillButton(s.fareCheck, primary = false, tag = "fare-check") { checked = true }
        if (checked && fare != null) {
            val room = budget?.roomPaise
            when {
                room == null -> Text(s.fareNoLimit, fontSize = 13.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 8.dp).testTag("fare-nolimit"))
                fare <= room -> Text(
                    s.fareFits.replace("{left}", rupees(room - fare)),
                    fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Tokens.go,
                    modifier = Modifier.padding(top = 8.dp).testTag("fare-fits"),
                )
                else -> Column(Modifier.padding(top = 8.dp)) {
                    Text(
                        s.fareOver.replace("{over}", rupees(fare - room)),
                        fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Tokens.critical,
                        modifier = Modifier.testTag("fare-over"),
                    )
                    Text(s.fareAsk, fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 2.dp))
                    Text(s.nudgeRail, fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 4.dp))
                }
            }
            if (!added) {
                PillButton(s.fareAdd, primary = true, tag = "fare-add") {
                    scope.launch { runCatching { api.addSpend(patientId, "", (fare / 100).toInt(), "travel") }.onSuccess { added = true } }
                }
            } else {
                Text(s.fareAdded, fontSize = 13.sp, color = Tokens.go, modifier = Modifier.padding(top = 8.dp).testTag("fare-added"))
            }
        }
    }
}

/** A way that is not the best: one line, with what it costs the family in time. */
@Composable
private fun OtherWay(w: WeighedWay, s: Strings) {
    val o = w.option
    val steps = o.steps.filter { it.mode != "walk" }
    val what = steps.joinToString(" + ") { st -> "${modeWord(st.mode, s)} ${st.line.orEmpty()}".trim() }.ifBlank { s.modeStep }
    Text(
        "$what · ${duration(o.minutes)}" + (w.leaveBy?.let { clock(it) }?.takeIf { it.isNotBlank() }?.let { " · " + s.wayLeaveBy.replace("{t}", it) } ?: ""),
        fontSize = 13.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 6.dp),
    )
}

/**
 * How to get through one leg, loaded as the screen opens and again whenever the
 * plan's travel day changes, so what a family sees is what the hospital holds
 * now. It leads with the one way we suggest, then the train when that is the
 * realistic choice, and keeps the rest a tap away. Nothing here invents a fare:
 * with none given it says the cost is not known.
 */
@Composable
fun LegGuide(api: SaathiApi, patientId: String, leg: String, refreshKey: String?, lang: Lang, s: Strings) {
    var typed by remember { mutableStateOf("") }
    var origin by remember { mutableStateOf("") }
    var editing by remember { mutableStateOf(false) }
    var showOthers by remember { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    var loaded by remember { mutableStateOf<WayOptions?>(null) }
    var failed by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(true) }

    LaunchedEffect(patientId, leg, origin, refreshKey, attempt) {
        busy = true; failed = false
        try {
            loaded = api.wayOptions(patientId, leg, origin)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            failed = true
        } finally {
            busy = false
        }
    }

    Column(Modifier.padding(top = 8.dp).testTag("leg-$leg")) {
        if (busy && loaded == null) Text(s.legLoading, fontSize = 13.sp, color = Tokens.ink3)
        if (failed) {
            Text(s.wayCantLoad, fontSize = 13.sp, color = Tokens.critical)
            PillButton(s.legRetry, primary = false, tag = "leg-retry-$leg") { attempt++ }
        }
        val data = loaded ?: return@Column
        visitWhen(data.arriveBy, lang)?.let {
            Text(s.legVisit.replace("{when}", it), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Tokens.ink)
        }
        if (leg == "near") {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 4.dp)) {
                Text(s.legFrom.replace("{place}", data.originUsed ?: origin), fontSize = 13.sp, color = Tokens.ink2)
                Text(
                    s.legChange, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Tokens.blue700,
                    modifier = Modifier.testTag("leg-change").clickable { editing = !editing },
                )
            }
            if (editing) {
                OutlinedTextField(
                    typed, { typed = it }, singleLine = true, label = { Text(s.wayFrom) },
                    modifier = Modifier.fillMaxWidth().padding(top = 6.dp).testTag("way-origin"),
                )
                PillButton(s.wayShow, primary = true, tag = "way-show-near") {
                    if (typed.isNotBlank()) { origin = typed.trim(); editing = false }
                }
            }
        }
        if (leg == "far") BudgetLine(data.budget, s)
        data.rail?.let { RailCard(it, data.budget, api, patientId, s) }
        val options = data.guidance.options
        if (data.rail != null) {
            // The car is only context here: the train is the suggestion.
            options.firstOrNull()?.let {
                Text(
                    s.byRoad.replace("{t}", duration(it.option.minutes)),
                    fontSize = 13.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 8.dp),
                )
            }
        } else {
            data.guidance.reasons.filter { it != "cost_unknown" }.mapNotNull { reasonWord(it, s) }.takeIf { it.isNotEmpty() }?.let {
                Text(it.joinToString(" · "), fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 6.dp))
            }
            val best = options.firstOrNull { it.option.id == data.guidance.recommendedId } ?: options.firstOrNull()
            best?.let { WayCard(it, true, s) }
            val rest = options.filter { it !== best }
            if (rest.isNotEmpty()) {
                Text(
                    s.legOther + (if (showOthers) " ▲" else " ▼"),
                    fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Tokens.blue700,
                    modifier = Modifier.padding(top = 10.dp).testTag("leg-others-$leg").clickable { showOthers = !showOthers },
                )
                if (showOthers) rest.forEach { OtherWay(it, s) }
            }
        }
    }
}
