package org.ekyatra.saathi.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color as AColor
import android.location.LocationManager
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.ekyatra.saathi.data.NearRanked
import org.ekyatra.saathi.data.RouteLine
import org.ekyatra.saathi.data.Routing
import org.ekyatra.saathi.data.SaathiApi
import org.ekyatra.saathi.data.Trip
import org.ekyatra.saathi.data.Way
import org.ekyatra.saathi.i18n.Strings
import org.ekyatra.saathi.ui.theme.Tokens
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polyline

/** Something on the map the family can pick. */
private data class Target(val name: String, val lat: Double, val lon: Double, val phone: String? = null)

private val NEEDS = listOf("medicine", "tests", "equipment", "clinic")

private fun needLabel(need: String, s: Strings) = when (need) {
    "medicine" -> s.nearMedicine
    "tests" -> s.nearTests
    "equipment" -> s.nearEquipment
    else -> s.nearClinic
}

/** Last position the phone already knows, if the family allowed it. Never sent anywhere. */
private fun lastKnown(context: Context): GeoPoint? {
    val granted = context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
        context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    if (!granted) return null
    val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    return runCatching {
        manager.getProviders(true).mapNotNull { manager.getLastKnownLocation(it) }
            .maxByOrNull { it.time }?.let { GeoPoint(it.latitude, it.longitude) }
    }.getOrNull()
}

/** Where the phone is right now, when it has no recent position stored (API 30+). Not sent anywhere. */
private fun freshFix(context: Context, onFix: (GeoPoint) -> Unit) {
    if (android.os.Build.VERSION.SDK_INT < 30) return
    val granted = context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
        context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    if (!granted) return
    val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    val provider = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).firstOrNull {
        runCatching { manager.isProviderEnabled(it) }.getOrDefault(false)
    } ?: return
    runCatching {
        manager.getCurrentLocation(provider, null, context.mainExecutor) { loc ->
            if (loc != null) onFix(GeoPoint(loc.latitude, loc.longitude))
        }
    }
}

private fun navigate(context: Context, target: Target, way: Way) {
    val mode = if (way == Way.WALK) "w" else "d"
    val intents = listOf(
        Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=${target.lat},${target.lon}&mode=$mode"))
            .setPackage("com.google.android.apps.maps"),
        Intent(Intent.ACTION_VIEW, Uri.parse("geo:${target.lat},${target.lon}?q=${target.lat},${target.lon}(${Uri.encode(target.name)})")),
    )
    for (i in intents) {
        if (runCatching { context.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }.isSuccess) return
    }
}

private fun minutes(seconds: Double) = maxOf(1, Math.round(seconds / 60.0).toInt())
private fun km(metres: Double) = if (metres < 1000) "${metres.toInt()} m" else "%.1f km".format(metres / 1000.0)

/**
 * The map: the hospital, shops and labs around it, where the family is, and the
 * way from one to the other, drawn on the road. Turn-by-turn is handed to Maps,
 * which does it better than we would.
 *
 * Where the family is is read on their phone and used only to draw and to ask
 * the routing service for a line; it does not go through Saathi's servers.
 */
