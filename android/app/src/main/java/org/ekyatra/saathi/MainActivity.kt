package org.ekyatra.saathi

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.ui.FamilyScreen
import org.ekyatra.saathi.ui.FamilyViewModel
import org.ekyatra.saathi.ui.PickerScreen
import org.ekyatra.saathi.ui.theme.SaathiTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val api = SaathiApi(BuildConfig.API_BASE)
        setContent { SaathiTheme { App(api) } }
    }
}

@Composable
private fun App(api: SaathiApi) {
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    val patientId = selected

    if (patientId == null) {
        PickerScreen(api) { selected = it }
    } else {
        val vm: FamilyViewModel = viewModel(
            key = patientId,
            factory = viewModelFactory { initializer { FamilyViewModel(api, patientId) } },
        )
        FamilyScreen(vm) { selected = null }
    }
}
