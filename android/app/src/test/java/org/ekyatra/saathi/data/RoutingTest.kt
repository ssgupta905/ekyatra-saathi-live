package org.ekyatra.saathi.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RoutingTest {
    @Test
    fun aRoutingAnswerBecomesALineInLatLonOrder() {
        val line = parseRoute(
            """{"code":"Ok","routes":[{"distance":1234.5,"duration":600.0,
               "geometry":{"type":"LineString","coordinates":[[72.84,19.0],[72.85,19.01]]}}]}""",
        )!!
        assertEquals(19.0 to 72.84, line.points.first())
        assertEquals(1234.5, line.metres, 0.0)
        assertEquals(600.0, line.seconds, 0.0)
    }

    @Test
    fun noRouteIsNullNotACrash() {
        assertNull(parseRoute("""{"code":"NoRoute","routes":[]}"""))
        assertNull(parseRoute("not json"))
    }
}
