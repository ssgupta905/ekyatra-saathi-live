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
    /** What the apps this journey leads to are opened on. Never the family's own place. */
    val trip: Trip? = null,
)

/** The hospital's door, as a driver would say it. Null when the hospital has none on record. */
@Serializable
data class TripPlace(
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val address: String,
)

@Serializable
data class Trip(
    val destination: TripPlace? = null,
    val city: String = "",
    /** Only when the plan is a GO. */
    @SerialName("arrive_on") val arriveOn: String? = null,
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
    /** The working behind this message, folded away until somebody taps it. */
    val detail: MessageDetail? = null,
)

/**
 * What a message was built from, carried with it.
 *
 * A proposal says "about ₹960–1140" in one sentence, because that is what a
 * family reading it on a bus needs. Everything underneath — which train, how
 * many people, whose figure, which published rate it came from — is here, and
 * stays folded until somebody wants it.
 *
 * Fetched with the message rather than separately: a card that has to call
 * the API when it opens is a card that is empty on a bad connection, which is
 * the connection this app is for.
 */
@Serializable
data class MessageDetail(
    @SerialName("on_day") val onDay: String? = null,
    val cost: CostBreakdown? = null,
)

@Serializable
data class CostBreakdown(
    val items: List<CostItem> = emptyList(),
    val rupees: String = "",
    @SerialName("has_stated") val hasStated: Boolean = false,
    @SerialName("all_stated") val allStated: Boolean = false,
)

