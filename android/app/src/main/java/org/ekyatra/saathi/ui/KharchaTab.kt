package org.ekyatra.saathi.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.Bookable
import org.ekyatra.saathi.data.Kharcha
import org.ekyatra.saathi.data.MonthOutlook
import org.ekyatra.saathi.data.SpendEntry
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.ui.theme.Tokens
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.TextStyle
import java.util.Locale

private val CATEGORIES = listOf("travel", "stay", "food", "medicine", "hospital", "other")

/** Whole rupees from paise, in the family's own grouping (₹1,23,456 in India). */
internal fun rupees(paise: Long): String {
    val fmt = NumberFormat.getCurrencyInstance(Locale("en", "IN")).apply { maximumFractionDigits = 0 }
    return fmt.format(paise / 100)
}

internal fun monthName(month: String, lang: Lang): String = runCatching {
    LocalDate.parse(month).month.getDisplayName(TextStyle.FULL, Locale(lang.code))
}.getOrDefault(month)

private fun categoryWord(code: String, s: Strings): String = when (code) {
    "travel" -> s.catTravel
    "stay" -> s.catStay
    "food" -> s.catFood
    "medicine" -> s.catMedicine
    "hospital" -> s.catHospital
    else -> s.catOther
}

private fun nudgeWord(kind: String, s: Strings): String? = when (kind) {
    "stay_costs_more" -> s.nudgeStay
    "scheme_may_cover" -> s.nudgeScheme
    "rail_concession" -> s.nudgeRail
    "over_what_you_said" -> s.nudgeOver
    else -> null
}

@Composable
fun KharchaTab(
    books: Kharcha?,
    error: String?,
    lang: Lang,
    s: Strings,
    act: (failed: String, work: suspend () -> Unit) -> Unit,
    api: org.ekyatra.saathi.data.SaathiApi,
    patientId: String,
) {
    val context = LocalContext.current
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).testTag("kharcha"),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (books == null) {
            SaathiCard { Text(s.kharchaNothingYet, color = Tokens.ink3, fontSize = 15.sp) }
            return@Column
        }
        if (error != null) {
            Text(
                error,
                color = Tokens.critical,
                fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth().background(Tokens.criticalTint, RoundedCornerShape(Tokens.radiusMd)).padding(12.dp),
            )
        }

        for (nudge in books.nudges) {
            val text = nudgeWord(nudge.kind, s) ?: continue
            SaathiCard {
                Text(
                    listOfNotNull(text, nudge.organisationName).joinToString(" · "),
                    color = Tokens.wait,
                    fontSize = 15.sp,
                )
            }
        }

        for (offer in books.bookable) BookCard(offer, s) { share ->
            act(s.kharchaCouldNotRead) { api.book(patientId, offer.itemId, share) }
        }

        for (entry in books.payable) PayCard(entry, s) {
            act(s.kharchaCouldNotRead) {
                api.payLink(patientId, entry.id)?.let {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            }
        }

        for (entry in books.toConfirm) {
            SaathiCard {
                Text(s.kharchaIsThisRight, color = Tokens.ink3, fontSize = 13.sp)
                Text(
                    "${rupees(entry.amountPaise)} · ${categoryWord(entry.category, s)}",
                    fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink,
                )
                entry.statedIn?.let { Text("${s.kharchaYourWords}: $it", color = Tokens.ink3, fontSize = 13.sp) }
                Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Pill(s.kharchaYes, true, Modifier.weight(1f)) { act(s.kharchaCouldNotRead) { api.confirmSpend(patientId, entry.id) } }
                    Pill(s.kharchaNo, false, Modifier.weight(1f)) { act(s.kharchaCouldNotRead) { api.removeSpend(patientId, entry.id) } }
                }
            }
        }

        books.months.forEachIndexed { i, m -> MonthCard(m, i == 0, lang, s) }
        if (books.months.size == 2) Chart(books.months, lang, s)

        books.limit?.let {
            SaathiCard { Text("${s.kharchaLimit}: ${rupees(it.monthlyPaise)}", color = Tokens.ink, fontSize = 15.sp) }
        }

        AddSpend(s) { text, amount, category ->
            act(s.kharchaCouldNotRead) { api.addSpend(patientId, text, amount, category) }
        }
        LimitForm(s) { rupeesIn -> act(s.kharchaCouldNotRead) { api.setLimit(patientId, rupeesIn) } }
    }
}

@Composable
private fun Pill(label: String, primary: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier
            .background(if (primary) Tokens.blue600 else Tokens.fillQuiet, RoundedCornerShape(Tokens.radiusPill))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (primary) Tokens.surface else Tokens.ink2, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
    }
}

@Composable
private fun BookCard(offer: Bookable, s: Strings, onBook: (Boolean) -> Unit) {
    var share by remember { mutableStateOf(false) }
    SaathiCard {
        Text(s.kharchaReadyToBook, color = Tokens.ink3, fontSize = 13.sp)
        Text(
            listOfNotNull(offer.provider.ifBlank { null }, offer.amountPaise?.let(::rupees)).joinToString(" · "),
            fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink,
        )
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(share, { share = it })
            Text(s.kharchaShareContact, color = Tokens.ink2, fontSize = 14.sp)
        }
        Pill(s.kharchaBook, share, Modifier.fillMaxWidth()) { if (share) onBook(true) }
    }
}

