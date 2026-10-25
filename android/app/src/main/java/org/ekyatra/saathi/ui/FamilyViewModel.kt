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
import org.ekyatra.saathi.data.LiveState
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.StreamSignal
import org.ekyatra.saathi.data.Thread
import org.ekyatra.saathi.data.Transcript
import org.ekyatra.saathi.data.applyEvent
import org.ekyatra.saathi.data.events
import org.ekyatra.saathi.i18n.Lang
import java.io.File

enum class Tab { PLAN, MESSAGES }

data class FamilyUiState(
    val home: FamilyHome? = null,
    val thread: Thread? = null,
    val error: String? = null,
    val switching: Boolean = false,
    val live: LiveState = LiveState(),
    val tab: Tab = Tab.PLAN,
)

/**
 * Everything the family screen shows, kept honest by the live stream.
 *
 * Anything that touches this family — a new plan, a held message, a disruption
 * at the hospital — re-reads the one endpoint rather than patching local state,
 * so what is on screen is always a thing the backend said.
 */
class FamilyViewModel(
    private val api: SaathiApi,
    val patientId: String,
) : ViewModel() {
    private val mutable = MutableStateFlow(FamilyUiState())
    val state: StateFlow<FamilyUiState> = mutable.asStateFlow()
    private var refreshJob: Job? = null

    init {
        refresh()
        viewModelScope.launch { listen() }
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
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                mutable.update { it.copy(error = e.message) }
            }
        }
    }

    private suspend fun listen() {
        while (currentCoroutineContext().isActive) {
            try {
                api.events().collect { signal ->
                    when (signal) {
                        StreamSignal.Opened -> setConnected(true)
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

    private companion object {
        const val RECONNECT_MS = 2_000L
    }
}
