package org.ekyatra.saathi.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import org.ekyatra.saathi.data.NearRanked
import org.ekyatra.saathi.data.NearResult
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.ui.theme.Tokens

//: "stay" is first because of who asks. A family forty hours from home needs
//: a bed before they need a pathology lab, and the backend offers a
//: dharamshala ahead of a hotel for the same reason it offers Jan Aushadhi
//: ahead of a pharmacy.
private val NEEDS = listOf("stay", "medicine", "tests", "equipment", "clinic")

private fun needWord(need: String, s: Strings) = when (need) {
    // The spends tab's own word for it, so the chip a family taps to find a
    // room and the category they file the receipt under read the same.
    "stay" -> s.budgetStay
    "medicine" -> s.nearMedicine
    "tests" -> s.nearTests
    "equipment" -> s.nearEquipment
    else -> s.nearClinic
}

private fun reasonWord(code: String, s: Strings) = when (code) {
    "open_round_the_clock" -> s.nearRoundClock
    "open_then" -> s.nearOpenThen
    "shut_then" -> s.nearShutThen
    "hours_unknown" -> s.nearHoursUnknown
    "government_price_generics" -> s.nearGovPrice
    else -> null
}

private fun distance(metres: Int) = if (metres < 1000) "$metres m" else "%.1f km".format(metres / 1000.0)

/** A tap-to-dial link. Dial, not call: the family presses the button themselves. */
internal fun dial(context: Context, phone: String) {
    runCatching {
        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + phone.filter { it.isDigit() || it == '+' }))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

@Composable
private fun Chip(label: String, on: Boolean, tag: String, onClick: () -> Unit) {
    Text(
        label,
        fontSize = 14.sp,
        fontWeight = FontWeight.Medium,
        color = if (on) Tokens.surface else Tokens.blue700,
        modifier = Modifier
            .testTag(tag)
            .clip(RoundedCornerShape(Tokens.radiusPill))
            .background(if (on) Tokens.blue600 else Tokens.surface)
            .border(1.dp, if (on) Tokens.blue600 else Tokens.line, RoundedCornerShape(Tokens.radiusPill))
            .clickable(onClick = onClick)
            .padding(14.dp, 8.dp),
    )
}

@Composable
private fun PlaceRow(r: NearRanked, s: Strings) {
    val context = LocalContext.current
    Column(
        Modifier.fillMaxWidth().padding(top = 10.dp).clip(RoundedCornerShape(Tokens.radiusMd))
            .border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusMd)).padding(12.dp).testTag("near-${r.place.id}"),
    ) {
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text(r.place.name, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink, modifier = Modifier.weight(1f))
            Text(distance(r.metres), fontSize = 14.sp, color = Tokens.ink3)
        }
        if (r.place.address.isNotBlank()) Text(r.place.address, fontSize = 13.sp, color = Tokens.ink3)
        val words = r.reasons.mapNotNull { reasonWord(it, s) }
        if (words.isNotEmpty()) {
            Text(
                words.joinToString(" · "), fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp),
                color = if (r.openThen == false) Tokens.critical else if (r.openThen == true) Tokens.go else Tokens.ink3,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            r.place.phone?.let { phone -> Chip(s.nearCall, false, "call-${r.place.id}") { dial(context, phone) } }
            Chip(s.nearDirections, false, "dir-${r.place.id}") {
                // Maps picks the mode the person usually travels by; the place's own id keeps it exact.
                val uri = Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${r.place.latitude},${r.place.longitude}" +
                    if (r.place.source == "google") "&destination_place_id=${r.place.id}" else "")
                runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            }
        }
        if (r.place.source == "demo") Text(s.nearDemo, fontSize = 11.sp, color = Tokens.critical, modifier = Modifier.padding(top = 4.dp))
    }
}

/**
 * Where to get what the journey needs, near the hospital or near home. These are
 * suggestions from a map service: the card says so, says to call before going,
 * and never claims a shop has anything.
 */
@Composable
fun NearYouCard(api: SaathiApi, patientId: String, s: Strings, onMap: () -> Unit = {}) {
    var need by remember { mutableStateOf("medicine") }
    var near by remember { mutableStateOf("hospital") }
    var result by remember { mutableStateOf<NearResult?>(null) }
    var failed by remember { mutableStateOf(false) }

    LaunchedEffect(need, near) {
        failed = false
        try {
            result = api.nearby(patientId, need, near)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            result = null; failed = true
        }
    }

    SaathiCard(Modifier.testTag("near-card")) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            GlyphBadge(Glyph.Home, Tokens.blue600, Tokens.blue100)
            Text(s.nearTitle, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
        }
        Chip(s.mapOpen, true, "near-map", onMap)
        NEEDS.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                pair.forEach { n -> Chip(needWord(n, s), need == n, "near-need-$n") { need = n } }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            Chip(s.nearHospital, near == "hospital", "near-at-hospital") { near = "hospital" }
            Chip(s.nearHome, near == "home", "near-at-home") { near = "home" }
        }
        if (failed) Text(s.nearCantLoad, fontSize = 13.sp, color = Tokens.critical, modifier = Modifier.padding(top = 8.dp))
        result?.let { r ->
            if (r.places.isEmpty()) Text(s.nearNone, fontSize = 14.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 8.dp))
            r.places.forEach { PlaceRow(it, s) }
            Text(s.nearConfirm, fontSize = 12.sp, color = Tokens.ink2, modifier = Modifier.padding(top = 10.dp))
            Text(s.nearRough, fontSize = 11.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 2.dp))
            if (r.source == "google") Text(s.nearPowered, fontSize = 11.sp, color = Tokens.ink3)
            if (r.source == "osm") Text(s.nearOsm, fontSize = 11.sp, color = Tokens.ink3)
        }
    }
}
