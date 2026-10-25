package org.ekyatra.saathi.i18n

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class I18nTest {
    private val allLangs = Lang.entries

    @Test
    fun `all four languages are registered`() {
        assertEquals(setOf("hi", "bn", "or", "en"), allLangs.map { it.code }.toSet())
    }

    @Test
    fun `no string is blank in any language`() {
        // A family reading Odia must never meet an empty label that Hindi has.
        for (lang in allLangs) {
            val strings = Translations.of(lang)
            val values = Strings::class.java.declaredFields
                .filter { it.type == String::class.java }
                .onEach { it.isAccessible = true }
                .map { it.name to it.get(strings) as String }
            assertTrue("${lang.code} has no strings", values.isNotEmpty())
            for ((name, value) in values) assertTrue("${lang.code}.$name is blank", value.isNotBlank())
        }
    }

    @Test
    fun `the three Indic languages are written in their own scripts`() {
        assertTrue(Translations.of(Lang.HI).come.any { it in 'ऀ'..'ॿ' })
        assertTrue(Translations.of(Lang.BN).come.any { it in 'ঀ'..'৿' })
        assertTrue(Translations.of(Lang.OR).come.any { it in '଀'..'୿' })
        assertNotEquals(Translations.of(Lang.HI).come, Translations.of(Lang.EN).come)
    }

    @Test
    fun `an unknown language falls back to English`() {
        assertEquals(Lang.EN, Lang.of("xx"))
        assertEquals(Lang.EN, Lang.of(null))
        assertEquals(Lang.OR, Lang.of("or"))
    }

    @Test
    fun `step names are translated, with the backend's words as the fallback`() {
        assertEquals(Translations.stepWords.getValue(Lang.HI).getValue("biopsy"), stepWord("biopsy", "Biopsy", Lang.HI))
        assertEquals("Biopsy", stepWord("biopsy", "Biopsy", Lang.EN))
        assertEquals("Anything", stepWord("not_a_step", "Anything", Lang.HI))
    }

    @Test
    fun `every pathway step is named in the three Indic languages`() {
        val reference = Translations.stepWords.getValue(Lang.HI).keys
        assertTrue(reference.size >= 12)
        for (lang in listOf(Lang.BN, Lang.OR)) {
            assertEquals(lang.code, reference, Translations.stepWords.getValue(lang).keys)
        }
    }

    @Test
    fun `a missing date is a dash`() {
        assertEquals("—", localDate(null, Lang.HI))
        assertEquals("—", localDateShort("not a date", Lang.BN))
    }

    @Test
    fun `dates are written out in the family's own language`() {
        assertEquals("Wednesday 28 October", localDate("2026-10-28", Lang.EN))
        assertTrue(localDateShort("2026-10-28", Lang.HI).any { it in 'ऀ'..'ॿ' })
        assertTrue(localDateShort("2026-10-28", Lang.BN).any { it in 'ঀ'..'৿' })
    }

    @Test
    fun `a time is shown on the phone's own clock`() {
        assertTrue(localTime("2026-10-25T05:28:55.433847+00:00", Lang.EN).isNotBlank())
        assertEquals("", localTime("garbage", Lang.EN))
    }
}
