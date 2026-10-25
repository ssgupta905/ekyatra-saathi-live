package org.ekyatra.saathi.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Parses real captured API responses, so a renamed field fails here and not on a family's screen. */
class ModelsTest {
    private fun fixture(name: String): String =
        checkNotNull(javaClass.classLoader?.getResource("fixtures/$name")) { "missing fixture $name" }.readText()

    @Test
    fun `the home payload carries everything the phone shows`() {
        val home = SaathiJson.decodeFromString<FamilyHome>(fixture("home_shambhu.json"))

        assertEquals("P-SHAMBHU", home.patient.id)
        assertEquals("hi", home.patient.language)
        assertEquals("wait", home.decision)
        assertNull(home.travelOn)
        assertTrue(home.steps.isNotEmpty())
        assertNotNull(home.message)
    }

    @Test
    fun `a go decision carries the date to travel and the step that is next`() {
        val home = SaathiJson.decodeFromString<FamilyHome>(fixture("home_go.json"))

        assertEquals("go", home.decision)
        assertEquals("2026-10-28", home.travelOn)
        assertEquals(41.2, home.patient.hoursEachWay!!, 0.001)
        assertTrue(home.steps.single().isNext)
        assertEquals("groq", home.message?.writtenBy)
    }

    @Test
    fun `a booked wait is certain and a forecast is a range`() {
        val home = SaathiJson.decodeFromString<FamilyHome>(fixture("home_shambhu.json"))
        val booked = home.waitingFor.first { it.certain }
        assertEquals(booked.earliest, booked.latest)
    }

    @Test
    fun `the step called when is read despite being a reserved word elsewhere`() {
        val home = SaathiJson.decodeFromString<FamilyHome>(fixture("home_shambhu.json"))
        val consult = home.steps.first { it.kind == "consult" }
        assertEquals("2026-10-20", consult.on)
        assertEquals("done", consult.state)
    }

    @Test
    fun `an unknown field does not break the phone`() {
        val json = """{"patient":{"id":"P1","district":"Gaya","language":"hi","distance_km":10},
            "decision":null,"a_field_added_next_year":123}"""
        val home = SaathiJson.decodeFromString<FamilyHome>(json)
        assertNull(home.decision)
        assertTrue(home.steps.isEmpty())
    }

    @Test
    fun `the patient list reads district and distance`() {
        val patients = SaathiJson.decodeFromString<List<PatientSummary>>(fixture("patients.json"))
        assertTrue(patients.any { it.id == "P-SHAMBHU" && it.district == "Gaya" })
        assertTrue(patients.all { it.distanceKm > 0 })
    }

    @Test
    fun `a thread keeps held, divider and non answerable entries distinct`() {
        val thread = SaathiJson.decodeFromString<Thread>(fixture("thread_mixed.json"))

        assertEquals(4, thread.thread.size)
        assertFalse(thread.thread.first().held)
        assertEquals("language", thread.thread[2].kind)
        assertTrue(thread.thread[3].held)

        val question = thread.thread[1]
        assertEquals("from_family", question.direction)
        assertEquals(false, question.answerable)
        // A message sent to the family has no answerable flag at all.
        assertNull(thread.thread.first().answerable)
    }

    @Test
    fun `the real captured thread parses too`() {
        val thread = SaathiJson.decodeFromString<Thread>(fixture("thread_shambhu.json"))
        assertEquals("P-SHAMBHU", thread.patientId)
        assertTrue(thread.thread.all { it.body.isNotBlank() })
    }
}
