package org.ekyatra.saathi.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.FamilyHome
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localDate
import org.ekyatra.saathi.ui.theme.Tokens
import org.ekyatra.saathi.voice.Speaker

/**
 * The whole screen, really. Everything else on the family app is detail.
 *
 * One word, one date, one sentence, in that order of size — because the question
 * a family opens this app with is "do we get on the bus or not", and an answer
 * they have to read twice has failed. The word is a label for the plan's
 * decision; the sentence is the message the language layer wrote and the guard
 * passed. If the guard held it, the sentence is replaced by "someone will call
 * you", which is true, rather than by a substitute invented here.
 */

private fun word(decision: String?, s: Strings): String = when (decision) {
    "go" -> s.come
    "wait" -> s.wait
    else -> s.notYet
}

private data class Band(val background: Color, val word: Color)

private fun band(decision: String?): Band = when (decision) {
    "go" -> Band(Tokens.goTint, Tokens.go)
    "wait", "replan" -> Band(Tokens.waitTint, Tokens.wait)
    "uncertain" -> Band(Tokens.uncertainTint, Tokens.uncertain)
    else -> Band(Tokens.sunken, Tokens.ink4)
}

@Composable
fun Verdict(home: FamilyHome?, lang: Lang, s: Strings, speaker: Speaker) {
    val decision = home?.decision
    if (home == null || decision == null) {
        Column(
            Modifier.fillMaxWidth().background(Tokens.sunken).padding(22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("·", fontSize = 40.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink4)
            Text(s.noPlanYet, fontSize = 17.sp, color = Tokens.ink2, textAlign = TextAlign.Center)
        }
        return
    }

    val colors = band(decision)
    val held = home.message?.held ?: false
    val sentence = if (held) s.personCalling else home.message?.body

    Column(
        Modifier.fillMaxWidth().background(colors.background).padding(22.dp, 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            word(decision, s),
            fontSize = 40.sp,
            lineHeight = 44.sp,
            fontWeight = FontWeight.SemiBold,
            color = colors.word,
        )

        if (decision == "go" && home.travelOn != null) {
            Text(
                s.travelOn.uppercase(),
                fontSize = 12.sp,
                letterSpacing = 1.sp,
                color = Tokens.ink3,
            )
            Text(
                localDate(home.travelOn, lang),
                fontSize = 22.sp,
                fontWeight = FontWeight.Medium,
                color = Tokens.ink,
            )
        }

        if (sentence != null) {
            Text(
                sentence,
                fontSize = 17.sp,
                lineHeight = 25.sp,
                color = if (held) Tokens.ink3 else Tokens.ink2,
                fontStyle = if (held) FontStyle.Italic else FontStyle.Normal,
                textAlign = TextAlign.Center,
            )
            ReadAloud(sentence, lang, s, speaker)
        }
    }
}

/** Read it aloud. Same prominence as the text, because for a caregiver who cannot read this script it *is* the text. */
@Composable
internal fun ReadAloud(text: String, lang: Lang, s: Strings, speaker: Speaker) {
    var speaking by remember { mutableStateOf(false) }
    var noVoice by remember(lang) { mutableStateOf(false) }

    val border = if (speaking) Tokens.blue500 else Tokens.line
    Surface(
        shape = RoundedCornerShape(Tokens.radiusPill),
        color = if (speaking) Tokens.blue100 else Tokens.surface,
        border = BorderStroke(1.dp, border),
        modifier = Modifier
            .heightIn(min = 44.dp)
            .clickable {
                if (speaking) {
                    speaker.stop()
                    speaking = false
                } else {
                    when (speaker.speak(text, lang) { speaking = false }) {
                        Speaker.Result.Started -> { speaking = true; noVoice = false }
                        Speaker.Result.NoVoice -> noVoice = true
                        Speaker.Result.NotReady -> Unit
                    }
                }
            },
    ) {
        Row(
            Modifier.padding(PaddingValues(horizontal = 16.dp, vertical = 9.dp)),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            SaathiIcon(Glyph.Speaker, if (speaking) Tokens.blue700 else Tokens.ink, 18.dp)
            Text(
                if (speaking) s.reading else s.speak,
                fontSize = 15.sp,
                color = if (speaking) Tokens.blue700 else Tokens.ink,
            )
        }
    }
    if (noVoice) {
        Text(
            "This phone has no ${lang.label} voice installed.",
            fontSize = 13.sp,
            color = Tokens.ink3,
            textAlign = TextAlign.Center,
        )
    }
}
