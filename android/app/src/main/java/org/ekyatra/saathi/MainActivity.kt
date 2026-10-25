package org.ekyatra.saathi

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.clickable
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import org.ekyatra.saathi.data.PrefsTokenStore
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.authConfig
import org.ekyatra.saathi.data.me
import org.ekyatra.saathi.data.signOut
import org.ekyatra.saathi.ui.FamilyScreen
import org.ekyatra.saathi.ui.FamilyViewModel
import org.ekyatra.saathi.ui.LoginScreen
import org.ekyatra.saathi.ui.PickerScreen
import org.ekyatra.saathi.ui.theme.SaathiTheme
import org.ekyatra.saathi.ui.theme.Tokens

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val api = SaathiApi(BuildConfig.API_BASE, tokens = PrefsTokenStore(this))
        setContent { SaathiTheme { App(api) } }
    }
}

/** Where the app is in getting a person in. */
private enum class Gate { Checking, Offline, SignedOut, Open, SignedIn }

@Composable
private fun App(api: SaathiApi) {
    var gate by remember { mutableStateOf(Gate.Checking) }
    var attempt by remember { mutableIntStateOf(0) }
    var failure by remember { mutableStateOf("") }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    // One family opens by itself the first time; coming back to the list is the person's choice.
    var autoPick by rememberSaveable { mutableStateOf(true) }

    // The server stopping trusting the token (expired, revoked) ends up here.
    LaunchedEffect(api) { api.onUnauthorized = { gate = Gate.SignedOut } }

    LaunchedEffect(attempt) {
        gate = Gate.Checking
        try {
            gate = when {
                !api.authConfig().required -> Gate.Open
                api.tokens.get() == null -> Gate.SignedOut
                else -> runCatching { api.me() }.fold({ Gate.SignedIn }, { Gate.SignedOut })
            }
        } catch (e: Exception) {
            failure = e.message ?: "could not reach the server"
            gate = Gate.Offline
        }
    }

    when (gate) {
        Gate.Checking -> Message("…")
        Gate.Offline -> Column(Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp)) {
            Text(failure, fontSize = 14.sp, color = Tokens.critical)
            Text(
                "Try again",
                fontSize = 16.sp,
                color = Tokens.blue500,
                modifier = Modifier.clickable { attempt++ }.padding(vertical = 14.dp),
            )
        }
        Gate.SignedOut -> LoginScreen(api) { gate = Gate.SignedIn }
        Gate.Open, Gate.SignedIn -> {
            val patientId = selected
            val signedIn = gate == Gate.SignedIn
            val leave = { selected = null; autoPick = false }
            if (patientId == null) {
                PickerScreen(
                    api,
                    signedIn = signedIn,
                    autoPick = signedIn && autoPick,
                    onSignOut = { api.signOut(); selected = null; autoPick = true; gate = Gate.SignedOut },
                ) { selected = it }
            } else {
                val vm: FamilyViewModel = viewModel(
                    key = patientId,
                    factory = viewModelFactory { initializer { FamilyViewModel(api, patientId) } },
                )
                FamilyScreen(vm, leave)
            }
        }
    }
}

@Composable
private fun Message(text: String) {
    Text(text, fontSize = 16.sp, color = Tokens.ink3, modifier = Modifier.padding(24.dp).safeDrawingPadding())
}
