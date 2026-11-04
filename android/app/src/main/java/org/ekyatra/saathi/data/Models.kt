package org.ekyatra.saathi.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * The API's shapes, as far as the family's phone reads them.
 *
 * Narrow on purpose: the phone can show a plan and a conversation, and nothing
 * else. There is no field here that could hold a finding, because the backend
 * has no endpoint that returns one. The unit tests parse real captured
 * responses (`src/test/resources/fixtures`), so a renamed field fails a test
 * rather than a family's screen.
 */

val SaathiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
}

@Serializable
data class PatientSummary(
    val id: String,
    @SerialName("home_district") val district: String,
    @SerialName("home_distance_km") val distanceKm: Double,
    val language: String,
)

@Serializable
data class HomePatient(
    val id: String,
    val district: String,
    val language: String,
    @SerialName("distance_km") val distanceKm: Double,
    @SerialName("hours_each_way") val hoursEachWay: Double? = null,
)

@Serializable
data class FamilyWait(
    val kind: String,
    val what: String,
    val earliest: String? = null,
    val latest: String? = null,
    /** A booking is a fact; a forecast is a range. */
    val certain: Boolean = false,
)

@Serializable
data class FamilyMessage(
    val body: String,
    val language: String,
    val kind: String,
    @SerialName("sent_at") val sentAt: String,
    /** Held by the guard, so never sent. The phone says a person will call. */
    val held: Boolean = false,
    @SerialName("written_by") val writtenBy: String? = null,
)

@Serializable
data class FamilyStep(
    val id: String,
    val kind: String,
    val what: String,
    @SerialName("when") val on: String? = null,
    /** "done", "waiting" or "ahead". */
    val state: String,
    /** False for reports: a result arrives, nobody travels for it. */
    val travels: Boolean = true,
    @SerialName("is_next") val isNext: Boolean = false,
)

@Serializable
data class StageStep(
    val kind: String,
    val done: Boolean = false,
    val on: String? = null,
)

@Serializable
data class GuideStage(
    val id: String,
    /** "tests", "reports", "insurance", "pharmacy", "ride", "stay", "documents", "visit", "next_session". */
    val kind: String,
    /** "done", "waiting", "problem" or "upcoming". */
    val state: String,
    /** The first stage not yet done: the one to look at. */
    @SerialName("is_now") val isNow: Boolean = false,
    /** What the family should do: "nothing_yet", "wait_for_team", "keep_documents_ready"... */
    val action: String = "none",
    /** Who has it: "Uber", "the lab". */
    val party: String? = null,
    val detail: String = "",
    val steps: List<StageStep> = emptyList(),
    /** A forecast window for a report still to come, never a promise. */
    val window: List<String>? = null,
    /** Only the visit, and only when the plan is a GO. */
    val on: String? = null,
    @SerialName("first_stop") val firstStop: String? = null,
    val bring: List<String> = emptyList(),
)

@Serializable
data class JourneyGuide(
    @SerialName("patient_id") val patientId: String,
    val decision: String? = null,
    val stages: List<GuideStage> = emptyList(),
    @SerialName("now_stage_id") val nowStageId: String? = null,
    val done: Int = 0,
    val total: Int = 0,
)

@Serializable
data class FamilyHome(
    val patient: HomePatient,
    /** "go", "wait", "uncertain" or "replan"; null before there is a plan. */
    val decision: String? = null,
    @SerialName("travel_on") val travelOn: String? = null,
    @SerialName("waiting_for") val waitingFor: List<FamilyWait> = emptyList(),
    val message: FamilyMessage? = null,
    val steps: List<FamilyStep> = emptyList(),
    /** Only for a family cleared to travel: what to carry, and the first desk. */
    @SerialName("what_to_bring") val whatToBring: List<String> = emptyList(),
    @SerialName("where_to_go_first") val whereToGoFirst: String? = null,
    /** The whole journey in order, with what the family should do now. */
    val guide: JourneyGuide? = null,
    @SerialName("sim_date") val simDate: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class ThreadEntry(
    val id: String,
    /** "to_family" or "from_family". */
    val direction: String,
    /** "message", "holding", "language"... */
    val kind: String,
    val body: String,
    val language: String? = null,
    @SerialName("sent_at") val sentAt: String,
    val held: Boolean = false,
    val reason: String? = null,
    val gloss: String? = null,
    /** False when a person, not Saathi, has to answer. */
    val answerable: Boolean? = null,
)

@Serializable
data class Thread(
    @SerialName("patient_id") val patientId: String,
    val language: String,
    val thread: List<ThreadEntry> = emptyList(),
    val unread: Int = 0,
)

@Serializable
data class Transcript(
    val text: String,
    val language: String,
    val model: String? = null,
    /** Always false: transcription hands back words, it does not send them. */
    val sent: Boolean = false,
)

@Serializable
data class LanguageChange(val language: String, val changed: Boolean = false)
