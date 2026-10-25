package org.ekyatra.saathi.i18n

import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * Dates in the family's own script. `java.time` carries the Indic month names
 * and numerals, so this is the platform's own locale data rather than a table
 * of month names we would have to keep correct ourselves.
 */

private fun localeOf(lang: Lang): Locale = Locale.forLanguageTag("${lang.code}-IN")

private fun format(iso: String?, pattern: String, lang: Lang): String =
    iso?.let {
        runCatching {
            LocalDate.parse(it).format(DateTimeFormatter.ofPattern(pattern, localeOf(lang)))
        }.getOrNull()
    } ?: "—"

/** "Wednesday 28 October", in the family's language. */
fun localDate(iso: String?, lang: Lang): String = format(iso, "EEEE d MMMM", lang)

/** "28 Oct". */
fun localDateShort(iso: String?, lang: Lang): String = format(iso, "d MMM", lang)

/** The time of day a message was sent, on this phone's clock. */
fun localTime(iso: String, lang: Lang): String =
    runCatching {
        OffsetDateTime.parse(iso)
            .atZoneSameInstant(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).withLocale(localeOf(lang)))
    }.getOrDefault("")

/** The step's name in this family's language, falling back to what the backend sent. */
fun stepWord(kind: String, fallback: String, lang: Lang): String =
    Translations.stepWords[lang]?.get(kind) ?: fallback
