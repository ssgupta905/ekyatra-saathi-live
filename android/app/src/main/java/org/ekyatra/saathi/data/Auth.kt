package org.ekyatra.saathi.data

import android.content.Context
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.put

/**
 * Signing in, as a family does it: a phone number, then the code sent to it.
 *
 * Staff have their own apps and their own passwords; nothing here is for them.
 * Mirrors `frontend/packages/api-client/src/auth.ts`.
 */

@Serializable
data class AuthConfig(val required: Boolean, val provider: String = "local")

@Serializable
data class Principal(
    val id: String,
    val name: String,
    val role: String,
    @SerialName("patient_ids") val patientIds: List<String> = emptyList(),
)

@Serializable
data class Session(
    val token: String,
    @SerialName("expires_in") val expiresIn: Int,
    val principal: Principal,
)

@Serializable
private data class Ticket(val ticket: String)

/** Where the sign-in is remembered. Replaceable so tests need no phone. */
interface TokenStore {
    fun get(): String?
    fun set(token: String)
    fun clear()
}

/** Remembers nothing across a restart: what tests and a signed-out app use. */
class MemoryTokenStore(private var token: String? = null) : TokenStore {
    override fun get(): String? = token
    override fun set(token: String) { this.token = token }
    override fun clear() { token = null }
}

/**
 * The token in the app's private storage. Private to this app and not readable by
 * others, but not encrypted at rest: a rooted phone could read it. It stays valid
 * for a week at most and the server can refuse it at any time.
 */
class PrefsTokenStore(context: Context) : TokenStore {
    private val prefs = context.applicationContext.getSharedPreferences("saathi-auth", Context.MODE_PRIVATE)
    override fun get(): String? = prefs.getString("token", null)
    override fun set(token: String) { prefs.edit().putString("token", token).apply() }
    override fun clear() { prefs.edit().remove("token").apply() }
}

suspend fun SaathiApi.authConfig(): AuthConfig =
    SaathiJson.decodeFromString(get("/auth/config"))

/** Always succeeds from the caller's side: the server does not say whether the number is on record. */
suspend fun SaathiApi.requestOtp(phone: String) {
    send("POST", "/auth/otp/request", json { put("phone", phone) })
}

/** The same, for a family that signs in by email. The address is sent lower-cased. */
suspend fun SaathiApi.requestEmailOtp(email: String) {
    send("POST", "/auth/otp/request", json { put("email", email.trim().lowercase()) })
}

suspend fun SaathiApi.verifyEmailOtp(email: String, code: String): Session {
    val session: Session = SaathiJson.decodeFromString(
        send(
            "POST", "/auth/otp/verify",
            json { put("email", email.trim().lowercase()); put("code", code) },
        ),
    )
    tokens.set(session.token)
    return session
}

/** Verifies the code and, on success, remembers the session's token. */
suspend fun SaathiApi.verifyOtp(phone: String, code: String): Session {
    val session: Session = SaathiJson.decodeFromString(
        send("POST", "/auth/otp/verify", json { put("phone", phone); put("code", code) }),
    )
    tokens.set(session.token)
    return session
}

suspend fun SaathiApi.me(): Principal = SaathiJson.decodeFromString(get("/auth/me"))

suspend fun SaathiApi.streamTicket(): String =
    SaathiJson.decodeFromString<Ticket>(send("POST", "/auth/stream-ticket", json { })).ticket

fun SaathiApi.signOut() = tokens.clear()
