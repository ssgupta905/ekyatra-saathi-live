package org.ekyatra.saathi.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.ekyatra.saathi.data.ApiException
import org.ekyatra.saathi.data.Transcript
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.ui.theme.Tokens
import org.ekyatra.saathi.voice.VoiceRecorder
import java.io.File

/**
 * How the family says something back: type it, or speak it.
 *
 * Voice is not a nice-to-have. A caregiver who cannot read their own script has no
 * other way in, so the mic is the same size as Send, not a small icon beside it.
 *
 * Speech and sending are deliberately two steps. Transcription hands back words and
 * nothing else; those words land in the box for the family to read and correct
 * before anything is sent. A mis-heard date in a script the operator cannot read is
 * not a mistake anyone downstream would catch.
 */
private enum class Phase { Idle, Recording, Transcribing, Sending }

@Composable
fun Composer(
    lang: Lang,
    s: Strings,
    onSend: suspend (String) -> Unit,
    onTranscribe: suspend (File) -> Transcript,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val recorder = remember { VoiceRecorder(context) }
    DisposableEffect(recorder) { onDispose { recorder.cancel() } }

    var text by rememberSaveable { mutableStateOf("") }
    var phase by remember { mutableStateOf(Phase.Idle) }
    var error by remember { mutableStateOf<String?>(null) }
    var fromVoice by remember { mutableStateOf(false) }

    fun begin() {
        if (recorder.start()) phase = Phase.Recording else error = "microphone unavailable"
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) begin() else error = "microphone permission was refused"
    }

    fun toggleRecording() {
        if (phase == Phase.Recording) {
            val recording = recorder.stop()
            if (recording == null) {
                phase = Phase.Idle
                error = "that recording was too short"
                return
            }
            phase = Phase.Transcribing
            scope.launch {
                try {
                    text = onTranscribe(recording).text
                    fromVoice = true
                } catch (e: ApiException) {
                    error = e.message
                } finally {
                    phase = Phase.Idle
                }
            }
        } else {
            error = null
            val granted = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            if (granted) begin() else permission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    fun send() {
        val body = text.trim()
        if (body.isEmpty() || phase != Phase.Idle) return
        phase = Phase.Sending
        error = null
        scope.launch {
            try {
                onSend(body)
                text = ""
                fromVoice = false
            } catch (e: ApiException) {
                error = e.message
            } finally {
                phase = Phase.Idle
            }
        }
    }

    val busy = phase == Phase.Sending || phase == Phase.Transcribing

    Column(
        Modifier
            .fillMaxWidth()
            .background(Tokens.surface)
            .padding(12.dp, 10.dp, 12.dp, 12.dp),
    ) {
        if (fromVoice && text.isNotEmpty()) {
            Text(s.checkBeforeSending, fontSize = 13.sp, color = Tokens.blue700, modifier = Modifier.padding(4.dp, 0.dp, 4.dp, 8.dp))
        }
        error?.let {
            Text(it, fontSize = 13.sp, color = Tokens.critical, modifier = Modifier.padding(4.dp, 0.dp, 4.dp, 8.dp).testTag("composer-error"))
        }

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val recording = phase == Phase.Recording
            Surface(
                shape = CircleShape,
                color = if (recording) Tokens.critical else Tokens.surface,
                border = BorderStroke(1.dp, if (recording) Tokens.critical else Tokens.line),
                modifier = Modifier
                    .size(44.dp)
                    .testTag("mic")
                    .clickable(enabled = !busy) { toggleRecording() },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    SaathiIcon(Glyph.Wave, if (recording) androidx.compose.ui.graphics.Color.White else Tokens.ink2, 18.dp)
                }
            }

            if (recording) {
                Row(
                    Modifier
                        .weight(1f)
                        .heightIn(min = 44.dp)
                        .background(Tokens.criticalTint, RoundedCornerShape(Tokens.radiusPill))
                        .padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(s.listening, fontSize = 15.sp, color = Tokens.critical)
                }
            } else {
                OutlinedTextField(
                    value = text,
                    onValueChange = {
                        text = it
                        fromVoice = false
                    },
                    modifier = Modifier.weight(1f).testTag("message-field"),
                    enabled = !busy,
                    singleLine = true,
                    shape = RoundedCornerShape(Tokens.radiusPill),
                    placeholder = {
                        Text(if (phase == Phase.Transcribing) s.transcribing else s.askPlaceholder, fontSize = 16.sp)
                    },
                    textStyle = androidx.compose.ui.text.TextStyle(fontSize = 16.sp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { send() }),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Tokens.blue500,
                        unfocusedBorderColor = Tokens.line,
                    ),
                )
            }

            val canSend = !busy && text.isNotBlank() && !recording
            Surface(
                shape = RoundedCornerShape(Tokens.radiusPill),
                color = if (canSend) Tokens.blue500 else Tokens.blue500.copy(alpha = 0.38f),
                modifier = Modifier
                    .heightIn(min = 44.dp)
                    .testTag("send")
                    .clickable(enabled = canSend) { send() },
            ) {
                Box(Modifier.heightIn(min = 44.dp).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                    if (phase == Phase.Sending) {
                        SaathiIcon(Glyph.Spark, androidx.compose.ui.graphics.Color.White, 15.dp)
                    } else {
                        Text(s.send, fontSize = 16.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.Medium, color = androidx.compose.ui.graphics.Color.White)
                    }
                }
            }
        }
    }
}
