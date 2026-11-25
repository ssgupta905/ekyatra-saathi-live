package org.ekyatra.saathi.ui

import org.ekyatra.saathi.data.Trip
import org.ekyatra.saathi.data.TripPlace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HandoffTest {
    @Test
    fun theAppSaathiAskedComesFirst() {
        assertEquals("Ola", appsFor("ride", "Ola").first().name)
        assertEquals("OYO", appsFor("stay", "OYO, Parel").first().name)
    }

    @Test
    fun withNoMatchTheOrderIsTheListedOne() {
        assertEquals(PARTNER_APPS.getValue("ride"), appsFor("ride", "Regional taxi network"))
        assertEquals(PARTNER_APPS.getValue("ride"), appsFor("ride", null))
    }

    @Test
    fun aStepWithNoAppsOffersNone() {
        assertTrue(appsFor("reports", "the lab").isEmpty())
        assertTrue(appsFor("visit", null).isEmpty())
    }

    @Test
    fun everyAppCanFallBackToAWebsiteAndIsListedOnce() {
        val all = PARTNER_APPS.values.flatten()
        assertTrue(all.all { it.website.startsWith("https://") && it.packageName.contains('.') })
        assertEquals(all.size, all.map { it.packageName }.toSet().size)
    }

    @Test
    fun theManifestMayLookForEveryApp() {
        // Android 11+ hides an app that is not named in <queries>; a missing one would never open.
        val manifest = java.io.File("src/main/AndroidManifest.xml").readText()
        PARTNER_APPS.values.flatten().forEach {
            assertTrue("${it.packageName} missing from <queries>", manifest.contains("\"${it.packageName}\""))
        }
    }

    @Test
    fun theDestinationIsTheHospitalsAddressWhenOneIsOnRecord() {
        val trip = Trip(destination = TripPlace("Tata Memorial", 19.0, 72.8, "Tata Memorial Hospital, Parel, Mumbai"))
        assertEquals("Tata Memorial Hospital, Parel, Mumbai", destinationText(trip))
    }

    @Test
    fun noEntranceOnRecordMeansNothingToCopyNotAGuess() {
        assertNull(destinationText(null))
        assertNull(destinationText(Trip(destination = null, city = "Mumbai")))
        assertNull(destinationText(Trip(destination = TripPlace("H", 1.0, 2.0, "  "))))
    }
}
