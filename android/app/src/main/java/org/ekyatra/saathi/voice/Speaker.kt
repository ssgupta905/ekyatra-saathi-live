package org.ekyatra.saathi.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import org.ekyatra.saathi.i18n.Lang
import java.util.Locale

/**
 * Read a message aloud. For a caregiver who cannot read their own script this is
 * not a convenience, it is the only way the message lands. Uses the phone's own
 * speech engine, so it costs nothing and works offline; a language the phone has
 * no voice for is reported rather than silently doing nothing.
 */
class Speaker(context: Context) {
    sealed interface Result {
        data object Started : Result
        data object NoVoice : Result
        data object NotReady : Result
    }

    private var ready = false
    private var onFinished: (() -> Unit)? = null
    private val tts: TextToSpeech = TextToSpeech(context.applicationContext) { status ->
        ready = status == TextToSpeech.SUCCESS
    }

    init {
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) = finish()
            override fun onStop(utteranceId: String?, interrupted: Boolean) = finish()

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) = finish()
        })
    }

    private fun finish() {
        onFinished?.invoke()
        onFinished = null
    }

    fun speak(text: String, lang: Lang, onFinished: () -> Unit): Result {
        if (!ready) return Result.NotReady
        val availability = tts.setLanguage(Locale.forLanguageTag("${lang.code}-IN"))
        if (availability == TextToSpeech.LANG_MISSING_DATA ||
            availability == TextToSpeech.LANG_NOT_SUPPORTED
        ) {
            return Result.NoVoice
        }
        tts.setSpeechRate(0.9f)
        this.onFinished = onFinished
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "saathi-utterance")
        return Result.Started
    }

    fun stop() {
        tts.stop()
    }

    fun shutdown() {
        tts.stop()
        tts.shutdown()
    }
}

/** One speaker for the screen, released when the screen goes away. */
@Composable
fun rememberSpeaker(): Speaker {
    val context = LocalContext.current
    val speaker = remember { Speaker(context) }
    DisposableEffect(speaker) { onDispose { speaker.shutdown() } }
    return speaker
}
