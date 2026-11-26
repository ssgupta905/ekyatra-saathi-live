package org.ekyatra.saathi.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.ekyatra.saathi.data.ApiException
import org.ekyatra.saathi.data.FamilyHome
import org.ekyatra.saathi.data.Kharcha
import org.ekyatra.saathi.data.LiveState
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.StreamSignal
import org.ekyatra.saathi.data.Thread
import org.ekyatra.saathi.data.Transcript
import org.ekyatra.saathi.data.applyEvent
import org.ekyatra.saathi.data.events
import org.ekyatra.saathi.i18n.Lang
import java.io.File

enum class Tab { TODAY, PLAN, MESSAGES, KHARCHA }

data class FamilyUiState(
    val home: FamilyHome? = null,
    val thread: Thread? = null,
    val error: String? = null,
    val switching: Boolean = false,
    val live: LiveState = LiveState(),
    val tab: Tab = Tab.TODAY,
    /** The family's books. Null until read, and where nothing is kept. */
    val kharcha: Kharcha? = null,
    /** A line in the family's own words when an action on their books failed. */
    val kharchaError: String? = null,
)

/**
 * Everything the family screen shows, kept honest by the live stream.
 *
 * Anything that touches this family — a new plan, a held message, a disruption
 * at the hospital — re-reads the one endpoint rather than patching local state,
 * so what is on screen is always a thing the backend said.
 */
class FamilyViewModel(
    val api: SaathiApi,
    val patientId: String,
) : ViewModel() {
    private val mutable = MutableStateFlow(FamilyUiState())
    val state: StateFlow<FamilyUiState> = mutable.asStateFlow()
    private var refreshJob: Job? = null

    init {
        refresh()
        viewModelScope.launch { listen() }
        viewModelScope.launch { keepUpToDate() }
    }

    /** Fetch again every so often, whatever the stream is doing.
     *
     *  The stream is the fast path, not the only one. It can be closed by a
     *  proxy, dropped while the phone sleeps, or carry a kind this build does
     *  not recognise — and every one of those fails silently: no error, no
     *  spinner, just a screen still showing what it showed when it opened. A
     *  family waiting to be told something would never learn they had been
     *  told.
     *
     *  So this is a backstop with no opinion about events at all. Polling
     *  costs battery, which is why the interval is tens of seconds and not
     *  one: a message that arrives twenty seconds late is a message that
     *  arrived.
     */
    private suspend fun keepUpToDate() {
        while (currentCoroutineContext().isActive) {
            delay(POLL_MS)
            refresh()
        }
    }

    fun refresh() {
        refreshJob?.cancel()
        refreshJob = viewModelScope.launch {
            try {
                val (home, thread) = coroutineScope {
                    val home = async { api.home(patientId) }
                    val thread = async { api.thread(patientId) }
                    home.await() to thread.await()
                }
                mutable.update { it.copy(home = home, thread = thread, error = null) }
                loadKharcha()
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                mutable.update { it.copy(error = e.message) }
            }
        }
    }

    /** Read apart from the rest: a service with no books must not stop the journey showing. */
    private suspend fun loadKharcha() {
        val books = try {
            api.kharcha(patientId)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            null
        }
        mutable.update { it.copy(kharcha = books) }
    }

    /** Do something to the books, then read them again. A failure is said, not hidden. */
    fun kharchaAction(failed: String, work: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                work()
                mutable.update { it.copy(kharchaError = null) }
                loadKharcha()
                refresh()
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                mutable.update { it.copy(kharchaError = failed) }
            }
        }
    }

    private suspend fun listen() {
        while (currentCoroutineContext().isActive) {
            try {
                api.events().collect { signal ->
                    when (signal) {
                        // Fetch on connect, not only on the events that follow
                        // it. Whatever happened while the stream was down was
                        // delivered to nobody, and reconnecting is the moment
                        // to find out.
                        StreamSignal.Opened -> {
                            setConnected(true)
                            refresh()
                        }
                        StreamSignal.Closed -> setConnected(false)
                        is StreamSignal.Received -> {
                            val before = mutable.value.live.revision
                            mutable.update { it.copy(live = applyEvent(it.live, signal.event, patientId)) }
                            if (mutable.value.live.revision != before) refresh()
                        }
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                // fall through to the reconnect below
            }
            setConnected(false)
            delay(RECONNECT_MS)
        }
    }

    private fun setConnected(connected: Boolean) =
        mutable.update { it.copy(live = it.live.copy(connected = connected)) }

    fun selectTab(tab: Tab) = mutable.update { it.copy(tab = tab) }

    fun chooseLanguage(language: Lang) {
        if (mutable.value.switching) return
        viewModelScope.launch {
            mutable.update { it.copy(switching = true) }
            try {
                api.chooseLanguage(patientId, language.code)
                refresh()
            } catch (e: ApiException) {
                mutable.update { it.copy(error = e.message) }
            } finally {
                mutable.update { it.copy(switching = false) }
            }
        }
    }

    /** Send a reply to the care team, then show the conversation: the answer arrives there. */
    suspend fun send(text: String) {
        api.say(patientId, text)
        mutable.update { it.copy(tab = Tab.MESSAGES) }
        refresh()
    }

    suspend fun transcribe(recording: File, language: Lang): Transcript =
        api.transcribe(patientId, recording, language.code)

    /**
     * Audio of a message, spoken by the service.
     *
     * Null when it has no voice configured or could not produce one, and the
     * screen then falls back to the phone's own engine. Most phones have no
     * Odia voice, so for an Odia family this is the difference between hearing
     * the message and being told there is no voice for it.
     */
    suspend fun speak(text: String, language: Lang): ByteArray? =
        api.say(patientId, text, language.code)

    private companion object {
        const val RECONNECT_MS = 2_000L

        /** How often the screen refreshes itself with no event to prompt it. */
        const val POLL_MS = 20_000L
    }
}
