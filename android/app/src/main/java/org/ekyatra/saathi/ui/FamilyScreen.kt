package org.ekyatra.saathi.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
 * The family's app: three places, one thumb.
 *
 * **Today** answers "do we travel" and nothing else until asked; **Plan** is the
 * journey; **Messages** is the conversation, with the box to write in only there.
 * Splitting them is the point: a caregiver at a bus stand should never have to
 * scroll past a care pathway to find out whether to get on.
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
    val messageCount = ui.thread?.thread?.size ?: 0

    BackHandler(onBack = onBack)

    Column(Modifier.fillMaxSize().background(Tokens.plane).safeDrawingPadding()) {
        TopBar(ui, lang, onBack, vm::chooseLanguage)

        val work = ui.live.workingFor(vm.patientId)
        AnimatedVisibility(work.isNotEmpty() || ui.switching) {
            Column(Modifier.fillMaxWidth().background(Tokens.blue100)) {
                LinearProgressIndicator(Modifier.fillMaxWidth().height(2.dp), color = Tokens.blue500, trackColor = Tokens.blue100)
                Row(Modifier.padding(16.dp, 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    SaathiIcon(Glyph.Spark, Tokens.blue700, 13.dp)
                    Text(
                        if (ui.switching) s.working else (work.firstOrNull()?.task ?: s.working),
                        fontSize = 13.sp,
                        color = Tokens.blue700,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }

        ui.error?.let {
            Text(
                it,
                fontSize = 14.sp,
                color = Tokens.critical,
                modifier = Modifier
                    .padding(16.dp, 10.dp, 16.dp, 0.dp)
                    .fillMaxWidth()
                    .background(Tokens.criticalTint, RoundedCornerShape(Tokens.radiusMd))
                    .padding(12.dp, 10.dp)
                    .testTag("error"),
            )
        }

        Box(Modifier.weight(1f)) {
            AnimatedContent(ui.tab, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "tab") { tab ->
                when (tab) {
                    Tab.TODAY -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        TodayTab(ui.home, lang, s, speaker, vm.patientId)
                        Boundary(lang, s)
                    }
                    Tab.PLAN -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                        SaathiCard {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                GlyphBadge(Glyph.Route, Tokens.blue600, Tokens.blue100)
                                Text(s.plan, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
                            }
                            Box(Modifier.height(14.dp))
                            PlanStrip(ui.home?.steps ?: emptyList(), lang, s, inCard = true)
                        }
                        Boundary(lang, s)
                    }
                    Tab.MESSAGES -> Messages(ui, lang, s, messageCount, vm)
                }
            }
        }

        BottomBar(ui.tab, messageCount, s, vm::selectTab)
    }
}

@Composable
private fun Messages(ui: FamilyUiState, lang: Lang, s: Strings, count: Int, vm: FamilyViewModel) {
    val scroll = rememberScrollState()
    // Stick to the newest message: wait one frame so the new bubble has been laid out.
    LaunchedEffect(count) {
        withFrameNanos { }
        scroll.scrollTo(scroll.maxValue)
    }
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(scroll)) {
            val entries = ui.thread?.thread ?: emptyList()
            if (entries.isEmpty()) {
                // Nothing yet: say what this place is for rather than show a blank page.
                Column(
                    Modifier.fillMaxWidth().padding(32.dp, 64.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    GlyphBadge(Glyph.Chat, Tokens.blue600, Tokens.blue100, size = 56)
                    Text(s.messages, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
                    Text(s.askPlaceholder, fontSize = 15.sp, color = Tokens.ink3, textAlign = TextAlign.Center)
                }
            } else {
                ThreadView(entries, lang, s)
            }
        }
        Composer(lang = lang, s = s, onSend = vm::send, onTranscribe = { vm.transcribe(it, lang) })
    }
}

@Composable
private fun Boundary(lang: Lang, s: Strings) {
    Row(
        Modifier.fillMaxWidth().padding(16.dp, 4.dp, 16.dp, 20.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SaathiIcon(Glyph.Shield, Tokens.ink4, 12.dp)
        Text(
            "  " + if (lang == Lang.EN) "Travel and appointments only. Saathi never discusses results." else s.aPersonWillReply,
            fontSize = 12.sp,
            color = Tokens.ink4,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun TopBar(ui: FamilyUiState, lang: Lang, onBack: () -> Unit, onLanguage: (Lang) -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().background(Tokens.surface).padding(4.dp, 8.dp, 12.dp, 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(44.dp).clickable(onClick = onBack).testTag("back"), contentAlignment = Alignment.Center) {
            SaathiIcon(Glyph.Back, Tokens.ink2, 20.dp)
        }
        Box(
            Modifier.size(34.dp).background(Tokens.blue500, RoundedCornerShape(10.dp)),
            contentAlignment = Alignment.Center,
        ) { Text("S", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp) }
        Column(Modifier.weight(1f).padding(start = 10.dp)) {
            Text("Saathi", fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
            ui.home?.let {
                Text(it.patient.district, fontSize = 13.sp, color = Tokens.ink3, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        Box {
            Row(
                Modifier
                    .heightIn(min = 40.dp)
                    .background(Tokens.fillQuiet, RoundedCornerShape(Tokens.radiusPill))
                    .clickable(enabled = !ui.switching) { menu = true }
                    .padding(12.dp, 8.dp)
                    .testTag("lang-menu"),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                SaathiIcon(Glyph.Globe, Tokens.ink2, 16.dp)
                Text(lang.endonym, fontSize = 15.sp, fontWeight = FontWeight.Medium, color = Tokens.ink)
                SaathiIcon(Glyph.ChevronDown, Tokens.ink3, 14.dp)
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                for (option in Lang.entries) {
                    DropdownMenuItem(
                        text = {
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(option.endonym, fontSize = 16.sp, fontWeight = if (option == lang) FontWeight.SemiBold else FontWeight.Normal)
                                Text(option.label, fontSize = 13.sp, color = Tokens.ink3)
                                if (option == lang) SaathiIcon(Glyph.Check, Tokens.blue600, 16.dp)
                            }
                        },
                        onClick = {
                            menu = false
                            if (option != lang) onLanguage(option)
                        },
                        modifier = Modifier.testTag("lang-${option.code}"),
                    )
                }
            }
        }
    }
    Box(Modifier.fillMaxWidth().height(1.dp).background(Tokens.lineSoft))
}

@Composable
private fun BottomBar(selected: Tab, messageCount: Int, s: Strings, onSelect: (Tab) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Tokens.surface)) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(Tokens.lineSoft))
        Row(Modifier.fillMaxWidth().padding(8.dp, 6.dp)) {
            NavItem(Modifier.weight(1f), s.todayTab, Glyph.Home, selected == Tab.TODAY, null, "tab-today") { onSelect(Tab.TODAY) }
            NavItem(Modifier.weight(1f), s.planTab, Glyph.Route, selected == Tab.PLAN, null, "tab-plan") { onSelect(Tab.PLAN) }
            NavItem(Modifier.weight(1f), s.messages, Glyph.Chat, selected == Tab.MESSAGES, messageCount.takeIf { it > 0 }, "tab-messages") { onSelect(Tab.MESSAGES) }
        }
    }
}

@Composable
private fun NavItem(
    modifier: Modifier,
    label: String,
    glyph: Glyph,
    selected: Boolean,
    count: Int?,
    tag: String,
    onClick: () -> Unit,
) {
    val ink = if (selected) Tokens.blue700 else Tokens.ink3
    Column(
        modifier.clickable(onClick = onClick).padding(vertical = 4.dp).testTag(tag),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Box(
            Modifier
                .background(if (selected) Tokens.blue100 else Color.Transparent, RoundedCornerShape(Tokens.radiusPill))
                .padding(18.dp, 5.dp),
            contentAlignment = Alignment.Center,
        ) {
            SaathiIcon(glyph, ink, 22.dp)
            if (count != null) {
                Text(
                    count.toString(),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(start = 26.dp)
                        .background(Tokens.critical, RoundedCornerShape(Tokens.radiusPill))
                        .padding(5.dp, 0.dp),
                )
            }
        }
        Text(label, fontSize = 12.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal, color = ink)
    }
}