@Composable
fun TripMap(api: SaathiApi, patientId: String, trip: Trip?, s: Strings, onClose: () -> Unit) {
    val context = LocalContext.current
    BackHandler(onBack = onClose)
    val hospital = trip?.destination?.let { Target(it.name, it.latitude, it.longitude) }

    var need by remember { mutableStateOf("medicine") }
    var places by remember { mutableStateOf<List<NearRanked>>(emptyList()) }
    var me by remember { mutableStateOf(lastKnown(context)) }
    var selected by remember { mutableStateOf(hospital) }
    var way by remember { mutableStateOf(Way.WALK) }
    var line by remember { mutableStateOf<RouteLine?>(null) }
    var noRoute by remember { mutableStateOf(false) }
    val routing = remember { Routing(api.client) }

    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        me = lastKnown(context); if (me == null) freshFix(context) { me = it }
    }
    LaunchedEffect(Unit) { if (me == null) ask.launch(Manifest.permission.ACCESS_FINE_LOCATION) }
    // No recent position stored: ask the phone for one now.
    LaunchedEffect(me == null) { if (me == null) freshFix(context) { me = it } }

    LaunchedEffect(need) {
        places = try {
            api.nearby(patientId, need, "hospital").places
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            emptyList()
        }
    }

    // The line: from the family to the place; or, with no location, from the hospital to the place.
    LaunchedEffect(selected, way, me) {
        val to = selected
        val from = me?.let { it.latitude to it.longitude } ?: hospital?.let { it.lat to it.lon }
        line = null; noRoute = false
        if (to == null || from == null || (from.first == to.lat && from.second == to.lon)) return@LaunchedEffect
        val got = withContext(Dispatchers.IO) { routing.route(from, to.lat to to.lon, way) }
        line = got; noRoute = got == null
    }

    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val map = remember {
        Configuration.getInstance().userAgentValue = "saathi-care-navigator/1.0"
        Configuration.getInstance().osmdroidBasePath = context.cacheDir
        Configuration.getInstance().osmdroidTileCache = context.cacheDir.resolve("tiles")
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            minZoomLevel = 4.0
            maxZoomLevel = 19.0
            controller.setZoom(16.0)
        }
    }
    DisposableEffect(lifecycle) {
        val watcher = LifecycleEventObserver { _, e ->
            if (e == Lifecycle.Event.ON_RESUME) map.onResume()
            if (e == Lifecycle.Event.ON_PAUSE) map.onPause()
        }
        lifecycle.addObserver(watcher)
        onDispose { lifecycle.removeObserver(watcher); map.onDetach() }
    }

    Box(Modifier.fillMaxSize().background(Tokens.plane).testTag("trip-map")) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { map },
            update = { view ->
                view.overlays.clear()
                line?.let { l ->
                    view.overlays.add(Polyline().apply {
                        setPoints(l.points.map { GeoPoint(it.first, it.second) })
                        outlinePaint.color = AColor.parseColor("#1D4ED8")
                        outlinePaint.strokeWidth = 12f
                    })
                }
                fun pin(t: Target, label: String, onTap: () -> Unit) = view.overlays.add(Marker(view).apply {
                    position = GeoPoint(t.lat, t.lon); title = label
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    setOnMarkerClickListener { _, _ -> onTap(); true }
                })
                places.forEach { r -> pin(Target(r.place.name, r.place.latitude, r.place.longitude, r.place.phone), r.place.name) { selected = Target(r.place.name, r.place.latitude, r.place.longitude, r.place.phone) } }
                hospital?.let { h -> pin(h, "${s.mapHospital}: ${h.name}") { selected = h } }
                me?.let { m -> pin(Target(s.mapYou, m.latitude, m.longitude), s.mapYou) { } }
                // Frame what matters: the destination, where they are, and the line between.
                val pts = buildList {
                    selected?.let { add(GeoPoint(it.lat, it.lon)) }
                    me?.let { add(it) }
                    if (me == null) hospital?.let { add(GeoPoint(it.lat, it.lon)) }
                    line?.points?.let { l -> addAll(l.map { GeoPoint(it.first, it.second) }) }
                }
                // Frame the points; a single point (or points on top of each other) would
                // zoom past where any map tiles exist, so those just centre at street level.
                val box = pts.takeIf { it.size >= 2 }?.let { BoundingBox.fromGeoPoints(it) }
                if (box != null && (box.latitudeSpan > 0.0005 || box.longitudeSpan > 0.0005)) {
                    view.post { view.zoomToBoundingBox(box, false, 120); if (view.zoomLevelDouble > 18.0) view.controller.setZoom(17.0) }
                } else pts.firstOrNull()?.let { view.controller.setZoom(16.0); view.controller.setCenter(it) }
                view.invalidate()
            },
        )

        Column(Modifier.fillMaxWidth().background(Tokens.surface.copy(alpha = 0.95f)).statusBarsPadding().padding(12.dp)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.horizontalScroll(rememberScrollState()),
            ) {
                Text(s.mapClose, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Tokens.blue700,
                    modifier = Modifier.testTag("map-close").clip(RoundedCornerShape(Tokens.radiusPill))
                        .border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusPill)).clickable(onClick = onClose).padding(14.dp, 8.dp))
                NEEDS.forEach { n ->
                    Text(needLabel(n, s), fontSize = 13.sp, fontWeight = FontWeight.Medium,
                        color = if (need == n) Tokens.surface else Tokens.blue700,
                        maxLines = 1, softWrap = false,
                        modifier = Modifier.testTag("map-need-$n").clip(RoundedCornerShape(Tokens.radiusPill))
                            .background(if (need == n) Tokens.blue600 else Tokens.surface)
                            .border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusPill))
                            .clickable { need = n }.padding(10.dp, 8.dp))
                }
            }
            if (me == null) Text(s.mapAllow, fontSize = 12.sp, color = Tokens.ink3, modifier = Modifier.padding(top = 6.dp)
                .clickable { ask.launch(Manifest.permission.ACCESS_FINE_LOCATION) })
        }

        Column(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(Tokens.surface)
                .padding(16.dp),
        ) {
            val t = selected
            if (t == null) {
                Text(s.mapPick, fontSize = 14.sp, color = Tokens.ink3)
            } else {
                Text(t.name, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Tokens.ink)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                    listOf(Way.WALK to s.mapWalk, Way.CAR to s.mapCar).forEach { (w, label) ->
                        Text(label, fontSize = 14.sp, fontWeight = FontWeight.Medium,
                            color = if (way == w) Tokens.surface else Tokens.blue700,
                            modifier = Modifier.testTag("map-way-${w.profile}").clip(RoundedCornerShape(Tokens.radiusPill))
                                .background(if (way == w) Tokens.blue600 else Tokens.surface)
                                .border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusPill))
                                .clickable { way = w }.padding(14.dp, 8.dp))
                    }
                }
                Text(
                    line?.let { s.mapRoute.replace("{d}", km(it.metres)).replace("{t}", minutes(it.seconds).toString()) }
                        ?: if (noRoute) s.mapNoRoute else if (me == null && t === hospital) s.mapAllow else "…",
                    fontSize = 15.sp, color = if (noRoute) Tokens.critical else Tokens.ink2,
                    modifier = Modifier.padding(top = 8.dp).testTag("map-route"),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 10.dp)) {
                    Text(s.mapNavigate, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Tokens.surface,
                        modifier = Modifier.testTag("map-navigate").clip(RoundedCornerShape(Tokens.radiusPill)).background(Tokens.blue600)
                            .clickable { navigate(context, t, way) }.padding(16.dp, 10.dp))
                    t.phone?.let { phone ->
                        Text(s.nearCall, fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Tokens.blue700,
                            modifier = Modifier.clip(RoundedCornerShape(Tokens.radiusPill))
                                .border(1.dp, Tokens.line, RoundedCornerShape(Tokens.radiusPill))
                                .clickable { dial(context, phone) }.padding(16.dp, 10.dp))
                    }
                }
            }
            Text(s.nearOsm, fontSize = 10.sp, color = Tokens.ink4, modifier = Modifier.padding(top = 8.dp))
        }
    }
}