@Serializable
data class CostItem(
    val label: String,
    val rupees: String,
    /** How it was worked out: "2680 km × 2 at 0.42/km/person". */
    val basis: String = "",
    /** The publication behind it, so "where did that come from?" has an answer. */
    val source: String = "",
    /** True when the family told us this themselves; it is not our estimate. */
    val stated: Boolean = false,
    /** Their own sentence, when they did. */
    val said: String = "",
    @SerialName("is_estimate") val isEstimate: Boolean = true,
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

/* ── Kharcha: what the journey costs this family ───────────────────────────
   Amounts are whole paise and each one comes from somebody: the family's own
   words, a provider's quote or payment, or arithmetic over those. */

@Serializable
data class SpendEntry(
    val id: String,
    val category: String,
    @SerialName("amount_paise") val amountPaise: Long,
    val status: String,
    val source: String = "",
    @SerialName("stated_in") val statedIn: String? = null,
    val party: String? = null,
    val on: String = "",
)

@Serializable
data class ProjectionLine(
    val category: String,
    @SerialName("amount_paise") val amountPaise: Long? = null,
    val basis: String = "",
    @SerialName("visits_used") val visitsUsed: Int = 0,
)

@Serializable
data class MonthOutlook(
    val month: String,
    @SerialName("spent_paise") val spentPaise: Long = 0,
    @SerialName("booked_paise") val bookedPaise: Long = 0,
    /** Null when there are visits ahead and nothing recorded to say what they will cost. */
    @SerialName("expected_paise") val expectedPaise: Long? = null,
    @SerialName("visits_ahead") val visitsAhead: List<String> = emptyList(),
    val lines: List<ProjectionLine> = emptyList(),
    @SerialName("by_category") val byCategory: Map<String, Long> = emptyMap(),
)

@Serializable
data class KharchaNudge(
    val kind: String,
    @SerialName("organisation_name") val organisationName: String? = null,
)

@Serializable
data class KharchaLimit(
    @SerialName("monthly_paise") val monthlyPaise: Long,
    @SerialName("stated_in") val statedIn: String = "",
)

/** A seller's firm price for a ride, waiting for the family's Book. */
@Serializable
data class Bookable(
    @SerialName("item_id") val itemId: String,
    val need: String = "",
    val provider: String = "",
    @SerialName("amount_paise") val amountPaise: Long? = null,
)

@Serializable
data class Kharcha(
    val months: List<MonthOutlook> = emptyList(),
    val limit: KharchaLimit? = null,
    @SerialName("over_limit") val overLimit: Boolean = false,
    val nudges: List<KharchaNudge> = emptyList(),
    @SerialName("to_confirm") val toConfirm: List<SpendEntry> = emptyList(),
    val bookable: List<Bookable> = emptyList(),
    val payable: List<SpendEntry> = emptyList(),
)

@Serializable
data class SpendReply(val entry: SpendEntry)

@Serializable
data class PayLink(@SerialName("pay_url") val payUrl: String? = null)

/* ── How to get there: which bus, boarded where, and which way suits the family ── */

@Serializable
data class WayStep(
    val mode: String,
    val line: String? = null,
    val towards: String? = null,
    @SerialName("board_at") val boardAt: String? = null,
    @SerialName("get_off_at") val getOffAt: String? = null,
    val stops: Int? = null,
    val departs: String? = null,
    val arrives: String? = null,
    val minutes: Int = 0,
    val note: String? = null,
)

@Serializable
data class WayOption(
    val id: String,
    val steps: List<WayStep> = emptyList(),
    val minutes: Int = 0,
    val departs: String? = null,
    val arrives: String? = null,
    /** Only when someone gave it: the route service or a seller's quote. */
    @SerialName("fare_paise") val farePaise: Long? = null,
    @SerialName("fare_basis") val fareBasis: String = "none",
    val source: String = "service",
)

@Serializable
data class WeighedWay(
    val option: WayOption,
    val tags: List<String> = emptyList(),
    /** "within", "over" or "unknown". */
    val fit: String = "unknown",
    @SerialName("extra_over_cheapest_paise") val extraOverCheapestPaise: Long? = null,
    @SerialName("leave_by") val leaveBy: String? = null,
)

@Serializable
data class WayGuidance(
    val options: List<WeighedWay> = emptyList(),
    @SerialName("recommended_id") val recommendedId: String? = null,
    val reasons: List<String> = emptyList(),
    @SerialName("room_paise") val roomPaise: Long? = null,
)

@Serializable
data class RailStation(val name: String, val code: String)

/**
 * The train journey for a long leg: both stations with the codes IRCTC asks
 * for. There is deliberately no train, time or fare here: no open service has
 * them, and the screen sends the family to IRCTC for those.
 */
@Serializable
data class RailGuide(
    @SerialName("from") val origin: RailStation,
    val to: RailStation,
    val also: List<RailStation> = emptyList(),
    @SerialName("visit_at") val visitAt: String? = null,
    @SerialName("road_minutes") val roadMinutes: Int? = null,
    @SerialName("allow_days") val allowDays: Int? = null,
    @SerialName("irctc_url") val irctcUrl: String = "",
    @SerialName("status_url") val statusUrl: String = "",
)

/**
 * What the family said they can manage, for the month they travel in. Every
 * figure is theirs: the limit they set, what is already spent or booked, and a
 * fare they said out loud. Saathi adds no price of its own.
 */
@Serializable
data class WayBudget(
    val month: String = "",
    @SerialName("limit_paise") val limitPaise: Long? = null,
    val said: String? = null,
    @SerialName("committed_paise") val committedPaise: Long = 0,
    @SerialName("room_paise") val roomPaise: Long? = null,
    @SerialName("stated_fare_paise") val statedFarePaise: Long? = null,
    @SerialName("stated_in") val statedIn: String? = null,
)

@Serializable
data class WayOptions(
    val leg: String,
    val source: String,
    val guidance: WayGuidance,
    /** When the family must be there, from the hospital's own booking. */
    @SerialName("arrive_by") val arriveBy: String? = null,
    @SerialName("arrive_by_source") val arriveBySource: String? = null,
    /** The place the last leg started from when the family typed none. */
    @SerialName("origin_used") val originUsed: String? = null,
    val notes: List<String> = emptyList(),
    val rail: RailGuide? = null,
    val budget: WayBudget? = null,
)

/* ── Near you: shops, labs and clinics around where the family will be ── */

@Serializable
data class NearPlace(
    val id: String,
    val name: String,
    val kind: String,
    val address: String = "",
    val latitude: Double,
    val longitude: Double,
    val phone: String? = null,
    @SerialName("maps_uri") val mapsUri: String? = null,
    val source: String = "google",
)

@Serializable
data class NearRanked(
    val place: NearPlace,
    val metres: Int,
    /** Open at the time they will be there. Null when the hours are not known. */
    @SerialName("open_then") val openThen: Boolean? = null,
    val reasons: List<String> = emptyList(),
)

@Serializable
data class NearResult(val need: String, val near: String, val source: String, val places: List<NearRanked> = emptyList())
