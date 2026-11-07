package org.ekyatra.saathi.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.concurrent.TimeUnit

/** An API call that did not succeed. Carries the HTTP status when there was one. */
class ApiException(message: String, val status: Int? = null, cause: Throwable? = null) :
    Exception(message, cause)

/**
 * The one place a request leaves the app.
 *
 * `baseUrl` is the API root including `/api`, set per build (see `apiBase` in
 * gradle.properties), so the same code reaches the emulator's host, a LAN
 * address or a deployed service.
 */
class SaathiApi(
    val baseUrl: String,
    val client: OkHttpClient = defaultClient(),
    /** Where the sign-in is remembered. Empty when login is off (the demo). */
    val tokens: TokenStore = MemoryTokenStore(),
) {
    /** Called when the server stops trusting the token, so the app can ask again. */
    @Volatile
    var onUnauthorized: (() -> Unit)? = null

    fun url(path: String): String = baseUrl.trimEnd('/') + path

    private suspend fun execute(request: Request, label: String): String =
        withContext(Dispatchers.IO) {
            try {
                val signed = tokens.get()?.let {
                    request.newBuilder().header("Authorization", "Bearer $it").build()
                } ?: request
                client.newCall(signed).execute().use { response ->
                    val body = response.body.string()
                    if (response.code == 401 && !request.url.encodedPath.contains("/auth/")) {
                        tokens.clear()
                        onUnauthorized?.invoke()
                    }
                    if (!response.isSuccessful) {
                        throw ApiException(
                            "$label failed: ${response.code}${detail(body)}",
                            response.code,
                        )
                    }
                    body
                }
            } catch (e: ApiException) {
                throw e
            } catch (e: Exception) {
                throw ApiException("could not reach ${url("")}: ${e.message}", cause = e)
            }
        }

    /** FastAPI puts the reason in {"detail": "..."}; show it rather than a bare status. */
    private fun detail(body: String): String = runCatching {
        val text = SaathiJson.parseToJsonElement(body)
            .let { (it as? kotlinx.serialization.json.JsonObject)?.get("detail") }
            ?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
        if (text.isNullOrBlank()) "" else " · $text"
    }.getOrDefault("")

    internal suspend fun get(path: String): String =
        execute(Request.Builder().url(url(path)).build(), "GET $path")

    internal suspend fun send(method: String, path: String, body: RequestBody): String =
        execute(Request.Builder().url(url(path)).method(method, body).build(), "$method $path")

    internal fun json(block: kotlinx.serialization.json.JsonObjectBuilder.() -> Unit): RequestBody =
        buildJsonObject(block).toString().toRequestBody("application/json".toMediaType())

    suspend fun health(): String = get("/health")

    suspend fun patients(): List<PatientSummary> =
        SaathiJson.decodeFromString(get("/patients"))

    suspend fun home(patientId: String): FamilyHome =
        SaathiJson.decodeFromString(get("/patients/$patientId/home"))

    suspend fun thread(patientId: String): Thread =
        SaathiJson.decodeFromString(get("/patients/$patientId/notifications"))

    suspend fun chooseLanguage(patientId: String, language: String): LanguageChange =
        SaathiJson.decodeFromString(
            send(
                "PATCH",
                "/patients/$patientId/language",
                json {
                    put("language", language)
                    put("chosen_by", "family")
                },
            ),
        )

    /** A family typing (or confirming dictated words) to the care team. */
    suspend fun say(patientId: String, text: String) {
        send(
            "POST",
            "/live/inject",
            json {
                put("patient_id", patientId)
                put("text", text)
            },
        )
    }

    /** Speech to text. Returns the words for the family to check; nothing is sent. */
    /**
     * Audio of a message, read out by the service in the family's own language.
     *
     * Bytes rather than JSON, so it does not go through [execute]. Returns null
     * when the service has no voice configured or could not produce one; the
     * caller then falls back to the phone's own engine, which is worse but
     * better than silence.
     *
     * The text is one the language layer already wrote and the guard already
     * passed — this reads a message, it never composes one.
     */
    suspend fun say(patientId: String, text: String, language: String): ByteArray? =
        withContext(Dispatchers.IO) {
            val body = json {
                put("text", text)
                put("language", language)
            }
            val request = Request.Builder()
                .url(url("/patients/$patientId/voice/say"))
                .post(body)
                .build()
            val signed = tokens.get()?.let {
                request.newBuilder().header("Authorization", "Bearer $it").build()
            } ?: request
            runCatching {
                client.newCall(signed).execute().use { response ->
                    if (response.isSuccessful) response.body.bytes() else null
                }
            }.getOrNull()
        }

    suspend fun transcribe(patientId: String, audio: File, language: String): Transcript {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "audio",
                audio.name,
                audio.asRequestBody("audio/m4a".toMediaType()),
            )
            .addFormDataPart("patient_id", patientId)
            .addFormDataPart("language", language)
            .build()
        return SaathiJson.decodeFromString(send("POST", "/voice/transcribe", body))
    }

    companion object {
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()
    }
}
