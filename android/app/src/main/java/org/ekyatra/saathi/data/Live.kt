package org.ekyatra.saathi.data

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import java.util.concurrent.TimeUnit

/**
 * The live stream, as the family's phone uses it.
 *
 * Mirrors `applyEvent` in `frontend/packages/api-client/src/live.ts`: the stream
 * holds *what changed*, never domain data. When something names this family the
 * screen re-reads the one endpoint, so what is shown is always a thing the
 * backend said, never a local guess.
 */

/** Events that change something about one family's page. Keep in step with live.ts. */
val PatientKinds: Set<String> = setOf(
    "plan.recomputed",
    "message.rendered",
    "message.held",
    "step.released",
    "ledger.appended",
    "inbound.received",
    "guard.blocked",
    "holding_message.sent",
    "options.ready",
    "approval.recorded",
    "confirmation.received",
    "process.answered",
)

@Serializable
data class WorldEvent(
    val kind: String,
    @SerialName("patient_id") val patientId: String? = null,
    val summary: String = "",
    val payload: JsonObject = JsonObject(emptyMap()),
)

/** Work announced and not yet finished: "Saathi is checking". */
data class WorkItem(val id: String, val task: String, val patientId: String?)

data class LiveState(
    val connected: Boolean = false,
    val working: List<WorkItem> = emptyList(),
    /** Bumped each time an event names this family. A change means: re-read. */
    val revision: Int = 0,
)

fun parseEvent(raw: String): WorldEvent? =
    runCatching { SaathiJson.decodeFromString<WorldEvent>(raw) }.getOrNull()

private fun WorldEvent.workId(): String? = (payload["work_id"] as? JsonPrimitive)?.content

fun applyEvent(state: LiveState, event: WorldEvent, patientId: String): LiveState {
    var working = state.working
    val workId = event.workId()
    if (event.kind == "agent.started" && workId != null) {
        working = working + WorkItem(workId, event.summary, event.patientId)
    } else if (event.kind == "agent.finished" && workId != null) {
        working = working.filterNot { it.id == workId }
    }

    val revision =
        if (event.patientId == patientId && event.kind in PatientKinds) state.revision + 1
        else state.revision

    return state.copy(working = working, revision = revision)
}

/** Only this family's work. Showing a stranger's would misreport whose problem is being worked on. */
fun LiveState.workingFor(patientId: String): List<WorkItem> =
    working.filter { it.patientId == null || it.patientId == patientId }

sealed interface StreamSignal {
    data object Opened : StreamSignal
    data class Received(val event: WorldEvent) : StreamSignal
    data object Closed : StreamSignal
}

/** Server-sent events from `/stream`, as a cold flow. One collection is one connection. */
fun SaathiApi.events(): Flow<StreamSignal> = callbackFlow {
    // The stream is endless by design, so it must not time out reading.
    val streaming = client.newBuilder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    val request = Request.Builder()
        .url(url("/stream"))
        .header("Accept", "text/event-stream")
        .build()

    val listener = object : EventSourceListener() {
        override fun onOpen(eventSource: EventSource, response: Response) {
            trySend(StreamSignal.Opened)
        }

        override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
            parseEvent(data)?.let { trySend(StreamSignal.Received(it)) }
        }

        override fun onClosed(eventSource: EventSource) {
            trySend(StreamSignal.Closed)
            close()
        }

        override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
            trySend(StreamSignal.Closed)
            close()
        }
    }

    val source = EventSources.createFactory(streaming).newEventSource(request, listener)
    awaitClose { source.cancel() }
}
