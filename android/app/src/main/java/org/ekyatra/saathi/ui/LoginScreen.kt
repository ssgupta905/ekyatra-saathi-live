package org.ekyatra.saathi.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.ekyatra.saathi.data.ApiException
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.requestOtp
import org.ekyatra.saathi.data.verifyOtp
import org.ekyatra.saathi.ui.theme.Tokens

/**
 * How a family gets in: the phone number the hospital has for them, then the
 * code sent to it. Whether the number is on record is never said, so a stranger
 * learns nothing by trying numbers.
 */
@Composable
fun LoginScreen(api: SaathiApi, onSignedIn: () -> Unit) {
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var asked by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun run(block: suspend () -> Unit) {
        busy = true
        error = null
        scope.launch {
            try {
                block()
            } catch (e: ApiException) {
                error = if (e.status == 401) "That code is wrong or has expired." else e.message
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(Tokens.blue100, Tokens.surface)))
            .safeDrawingPadding()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        androidx.compose.foundation.layout.Box(
            Modifier.padding(bottom = 18.dp).size(52.dp).background(Tokens.blue500, RoundedCornerShape(16.dp)),
            contentAlignment = Alignment.Center,
        ) { Text("S", color = androidx.compose.ui.graphics.Color.White, fontWeight = FontWeight.Bold, fontSize = 28.sp) }
        Text("Saathi", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Tokens.ink)
        Text(
            if (asked) "Enter the code we sent" else "Your phone number",
            fontSize = 16.sp,
            color = Tokens.ink3,
            modifier = Modifier.padding(top = 4.dp, bottom = 20.dp),
        )

        if (!asked) {
            OutlinedTextField(
                value = phone,
                onValueChange = { phone = it },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth().testTag("login-phone"),
            )
            Text(
                "We send a code to the number the hospital has for you. If it is on record, it arrives.",
                fontSize = 13.sp,
                color = Tokens.ink3,
                modifier = Modifier.padding(top = 10.dp, bottom = 16.dp),
            )
            Action("Send me a code", enabled = !busy && phone.trim().length >= 5, tag = "login-send") {
                run {
                    api.requestOtp(phone.trim())
                    asked = true
                }
            }
        } else {
            OutlinedTextField(
                value = code,
                onValueChange = { code = it },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth().testTag("login-code"),
            )
            Column(Modifier.padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Action("Continue", enabled = !busy && code.trim().length >= 4, tag = "login-verify") {
                    run {
                        api.verifyOtp(phone.trim(), code.trim())
                        onSignedIn()
                    }
                }
                Text(
                    "Use a different number",
                    fontSize = 15.sp,
                    color = Tokens.blue500,
                    modifier = Modifier
                        .heightIn(min = 44.dp)
                        .clickable { asked = false; code = ""; error = null }
                        .padding(vertical = 10.dp),
                )
            }
        }

        error?.let {
            Text(it, fontSize = 14.sp, color = Tokens.critical, modifier = Modifier.padding(top = 12.dp).testTag("login-error"))
        }
    }
}

@Composable
private fun Action(label: String, enabled: Boolean, tag: String, onClick: () -> Unit) {
    Text(
        label,
        color = Tokens.surface,
        fontSize = 16.sp,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .background(if (enabled) Tokens.blue500 else Tokens.blue300, RoundedCornerShape(Tokens.radiusPill))
            .then(if (enabled) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(vertical = 13.dp)
            .testTag(tag),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}
