package org.ekyatra.saathi.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

/**
 * One light theme, deliberately. A caregiver reads this in daylight at a bus
 * stand, and should never see two different renderings of the same decision.
 */
@Composable
fun SaathiTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Tokens.blue500,
            onPrimary = Tokens.surface,
            background = Tokens.surface,
            onBackground = Tokens.ink,
            surface = Tokens.surface,
            onSurface = Tokens.ink,
            surfaceVariant = Tokens.fillQuiet,
            outline = Tokens.line,
            error = Tokens.critical,
            errorContainer = Tokens.criticalTint,
        ),
        content = content,
    )
}
