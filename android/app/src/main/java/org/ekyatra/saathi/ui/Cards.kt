package org.ekyatra.saathi.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.ekyatra.saathi.ui.theme.Tokens

/** A white card on the plane: the phone's one surface for anything below the answer. */
@Composable
fun SaathiCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Tokens.radiusLg),
        color = Tokens.surface,
        border = BorderStroke(1.dp, Tokens.lineSoft),
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(16.dp), content = content)
    }
}

/** A tinted round badge holding a glyph, the visual anchor of a card's title row. */
@Composable
fun GlyphBadge(glyph: Glyph, tint: Color, background: Color, size: Int = 36) {
    Box(
        Modifier.size(size.dp).background(background, RoundedCornerShape(Tokens.radiusMd)),
        contentAlignment = Alignment.Center,
    ) { SaathiIcon(glyph, tint, (size * 0.5).dp) }
}

/**
 * A card that shows one line until it is asked for more. The family sees the
 * answer first; the reasons and details are there when they want them, not all
 * at once.
 */
@Composable
fun ExpandableCard(
    title: String,
    summary: String,
    glyph: Glyph,
    tint: Color,
    background: Color,
    tag: String,
    initiallyOpen: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    var open by rememberSaveable(tag) { mutableStateOf(initiallyOpen) }
    val turn by animateFloatAsState(if (open) 180f else 0f, label = "chevron")
    SaathiCard(Modifier.testTag(tag)) {
        Row(
            Modifier.fillMaxWidth().clickable { open = !open }.testTag("$tag-toggle"),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlyphBadge(glyph, tint, background)
            Column(Modifier.weight(1f)) {
                Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
                Text(summary, fontSize = 13.sp, color = Tokens.ink3)
            }
            SaathiIcon(Glyph.ChevronDown, Tokens.ink4, 20.dp, Modifier.rotate(turn))
        }
        AnimatedVisibility(open, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            Column(Modifier.padding(top = 14.dp), content = content)
        }
    }
}
