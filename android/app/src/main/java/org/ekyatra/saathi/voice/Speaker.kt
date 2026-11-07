package org.ekyatra.saathi.voice

import android.content.Context
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import org.ekyatra.saathi.i18n.Lang
import java.io.File
import java.util.Locale

/**
 * Read a message aloud.
 *
 * For a caregiver who cannot read their own script this is not a convenience,
 * it is the only way the message lands — so it matters which voice does it.
 *
 * The service speaks first. It uses a provider built for these languages, and
 * crucially it has an Odia voice: most phones do not, so for an Odia family the
 * phone's own engine answers [Result.NoVoice] and the message is never heard.
 *
 * The phone's engine is still the fallback. It costs nothing, it works with no
 * signal, and a worse voice in Hindi beats no voice at all. Only when both have
 * nothing does the caller hear [Result.NoVoice], which the screen then says out
 * loud rather than leaving a button that quietly does nothing.
 */
class Speaker(context: Context) {
    sealed interface Result {
        /** Speaking now. [fromService] is true when the good voice was used. */
        data class Started(val fromService: Boolean) : Result
        data object NoVoice : Result
        data object NotReady : Result
    }

    private val appContext = context.applicationContext
    private var ready = false
    private var onFinished: (() -> Unit)? = null
    private var player: MediaPlayer? = null

    private val tts: TextToSpeech = TextToSpeech(appContext) { status ->
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

    /**
     * Play audio the service produced.
     *
     * Written to the cache rather than streamed: the file is a second or two of
     * speech, and a local file plays the same way on every Android version
     * whereas streaming a byte array does not.
     */
    fun play(audio: ByteArray, onFinished: () -> Unit): Result {
        stop()
        val file = File(appContext.cacheDir, "saathi-speech.wav")
        return runCatching {
            file.writeBytes(audio)
            val media = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener {
                    it.release()
                    player = null
                    onFinished()
                }
                setOnErrorListener { mp, _, _ ->
                    mp.release()
                    player = null
                    onFinished()
                    true
                }
                prepare()
                start()
            }
            player = media
            Result.Started(fromService = true) as Result
        }.getOrElse { Result.NoVoice }
    }

    /** The phone's own engine. Second choice, and silent for most Indian scripts. */
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
        return Result.Started(fromService = false)
    }

    fun stop() {
        tts.stop()
        player?.let {
            runCatching { it.stop() }
            it.release()
        }
        player = null
    }

    fun shutdown() {
        stop()
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