@Composable
private fun PayCard(entry: SpendEntry, s: Strings, onPay: () -> Unit) {
    SaathiCard {
        Text(s.kharchaToPay, color = Tokens.ink3, fontSize = 13.sp)
        Text(
            listOfNotNull(entry.party, rupees(entry.amountPaise)).joinToString(" · "),
            fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink,
        )
        Box(Modifier.height(8.dp))
        Pill(s.kharchaPay, true, Modifier.fillMaxWidth(), onPay)
    }
}

@Composable
private fun MonthCard(m: MonthOutlook, current: Boolean, lang: Lang, s: Strings) {
    SaathiCard {
        Text(
            "${if (current) s.kharchaThisMonth else s.kharchaNextMonth} · ${monthName(m.month, lang)}",
            color = Tokens.ink3, fontSize = 13.sp,
        )
        Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Figure(s.kharchaSpent, rupees(m.spentPaise), Modifier.weight(1f))
            Figure(s.kharchaBooked, rupees(m.bookedPaise), Modifier.weight(1f))
            Figure(s.kharchaExpected, m.expectedPaise?.let(::rupees) ?: "—", Modifier.weight(1f))
        }
        if (m.visitsAhead.isEmpty()) {
            Text(s.kharchaNoVisitsAhead, color = Tokens.ink3, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
        } else if (m.expectedPaise == null) {
            // No figure is made up: nothing recorded to go on means we say so.
            Text(s.kharchaCannotSayYet, color = Tokens.uncertain, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
        }
        for ((code, paise) in m.byCategory) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(categoryWord(code, s), color = Tokens.ink2, fontSize = 15.sp)
                Text(rupees(paise), color = Tokens.ink, fontSize = 15.sp, fontWeight = FontWeight.Medium)
            }
        }
        // Why this number: the working, with the count of visits it was drawn from.
        for (line in m.lines.filter { it.amountPaise != null && it.visitsUsed > 0 }) {
            Text(
                "${categoryWord(line.category, s)}: ${s.kharchaBasedOnVisits.replace("{n}", line.visitsUsed.toString())}",
                color = Tokens.ink4, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun Figure(label: String, value: String, modifier: Modifier) {
    Column(modifier) {
        Text(label, color = Tokens.ink3, fontSize = 12.sp)
        Text(value, color = Tokens.ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
    }
}

/** Two months side by side: spent, booked and expected stacked, heights to scale. */
@Composable
private fun Chart(months: List<MonthOutlook>, lang: Lang, s: Strings) {
    val top = months.maxOf { it.spentPaise + it.bookedPaise + (it.expectedPaise ?: 0) }.coerceAtLeast(1)
    SaathiCard {
        Row(Modifier.fillMaxWidth().height(120.dp), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.Bottom) {
            for (m in months) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Column(Modifier.width(56.dp), verticalArrangement = Arrangement.Bottom) {
                        for ((value, color) in listOf(
                            (m.expectedPaise ?: 0L) to Tokens.blue200,
                            m.bookedPaise to Tokens.blue400,
                            m.spentPaise to Tokens.blue700,
                        )) {
                            if (value > 0) Box(Modifier.fillMaxWidth().height((88f * value / top).dp).background(color))
                        }
                    }
                    Text(monthName(m.month, lang), fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 4.dp))
                }
            }
        }
        Text(
            "${s.kharchaSpent} · ${s.kharchaBooked} · ${s.kharchaExpected}",
            color = Tokens.ink4, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
        )
    }
}

@Composable
private fun AddSpend(s: Strings, onSave: (String, Int?, String?) -> Unit) {
    var words by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var category by remember { mutableStateOf<String?>(null) }
    SaathiCard {
        Text(s.kharchaAdd, fontWeight = FontWeight.SemiBold, color = Tokens.ink, fontSize = 16.sp)
        OutlinedTextField(
            words, { words = it }, label = { Text(s.kharchaAddHint) },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("spend-words"),
        )
        OutlinedTextField(
            amount, { amount = it.filter(Char::isDigit).take(7) }, label = { Text(s.kharchaAmount) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("spend-amount"),
        )
        Text(s.kharchaKind, color = Tokens.ink3, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
        CATEGORIES.chunked(3).forEach { row ->
            Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (code in row) {
                    val on = category == code
                    Box(
                        Modifier
                            .background(if (on) Tokens.blue100 else Tokens.fillQuiet, RoundedCornerShape(Tokens.radiusPill))
                            .clickable { category = if (on) null else code }
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                    ) { Text(categoryWord(code, s), color = if (on) Tokens.blue700 else Tokens.ink2, fontSize = 14.sp) }
                }
            }
        }
        Box(Modifier.height(10.dp))
        Pill(s.kharchaSave, words.isNotBlank() || amount.isNotBlank(), Modifier.fillMaxWidth()) {
            if (words.isNotBlank() || amount.isNotBlank()) {
                onSave(words.trim(), amount.toIntOrNull(), category)
                words = ""; amount = ""; category = null
            }
        }
    }
}

@Composable
private fun LimitForm(s: Strings, onSave: (Int) -> Unit) {
    var amount by remember { mutableStateOf("") }
    SaathiCard {
        Text(s.kharchaLimit, fontWeight = FontWeight.SemiBold, color = Tokens.ink, fontSize = 16.sp)
        Text(s.kharchaLimitHint, color = Tokens.ink3, fontSize = 13.sp)
        OutlinedTextField(
            amount, { amount = it.filter(Char::isDigit).take(7) }, label = { Text(s.kharchaAmount) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("limit-amount"),
        )
        Box(Modifier.height(10.dp))
        Pill(s.kharchaLimitSave, amount.isNotBlank(), Modifier.fillMaxWidth()) {
            amount.toIntOrNull()?.let { onSave(it); amount = "" }
        }
    }
}
