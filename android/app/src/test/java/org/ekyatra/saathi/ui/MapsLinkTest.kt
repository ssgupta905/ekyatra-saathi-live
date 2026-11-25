package org.ekyatra.saathi.ui

import org.ekyatra.saathi.data.Trip
import org.ekyatra.saathi.data.TripPlace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertEquals as eq
import org.junit.Test

class MapsLinkTest {
    @Test
    fun theDoorIsGivenToMapsByCoordinates() {
        val trip = Trip(destination = TripPlace("Tata Memorial", 18.99, 72.84, "Dr E Borges Rd, Parel"), city = "Mumbai")
        assertEquals("18.99,72.84", tripDestination(trip))
    }

    @Test
    fun withNoHospitalOnRecordThereIsNoRoute() {
        assertNull(tripDestination(null))
        assertNull(tripDestination(Trip()))
    }

    @Test
    fun threeWaysOfTravellingAreOffered() {
        eq(listOf("transit", "driving", "walking"), TravelMode.entries.map { it.param })
    }
}
