package org.ekyatra.saathi.ui

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import org.ekyatra.saathi.data.Trip

/**
 * Opening the apps a journey runs through, from Saathi.
 *
 * A family books a ride in Uber or Ola, a room through a travel app, medicines
 * from a pharmacy app. Saathi does not stand in for those apps; it gets the
 * family into them. Tapping a name opens the app if it is on the phone, its Play
 * Store page if it is not, and its website if there is no store.
 *
 * What does and does not go with the tap, because it matters:
 *
 * - Nothing about the family: no name, no phone, no reason for travelling, and
 *   never where they are staying.
 * - For a ride or a stay, the hospital's address is copied to the clipboard, and
 *   shown on the screen, for the family to paste where the app asks "Where to?".
 *   Uber, Ola and MakeMyTrip each ignore a destination, city or dates sent in by
 *   an outside app unless the sender is a registered partner, so there is no
 *   honest way to fill it in for them; pasting is what works on every phone today.
 * - Uber is also told "my location" as the pickup, which it does honour, so the
 *   pickup is already right.
 *
 * Package names are the apps' published Play Store ids. A wrong id fails
 * softly (the store page is missing, so the website opens), which is why every
 * entry carries a website.
 */
data class PartnerApp(
    val name: String,
    val packageName: String,
    val website: String,
)

/** The apps to offer for each kind of step in the chain. */
val PARTNER_APPS: Map<String, List<PartnerApp>> = mapOf(
    "ride" to listOf(
        PartnerApp("Uber", "com.ubercab", "https://m.uber.com"),
        PartnerApp("Ola", "com.olacabs.customer", "https://www.olacabs.com"),
        PartnerApp("Rapido", "com.rapido.passenger", "https://www.rapido.bike"),
    ),
    "stay" to listOf(
        PartnerApp("OYO", "com.oyo.consumer", "https://www.oyorooms.com"),
        PartnerApp("MakeMyTrip", "com.makemytrip", "https://www.makemytrip.com"),
    ),
    "pharmacy" to listOf(
        PartnerApp("PharmEasy", "com.phonegt", "https://pharmeasy.in"),
        PartnerApp("Tata 1mg", "com.aranoah.healthkart.plus", "https://www.1mg.com"),
    ),
)

/**
 * The apps for this step, with the one Saathi asked on the family's behalf first.
 * `party` is what the journey names ("Uber", "OYO, Parel"); a match moves that app up.
 */
fun appsFor(kind: String, party: String?): List<PartnerApp> {
    val all = PARTNER_APPS[kind] ?: return emptyList()
    val asked = party?.lowercase().orEmpty()
    return all.sortedBy { if (asked.contains(it.name.lowercase())) 0 else 1 }
}

/**
 * The railway's own booking app. IRCTC takes no station, date or train from an
 * outside app, so the screen shows the two stations and the family types them;
 * the tap gets them into the app, or its store page, or the website.
 */
val IRCTC_APP = PartnerApp("IRCTC Rail Connect", "cris.org.in.prs.ima", "https://www.irctc.co.in/nget/train-search")

enum class Opened { APP, STORE, WEBSITE, NOTHING }

/** Open a web page. False when nothing on the phone can show one. */
fun openWeb(context: Context, url: String): Boolean =
    start(context, Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))

/** The hospital's address for the family to paste, or null when there is none on record. */
fun destinationText(trip: Trip?): String? = trip?.destination?.address?.takeIf { it.isNotBlank() }

/** The kinds of step whose apps ask where the family is going. */
private val ASKS_WHERE = setOf("ride", "stay")

/**
 * What to open the app with, when the app takes anything at all. Only Uber does:
 * "my location" as the pickup, which it honours. Everything else opens the app.
 */
internal fun deepLinkFor(app: PartnerApp): Uri? = when (app.packageName) {
    "com.ubercab" -> Uri.parse("https://m.uber.com/ul/?action=setPickup&pickup=my_location")
    else -> null
}

/** Open the app, or where to get it. Returns which of those happened. */
fun openPartnerApp(context: Context, app: PartnerApp, kind: String = "", trip: Trip? = null): Opened {
    if (kind in ASKS_WHERE) copyDestination(context, trip)
    val pm = context.packageManager
    deepLinkFor(app)?.let { link ->
        val intent = Intent(Intent.ACTION_VIEW, link).setPackage(app.packageName)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.resolveActivity(pm) != null && start(context, intent)) return Opened.APP
    }
    pm.getLaunchIntentForPackage(app.packageName)?.let { launch ->
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (start(context, launch)) return Opened.APP
    }
    val store = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=${app.packageName}"))
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    if (store.resolveActivity(pm) != null && start(context, store)) return Opened.STORE
    val site = Intent(Intent.ACTION_VIEW, Uri.parse(app.website)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    return if (start(context, site)) Opened.WEBSITE else Opened.NOTHING
}

private fun copyDestination(context: Context, trip: Trip?) {
    val text = destinationText(trip) ?: return
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("Hospital address", text))
}

private fun start(context: Context, intent: Intent): Boolean = try {
    context.startActivity(intent)
    true
} catch (_: ActivityNotFoundException) {
    false
} catch (_: SecurityException) {
    false
}

/**
 * Directions in Google Maps, one tap per way of travelling.
 *
 * The documented Maps URL needs no key and shows the time and route for the
 * mode chosen, live, on the family's own phone. "Where to" is the hospital's
 * door by coordinates when the directory has them, else its address.
 * Nothing about the family goes in the link; with no origin Maps starts from
 * where the phone is.
 */
enum class TravelMode(val param: String) { TRANSIT("transit"), DRIVING("driving"), WALKING("walking") }

internal fun mapsLink(destination: String, origin: String?, mode: TravelMode): Uri {
    val b = Uri.Builder().scheme("https").authority("www.google.com").appendPath("maps").appendPath("dir").appendPath("")
        .appendQueryParameter("api", "1")
        .appendQueryParameter("destination", destination)
        .appendQueryParameter("travelmode", mode.param)
    if (!origin.isNullOrBlank()) b.appendQueryParameter("origin", origin)
    return b.build()
}

internal fun tripDestination(trip: Trip?): String? =
    trip?.destination?.let { "${it.latitude},${it.longitude}" } ?: destinationText(trip)

/** Open Maps. False when nothing on the phone can show a map link. */
fun openMaps(context: Context, destination: String, origin: String?, mode: TravelMode): Boolean =
    start(context, Intent(Intent.ACTION_VIEW, mapsLink(destination, origin, mode)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
