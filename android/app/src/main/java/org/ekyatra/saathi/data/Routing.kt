package org.ekyatra.saathi.data

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

/** A way to walk or drive, drawn on the map. */
data class RouteLine(
    /** (latitude, longitude) points, in order. */
    val points: List<Pair<Double, Double>>,
    val metres: Double,
    val seconds: Double,
)

enum class Way(val profile: String) { WALK("foot"), CAR("car") }

/**
 * A walking or driving line between two points, from OpenStreetMap's public
 * routing service, asked **from the phone itself**: where the family is stands
 * between them and that service, and never passes through Saathi's servers.
 *
 * It is a free service meant for light use. It knows roads and paths, not buses
 * or trains; those come from the route planner.
 */
class Routing(private val client: OkHttpClient) {
    fun route(from: Pair<Double, Double>, to: Pair<Double, Double>, way: Way): RouteLine? {
        val coords = "${from.second},${from.first};${to.second},${to.first}"
        val url = "https://routing.openstreetmap.de/routed-${way.profile}/route/v1/${way.profile}/$coords" +
            "?overview=full&geometries=geojson"
        val request = Request.Builder().url(url).header("User-Agent", "saathi-care-navigator/1.0").build()
        return try {
            client.newCall(request).execute().use { r -> if (r.isSuccessful) parseRoute(r.body.string()) else null }
        } catch (_: Exception) {
            null
        }
    }
}

/** An OSRM answer as a line, or null when there is no way. Public so it can be tested. */
fun parseRoute(text: String): RouteLine? = runCatching {
    val route = Json.parseToJsonElement(text).jsonObject["routes"]!!.jsonArray.firstOrNull()?.jsonObject ?: return null
    val coords = route["geometry"]!!.jsonObject["coordinates"]!!.jsonArray.map {
        val pair = it.jsonArray
        pair[1].jsonPrimitive.content.toDouble() to pair[0].jsonPrimitive.content.toDouble()
    }
    RouteLine(
        coords,
        (route["distance"] as JsonPrimitive).doubleOrNull ?: 0.0,
        (route["duration"] as JsonPrimitive).doubleOrNull ?: 0.0,
    )
}.getOrNull()

