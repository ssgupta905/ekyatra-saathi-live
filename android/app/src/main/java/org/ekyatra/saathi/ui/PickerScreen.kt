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
import androidx.compose.foundation.layout.size
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
 * Which family is this phone? Signed in, the server lists only this person's own
 * (usually one, which opens by itself); with login off, the demo, the team picks
 * from all of them so every family can be tested.
 */
@Composable
fun PickerScreen(
    api: SaathiApi,
    signedIn: Boolean = false,
    autoPick: Boolean = false,
    onSignOut: () -> Unit = {},
    onPick: (String) -> Unit,
) {
    var patients by remember { mutableStateOf<List<PatientSummary>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }

    LaunchedEffect(attempt) {
        error = null
        try {
            patients = api.patients().sortedBy { if (it.id in Featured) Featured.indexOf(it.id) else Featured.size }
            patients?.singleOrNull()?.takeIf { autoPick }?.let { onPick(it.id) }
        } catch (e: ApiException) {
            error = e.message
        }
    }

    Column(Modifier.fillMaxSize().background(Tokens.plane).safeDrawingPadding()) {
        Column(
            Modifier
                .fillMaxWidth()
                .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(Tokens.nav, Tokens.blue700)))
                .padding(20.dp, 28.dp, 20.dp, 22.dp),
        ) {
            Box(
                Modifier.size(40.dp).background(Tokens.blue500, RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center,
            ) { Text("S", color = androidx.compose.ui.graphics.Color.White, fontWeight = FontWeight.Bold, fontSize = 22.sp) }
            Text("Saathi", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = androidx.compose.ui.graphics.Color.White, modifier = Modifier.padding(top = 12.dp))
            Text(if (signedIn) "Your family" else "Choose a family", fontSize = 16.sp, color = Tokens.navInk)
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

        if (signedIn) {
            Text(
                "Sign out",
                fontSize = 15.sp,
                color = Tokens.blue500,
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .clickable(onClick = onSignOut)
                    .padding(20.dp, 10.dp)
                    .testTag("sign-out"),
            )
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
            .padding(16.dp, 5.dp)
            .background(Tokens.surface, RoundedCornerShape(Tokens.radiusLg))
            .heightIn(min = 64.dp)
            .clickable(onClick = onClick)
            .testTag("family-${patient.id}")
            .padding(16.dp, 12.dp),
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
