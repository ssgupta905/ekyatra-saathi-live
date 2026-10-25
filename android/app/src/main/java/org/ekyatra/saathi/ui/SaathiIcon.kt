package org.ekyatra.saathi.ui

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Glyphs, the same ones the web apps use: a 20px box, 1.8px stroke. A status
 * colour never carries meaning alone, so each is paired with a word wherever it
 * appears. The path data is copied from `frontend/packages/ui-web/src/icons.tsx`.
 */
private fun circle(cx: Float, cy: Float, r: Float): String =
    "M${cx - r} $cy a$r $r 0 1 0 ${2 * r} 0 a$r $r 0 1 0 ${-2 * r} 0"

enum class Glyph(val paths: List<String>) {
    CheckCircle(listOf(circle(10f, 10f, 7.6f), "M6.6 10.3l2.3 2.3 4.5-4.9")),
    Clock(listOf(circle(10f, 10f, 7.6f), "M10 5.9V10l3 1.9")),
    Doc(
        listOf(
            "M11.4 2.8H6.6a1.4 1.4 0 0 0-1.4 1.4v11.6a1.4 1.4 0 0 0 1.4 1.4h6.8a1.4 1.4 0 0 0 1.4-1.4V6.2z",
            "M11.4 2.8v3.4h3.4",
        ),
    ),
    Inbox(
        listOf(
            "M3.4 11.2h3.3l1.1 1.9h4.4l1.1-1.9h3.3",
            "M5.4 4.2h9.2l2 7v4.2a1.4 1.4 0 0 1-1.4 1.4H4.8a1.4 1.4 0 0 1-1.4-1.4V11.2z",
        ),
    ),
    Pin(listOf("M10 17.2s5-4.4 5-8.2a5 5 0 0 0-10 0c0 3.8 5 8.2 5 8.2z", circle(10f, 8.8f, 1.9f))),
    Shield(listOf("M10 2.9l5.4 2v4.4c0 3.2-2.1 6-5.4 7.1-3.3-1.1-5.4-3.9-5.4-7.1V4.9l5.4-2z")),
    Spark(listOf("M10 3.2l1.6 4.1 4.2 1.5-4.2 1.5L10 14.4l-1.6-4.1-4.2-1.5 4.2-1.5z")),
    Speaker(listOf("M5 8h2.4L10.6 5v10L7.4 12H5z", "M13.2 7.6a3.4 3.4 0 0 1 0 4.8")),
    Wave(listOf("M3 10h2.4l1.6-4.6L9.4 15l2-7.4L13 11.4l1-1.4H17")),
    Back(listOf("M12 5.5l-5 4.5 5 4.5")),
}

private fun Glyph.toVector(): ImageVector {
    val builder = ImageVector.Builder(
        name = name,
        defaultWidth = 20.dp,
        defaultHeight = 20.dp,
        viewportWidth = 20f,
        viewportHeight = 20f,
    )
    for (d in paths) {
        builder.addPath(
            pathData = PathParser().parsePathString(d).toNodes(),
            stroke = SolidColor(Color.Black),
            strokeLineWidth = 1.8f,
            strokeLineCap = StrokeCap.Round,
            strokeLineJoin = StrokeJoin.Round,
        )
    }
    return builder.build()
}

@Composable
fun SaathiIcon(glyph: Glyph, tint: Color, size: Dp = 16.dp, modifier: Modifier = Modifier) {
    val vector = remember(glyph) { glyph.toVector() }
    Icon(imageVector = vector, contentDescription = null, tint = tint, modifier = modifier.size(size))
}
