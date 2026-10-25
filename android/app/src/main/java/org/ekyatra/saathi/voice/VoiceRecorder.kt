package org.ekyatra.saathi.voice

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

/**
 * Records a spoken reply to an AAC `.m4a` file, which Whisper reads directly.
 *
 * Voice is not a nicety here: a caregiver who cannot read their own script has no
 * other way in. Recording is mono 16 kHz, which is all speech needs and keeps the
 * upload small on a poor connection.
 */
class VoiceRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null

    val isRecording: Boolean get() = recorder != null

    /** False if the microphone could not be opened (busy, or not permitted). */
    fun start(): Boolean {
        if (recorder != null) return true
        val target = File(context.cacheDir, "reply.m4a").also { it.delete() }
        val next = newRecorder()
        return try {
            next.setAudioSource(MediaRecorder.AudioSource.MIC)
            next.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            next.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            next.setAudioChannels(1)
            next.setAudioSamplingRate(16_000)
            next.setAudioEncodingBitRate(48_000)
            next.setOutputFile(target.absolutePath)
            next.prepare()
            next.start()
            recorder = next
            file = target
            true
        } catch (e: Exception) {
            next.release()
            false
        }
    }

    /** The recording, or null if it was too short to be real. */
    fun stop(): File? {
        val active = recorder ?: return null
        recorder = null
        return try {
            active.stop()
            file
        } catch (e: RuntimeException) {
            // MediaRecorder throws when stopped immediately after starting.
            null
        } finally {
            active.release()
        }
    }

    fun cancel() {
        stop()
        file?.delete()
    }

    @Suppress("DEPRECATION")
    private fun newRecorder(): MediaRecorder =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else MediaRecorder()
}
