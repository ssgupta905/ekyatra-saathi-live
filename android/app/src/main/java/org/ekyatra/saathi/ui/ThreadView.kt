package org.ekyatra.saathi.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.data.ThreadEntry
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.localTime
import org.ekyatra.saathi.ui.theme.Tokens

/**
 * One conversation, both directions.
 *
 * Not "your notifications" and "your replies" as two lists: a family does not
 * experience it that way, and reading a holding message directly above their own
 * reply to it is the entire reason to show it. Newest at the bottom, like every
 * messaging app anyone has ever used.
 *
 * A clinical question is shown with the note that a person will answer it. That is
 * not an apology for a limitation; it is the product working. Saathi never
 * answers a question about a result, and the family should be able to see that
 * their question was received and routed rather than ignored.
 *
 * Older messages keep the language they were sent in, and say so. A family that
 * switches to Bengali on Tuesday did not retroactively receive Monday's message
 * in Bengali, and rewriting the thread to pretend otherwise would make the one
 * record of what this family was actually told untrue.
 */
@Composable
fun ThreadView(entries: List<ThreadEntry>, lang: Lang, s: Strings) {
    if (entries.isEmpty()) return

    Column(Modifier.fillMaxWidth().padding(16.dp, 20.dp, 16.dp, 16.dp)) {
        Text(
            s.messages.uppercase(),
            fontSize = 12.sp,
            letterSpacing = 1.sp,
            color = Tokens.ink3,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val bubbleMax = maxWidth * 0.85f
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                for (entry in entries) {
                    if (entry.kind == "language") Divider(entry, s) else Bubble(entry, lang, s, bubbleMax)
                }
            }
        }
    }
}

/** The moment the family changed language, drawn as a divider: what makes a thread of two scripts read as a record. */
@Composable
private fun Divider(entry: ThreadEntry, s: Strings) {
    Text(
        "${s.languageChanged} · ${Lang.of(entry.language).endonym}",
        fontSize = 12.sp,
        color = Tokens.ink3,
        textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    )
}

@Composable
private fun Bubble(entry: ThreadEntry, lang: Lang, s: Strings, maxWidth: androidx.compose.ui.unit.Dp) {
    val mine = entry.direction == "from_family"
    val shape = RoundedCornerShape(
        topStart = 18.dp,
        topEnd = 18.dp,
        bottomStart = if (mine) 18.dp else 5.dp,
        bottomEnd = if (mine) 5.dp else 18.dp,
    )
    val background = when {
        entry.held -> Tokens.waitTint
        mine -> Tokens.blue500
        else -> Tokens.fillQuiet
    }
    val ink = if (mine && !entry.held) Color.White else Tokens.ink
    val sentIn = entry.language?.takeIf { it != lang.code }

    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        Column(
            Modifier
                .widthIn(max = maxWidth)
                .background(background, shape)
                .then(if (entry.held) Modifier.border(BorderStroke(1.dp, Tokens.wait), shape) else Modifier)
                .padding(13.dp, 10.dp),
        ) {
            Text(entry.body, fontSize = 16.sp, lineHeight = 22.sp, color = ink)
            Row(
                Modifier.padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val foot = ink.copy(alpha = 0.66f)
                Text(if (mine) s.you else "Saathi", fontSize = 11.sp, color = foot)
                Text(localTime(entry.sentAt, lang), fontSize = 11.sp, color = foot)
                if (sentIn != null) Text(Lang.of(sentIn).endonym, fontSize = 11.sp, color = foot)
            }
            if (entry.answerable == false) {
                Row(
                    Modifier.padding(top = 6.dp),
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    val note = if (mine && !entry.held) Color.White.copy(alpha = 0.86f) else Tokens.ink3
                    SaathiIcon(Glyph.Shield, note, 12.dp)
                    Text(s.aPersonWillReply, fontSize = 12.sp, color = note)
                }
            }
        }
    }
}
