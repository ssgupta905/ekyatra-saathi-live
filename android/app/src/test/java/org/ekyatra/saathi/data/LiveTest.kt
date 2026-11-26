package org.ekyatra.saathi.data

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import java.io.File
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
        // Read from live.ts, not copied from it. This test used to hold its own
        // transcript of the list, which meant it enforced whatever the list had
        // been on the day it was written: nine kinds were added to the web and
        // this went on passing, with the phone quietly ignoring every one of
        // them — including a family being asked a question.
        // Found by walking up rather than by counting directories: Gradle runs
        // unit tests from the module directory, not the repository root, and a
        // fixed number of `..` is one build-file change away from being wrong.
        val wanted = "frontend/packages/api-client/src/live.ts"
        var dir: File? = File("").absoluteFile
        var liveTs: File? = null
        while (dir != null && liveTs == null) {
            val candidate = File(dir, wanted)
            if (candidate.exists()) liveTs = candidate else dir = dir.parentFile
        }
        assertNotNull("cannot find $wanted above ${File("").absolutePath}", liveTs)
        val block = Regex("""PATIENT_KINDS = new Set<EventKind>\(\[(.*?)]\)""", RegexOption.DOT_MATCHES_ALL)
            .find(liveTs!!.readText())
        assertNotNull("PATIENT_KINDS not found in live.ts — renamed?", block)
        val web = Regex("\"([^\"]+)\"").findAll(block!!.groupValues[1])
            .map { it.groupValues[1] }.toSet()

        assertEquals(
            "the phone ignores kinds the web refreshes on; nothing will update on screen",
            web,
            PatientKinds,
        )
    }
}
