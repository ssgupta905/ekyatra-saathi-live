package org.ekyatra.saathi.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.ApiException
import org.ekyatra.saathi.data.PatientSummary
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.ui.theme.Tokens

/** The two families the scripted demo follows, listed first. */
private val Featured = listOf("P-SHAMBHU", "P-ANITA")

/**
 * Which family is this phone? A stand-in until login exists: in a pilot the family
 * arrives from a link in their message, and sees only their own plan. Here the
 * team picks one, so every family can be tested.
 */
@Composable
fun PickerScreen(api: SaathiApi, onPick: (String) -> Unit) {
    var patients by remember { mutableStateOf<List<PatientSummary>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }

    LaunchedEffect(attempt) {
        error = null
        try {
            patients = api.patients().sortedBy { if (it.id in Featured) Featured.indexOf(it.id) else Featured.size }
        } catch (e: ApiException) {
            error = e.message
        }
    }

    Column(Modifier.fillMaxSize().background(Tokens.surface).safeDrawingPadding()) {
        Column(Modifier.padding(20.dp, 24.dp, 20.dp, 12.dp)) {
            Text("Saathi", fontSize = 30.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
            Text("Choose a family", fontSize = 16.sp, color = Tokens.ink3)
        }

        Box(Modifier.weight(1f)) {
            val list = patients
            when {
                error != null -> Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(error ?: "", fontSize = 14.sp, color = Tokens.critical, modifier = Modifier.testTag("picker-error"))
                    Text(
                        "Try again",
                        fontSize = 16.sp,
                        color = Tokens.blue500,
                        modifier = Modifier.heightIn(min = 44.dp).clickable { attempt++ }.padding(vertical = 10.dp),
                    )
                }
                list == null -> Text("…", fontSize = 16.sp, color = Tokens.ink3, modifier = Modifier.padding(20.dp))
                else -> LazyColumn(Modifier.testTag("family-list")) {
                    items(list, key = { it.id }) { patient -> FamilyRow(patient) { onPick(patient.id) } }
                }
            }
        }

        Text(
            api.baseUrl,
            fontSize = 11.sp,
            color = Tokens.ink4,
            modifier = Modifier.fillMaxWidth().padding(20.dp, 8.dp, 20.dp, 12.dp),
        )
    }
}

@Composable
private fun FamilyRow(patient: PatientSummary, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .clickable(onClick = onClick)
            .testTag("family-${patient.id}")
            .padding(20.dp, 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column {
            Text(patient.id, fontSize = 17.sp, color = Tokens.ink)
            Text("${patient.district} · ${"%.0f".format(patient.distanceKm)} km", fontSize = 14.sp, color = Tokens.ink3)
        }
        Text(
            Lang.of(patient.language).endonym,
            fontSize = 13.sp,
            color = Tokens.ink3,
            modifier = Modifier.background(Tokens.fillQuiet, RoundedCornerShape(Tokens.radiusPill)).padding(10.dp, 4.dp),
        )
    }
}
