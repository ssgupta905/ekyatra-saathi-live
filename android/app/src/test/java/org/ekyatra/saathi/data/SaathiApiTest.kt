package org.ekyatra.saathi.data

import kotlinx.coroutines.test.runTest
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/** What the client sends and how it reads what comes back, with no network. */
class SaathiApiTest {
    private class Recorder(private val code: Int = 200, private val body: String = "{}") : Interceptor {
        val requests = mutableListOf<Request>()

        override fun intercept(chain: Interceptor.Chain): Response {
            requests += chain.request()
            return Response.Builder()
                .request(chain.request())
                .protocol(Protocol.HTTP_1_1)
                .code(code)
                .message("test")
                .body(body.toResponseBody("application/json".toMediaType()))
                .build()
        }
    }

    private fun api(recorder: Recorder) =
        SaathiApi("http://host/api/", OkHttpClient.Builder().addInterceptor(recorder).build())

    private fun Request.bodyText(): String = Buffer().also { body?.writeTo(it) }.readUtf8()

    @Test
    fun `urls are joined without doubling the slash`() = runTest {
        val recorder = Recorder(body = "[]")
        api(recorder).patients()
        assertEquals("http://host/api/patients", recorder.requests.single().url.toString())
    }

    @Test
    fun `choosing a language is a patch carrying the language and who chose it`() = runTest {
        val recorder = Recorder(body = """{"language":"bn","changed":true}""")
        val result = api(recorder).chooseLanguage("P1", "bn")

        val request = recorder.requests.single()
        assertEquals("PATCH", request.method)
        assertEquals("/api/patients/P1/language", request.url.encodedPath)
        assertTrue(request.bodyText().contains(""""language":"bn""""))
        assertTrue(request.bodyText().contains(""""chosen_by":"family""""))
        assertTrue(result.changed)
    }

    @Test
    fun `a reply goes to the inbound endpoint with the patient and the text`() = runTest {
        val recorder = Recorder()
        api(recorder).say("P1", "Can we change the date?")

        val request = recorder.requests.single()
        assertEquals("POST", request.method)
        assertEquals("/api/live/inject", request.url.encodedPath)
        assertTrue(request.bodyText().contains(""""patient_id":"P1""""))
        assertTrue(request.bodyText().contains("Can we change the date?"))
    }

    @Test
    fun `a recording is uploaded as an m4a under its real name`() = runTest {
        val file = File.createTempFile("reply", ".m4a").apply { writeBytes(ByteArray(2_000)) }
        val recorder = Recorder(body = """{"text":"hello","language":"hi","sent":false}""")
        val transcript = api(recorder).transcribe("P1", file, "hi")

        val request = recorder.requests.single()
        assertEquals("/api/voice/transcribe", request.url.encodedPath)
        val text = request.bodyText()
        assertTrue(text.contains("""name="audio"; filename="${file.name}""""))
        assertTrue(text.contains("Content-Type: audio/m4a"))
        assertTrue(text.contains("""name="patient_id""""))
        assertEquals("hello", transcript.text)
        assertEquals(false, transcript.sent)
    }

    @Test
    fun `a failure carries the status and the backend's own explanation`() = runTest {
        val recorder = Recorder(code = 503, body = """{"detail":"speech-to-text needs GROQ_API_KEY"}""")
        try {
            api(recorder).health()
            fail("expected an ApiException")
        } catch (e: ApiException) {
            assertEquals(503, e.status)
            assertTrue(e.message!!.contains("503"))
            assertTrue(e.message!!.contains("needs GROQ_API_KEY"))
        }
    }

    @Test
    fun `an unreachable server is reported as an ApiException with no status`() = runTest {
        val failing = OkHttpClient.Builder()
            .addInterceptor { throw java.io.IOException("connection refused") }
            .build()
        try {
            SaathiApi("http://host/api", failing).health()
            fail("expected an ApiException")
        } catch (e: ApiException) {
            assertEquals(null, e.status)
            assertTrue(e.message!!.contains("could not reach"))
        }
    }
}
