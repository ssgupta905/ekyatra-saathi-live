package org.ekyatra.saathi.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.ekyatra.saathi.data.workingFor
import org.ekyatra.saathi.i18n.Lang
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.i18n.Translations
import org.ekyatra.saathi.ui.theme.Tokens
import org.ekyatra.saathi.voice.rememberSpeaker

/**
 * The family's screen. A phone, not a card in a grid: one column, one thumb, one
 * hand, daylight. The answer stays put. Whichever tab is open, the family can
 * always see whether to travel without going looking for it.
 *
 * Everything here reacts to the same event stream the hospital's screens watch.
 * When the hospital's day goes wrong, this screen changes while the family is
 * looking at it, and says so.
 */
@Composable
fun FamilyScreen(vm: FamilyViewModel, onBack: () -> Unit) {
    val ui by vm.state.collectAsStateWithLifecycle()
    val lang = Lang.of(ui.home?.patient?.language)
    val s = Translations.of(lang)
    val speaker = rememberSpeaker()
    val scroll = rememberScrollState()
    val messageCount = ui.thread?.thread?.size ?: 0

    BackHandler(onBack = onBack)

    // Stick to the newest message: wait one frame so the new bubble has been laid out.
    LaunchedEffect(ui.tab, messageCount) {
        if (ui.tab == Tab.MESSAGES) {
            withFrameNanos { }
            scroll.scrollTo(scroll.maxValue)
        }
    }

    Column(Modifier.fillMaxSize().background(Tokens.surface).safeDrawingPadding()) {
        Header(ui, lang, onBack, vm::chooseLanguage)

        val work = ui.live.workingFor(vm.patientId)
        if (work.isNotEmpty() || ui.switching) {
            Row(
                Modifier.fillMaxWidth().background(Tokens.blue100).padding(16.dp, 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                SaathiIcon(Glyph.Spark, Tokens.blue700, 13.dp)
                Text(
                    if (ui.switching) s.working else (work.firstOrNull()?.task ?: s.working),
                    fontSize = 14.sp,
                    color = Tokens.blue700,
                )
            }
        }

        Verdict(ui.home, lang, s, speaker)
        Tabs(ui.tab, messageCount, s, vm::selectTab)

        Column(Modifier.weight(1f).verticalScroll(scroll)) {
            ui.error?.let {
                Text(
                    it,
                    fontSize = 14.sp,
                    color = Tokens.critical,
                    modifier = Modifier
                        .padding(16.dp, 12.dp)
                        .fillMaxWidth()
                        .background(Tokens.criticalTint, RoundedCornerShape(Tokens.radiusMd))
                        .padding(12.dp, 10.dp)
                        .testTag("error"),
                )
            }

            if (ui.tab == Tab.PLAN) {
                Why(ui.home?.waitingFor ?: emptyList(), lang, s)
                PlanStrip(ui.home?.steps ?: emptyList(), lang, s)
                ui.home?.let { home ->
                    val hours = home.patient.hoursEachWay?.let { " · ${"%.0f".format(it)} ${s.hoursEachWay}" } ?: ""
                    Footnote("${"%.0f".format(home.patient.distanceKm)} ${s.kmAway}$hours")
                }
            } else {
                ThreadView(ui.thread?.thread ?: emptyList(), lang, s)
            }

            Row(
                Modifier.fillMaxWidth().padding(16.dp, 14.dp, 16.dp, 20.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SaathiIcon(Glyph.Shield, Tokens.ink4, 12.dp)
                Text(
                    "  " + if (lang == Lang.EN) "Travel and appointments only. Saathi never discusses results." else s.aPersonWillReply,
                    fontSize = 12.sp,
                    color = Tokens.ink4,
                )
            }
        }

        Composer(
            lang = lang,
            s = s,
            onSend = vm::send,
            onTranscribe = { vm.transcribe(it, lang) },
        )
    }
}

@Composable
private fun Footnote(text: String) {
    Text(
        text,
        fontSize = 12.sp,
        color = Tokens.ink4,
        modifier = Modifier.fillMaxWidth().padding(16.dp, 14.dp, 16.dp, 0.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

@Composable
private fun Header(
    ui: FamilyUiState,
    lang: Lang,
    onBack: () -> Unit,
    onLanguage: (Lang) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(4.dp, 8.dp, 12.dp, 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(44.dp).clickable(onClick = onBack).testTag("back"),
            contentAlignment = Alignment.Center,
        ) { SaathiIcon(Glyph.Back, Tokens.ink2, 20.dp) }

        Column(Modifier.weight(1f)) {
            Text("Saathi", fontSize = 19.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
            ui.home?.let {
                Text(it.patient.district, fontSize = 13.sp, color = Tokens.ink3, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            for (option in Lang.entries) {
                val selected = option == lang
                Text(
                    option.endonym,
                    fontSize = 14.sp,
                    fontWeight = if (selected) FontWeight.Medium else FontWeight.Normal,
                    color = if (selected) androidx.compose.ui.graphics.Color.White else Tokens.ink3,
                    modifier = Modifier
                        .testTag("lang-${option.code}")
                        .heightIn(min = 36.dp)
                        .background(if (selected) Tokens.ink else androidx.compose.ui.graphics.Color.Transparent, RoundedCornerShape(Tokens.radiusPill))
                        .clickable(enabled = !ui.switching && !selected) { onLanguage(option) }
                        .padding(9.dp, 7.dp),
                )
            }
        }
    }
    Box(Modifier.fillMaxWidth().height(1.dp).background(Tokens.lineSoft))
}

@Composable
private fun Tabs(selected: Tab, messageCount: Int, s: Strings, onSelect: (Tab) -> Unit) {
    Row(Modifier.fillMaxWidth()) {
        TabButton(Modifier.weight(1f), s.planTab, Glyph.Pin, selected == Tab.PLAN, null, "tab-plan") { onSelect(Tab.PLAN) }
        TabButton(Modifier.weight(1f), s.messages, Glyph.Inbox, selected == Tab.MESSAGES, messageCount.takeIf { it > 0 }, "tab-messages") { onSelect(Tab.MESSAGES) }
    }
}

@Composable
private fun TabButton(
    modifier: Modifier,
    label: String,
    glyph: Glyph,
    selected: Boolean,
    count: Int?,
    tag: String,
    onClick: () -> Unit,
) {
    val ink = if (selected) Tokens.ink else Tokens.ink3
    Column(modifier.clickable(onClick = onClick).testTag(tag), horizontalAlignment = Alignment.CenterHorizontally) {
        Row(
            Modifier.heightIn(min = 46.dp).padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
        ) {
            SaathiIcon(glyph, ink, 14.dp)
            Text(label, fontSize = 15.sp, fontWeight = if (selected) FontWeight.Medium else FontWeight.Normal, color = ink)
            if (count != null) {
                Text(
                    count.toString(),
                    fontSize = 11.sp,
                    color = Tokens.blue700,
                    modifier = Modifier.background(Tokens.blue100, RoundedCornerShape(Tokens.radiusPill)).padding(6.dp, 1.dp),
                )
            }
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(if (selected) Tokens.ink else Tokens.lineSoft))
    }
}
