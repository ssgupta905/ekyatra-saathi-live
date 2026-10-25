package org.ekyatra.saathi.data

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The Kotlin twin of `live.test.ts`: both must make the same decisions about the same events. */
class LiveTest {
    private fun event(kind: String, patientId: String? = null, workId: String? = null, summary: String = "") =
        WorldEvent(
            kind = kind,
            patientId = patientId,
            summary = summary,
            payload = if (workId == null) JsonObject(emptyMap()) else JsonObject(mapOf("work_id" to JsonPrimitive(workId))),
        )

    @Test
    fun `an event that names this family bumps the revision`() {
        val after = applyEvent(LiveState(), event("plan.recomputed", "P1"), "P1")
        assertEquals(1, after.revision)
    }

    @Test
    fun `an event about another family leaves this one alone`() {
        val after = applyEvent(LiveState(), event("plan.recomputed", "P2"), "P1")
        assertEquals(0, after.revision)
    }

    @Test
    fun `a kind that does not change a family's page is ignored even when it names them`() {
        val after = applyEvent(LiveState(), event("clock.tick", "P1"), "P1")
        assertEquals(0, after.revision)
    }

    @Test
    fun `work is tracked from started until finished`() {
        var state = applyEvent(LiveState(), event("agent.started", "P1", "w1", "Re-planning"), "P1")
        assertEquals(listOf(WorkItem("w1", "Re-planning", "P1")), state.working)

        state = applyEvent(state, event("agent.finished", workId = "w1"), "P1")
        assertTrue(state.working.isEmpty())
    }

    @Test
    fun `work without an id is ignored`() {
        val state = applyEvent(LiveState(), event("agent.started"), "P1")
        assertTrue(state.working.isEmpty())
    }

    @Test
    fun `only this family's work is shown`() {
        val state = LiveState(
            working = listOf(
                WorkItem("a", "mine", "P1"),
                WorkItem("b", "a stranger's", "P2"),
                WorkItem("c", "the whole cohort", null),
            ),
        )
        assertEquals(listOf("mine", "the whole cohort"), state.workingFor("P1").map { it.task })
    }

    @Test
    fun `the state it was given is not changed`() {
        val before = LiveState()
        applyEvent(before, event("plan.recomputed", "P1"), "P1")
        assertEquals(0, before.revision)
    }

    @Test
    fun `a frame that is not an event is dropped rather than crashing the stream`() {
        assertNull(parseEvent("not json"))
        assertNotNull(parseEvent("""{"kind":"clock.tick","extra":true}"""))
    }

    @Test
    fun `every kind the web treats as a family's own is treated the same here`() {
        // Mirrors PATIENT_KINDS in frontend/packages/api-client/src/live.ts.
        val web = setOf(
            "plan.recomputed", "message.rendered", "message.held", "step.released",
            "ledger.appended", "inbound.received", "guard.blocked", "holding_message.sent",
            "options.ready", "approval.recorded", "confirmation.received", "process.answered",
        )
        assertEquals(web, PatientKinds)
    }
}
