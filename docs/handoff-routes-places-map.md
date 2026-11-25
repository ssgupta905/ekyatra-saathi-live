# Handoff: family finances, route guidance, nearby places and the map

Written 25 Nov 2026 for whoever picks this up next. Branch: `orchestrator-pathways-readiness`.
Read this top to bottom once; the last two sections (what is blocked, what to do next) are the
ones you will act on.

## 1. What this batch is

Four things for the **family** (patient + caregiver) app, mostly on Android, all backed by the
FastAPI service:

| Feature | Where a family sees it | Backend |
|---|---|---|
| **Kharcha**: what the journey costs, this month and next | Android 4th tab "Spends" (web has had it since `5774e56`) | `api/kharcha.py` (already pushed) |
| **Ways to go**: which bus, boarded where, when; weighed against the family's money | Android, Plan tab, "Choose how to get there" | `api/trip.py`, `orchestrator/trip_options.py`, `adapters/routes/` |
| **Near you**: pharmacies, labs, equipment, clinics near the hospital or home | Android, Plan tab, "Near you" | `api/nearby.py`, `orchestrator/nearby_needs.py`, `adapters/places/` |
| **Map**: hospital, places, your position, walking/driving line, hand-off to Maps for turn-by-turn | Android, "Show on map" in Near you | mostly on-device (`ui/TripMap.kt`, `data/Routing.kt`) |

Plus: open-in-app buttons (Uber/Ola/Rapido/OYO/MakeMyTrip/PharmEasy/1mg), the hospital's
entrance coordinates and address (migration `0014`), and 5-language strings for all of it.

## 2. Rules this code holds to (do not break these)

These came from earlier decisions; tests enforce several of them.

1. **A rupee figure is shown only if someone gave it.** A route service's fare, a seller's quote,
   or the family's own words. When none exists the screen says "cost not known". There is no
   rate table anywhere (`test_kharcha*`, `tests/test_trip_options.py`).
2. **The planner never reads money.** Money may reorder *which cab is asked*, never a clinical
   date. `api/trip.py` and `api/nearby.py` read only "how much of the family's own monthly limit is
   free" / "did they state a limit", and are allow-listed in `tests/test_kharcha_api.py`.
3. **Nothing about the family goes to a map service.** Only a point and a generic category
   ("pharmacy"). No names, no diagnosis, no condition. Ratings and reviews are never requested
   (`test_no_rating_is_ever_read`). Doctors are never ranked or recommended.
4. **The family's position never passes through Saathi's servers.** The map reads the GPS on the
   phone and asks the routing service directly from the phone. The typed "starting from" place for
   the bus planner does go to the route service for one request and is not stored.
5. **We never claim a shop has stock.** The card says "call to check".
6. **Demo providers are refused when `SAATHI_ENVIRONMENT=production`** (`config.py`).
7. Ports/adapters layering is enforced by `tests/test_architecture.py`: ports and domain import
   no `httpx`; adapters import only domain/ports/db/ledger.

## 3. How to run it locally

```bash
# backend (from repo root; python venv at .venv)
SAATHI_WORLD=real SAATHI_SEED_DEMO=true SAATHI_AUTH=off \
SAATHI_ROUTES_PROVIDER=demo SAATHI_PLACES_PROVIDER=demo \
SAATHI_TOOLS_ALLOW_NETWORK=true \
.venv/bin/uvicorn saathi.main:app --app-dir backend --port 8000

# android (JDK 17), build pointing at the local API; phone/emulator need a tunnel
cd android
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
./gradlew assembleDebug -PapiBase=http://localhost:8000/api
adb reverse tcp:8000 tcp:8000
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

- Meena (`DEMO-3`, Varanasi -> Tata Memorial, Mumbai) is the best family to try: she has a
  bookable ride quote, Kharcha numbers, and the hospital has entrance coordinates.
- Tests: `.venv/bin/python -m pytest -q` (1054 passing when this was written),
  `cd android && ./gradlew testDebugUnitTest`, and the web `npx vitest run` (one test,
  `apps.test.ts`, fails if your local `.claude/launch.json` has extra servers; that file is
  deliberately not committed).
- Node: use node 22 (`PATH=/opt/homebrew/opt/node@22/bin:$PATH`). After editing
  `frontend/packages/i18n/src/i18n.ts` regenerate the Android strings:
  `node android/tools/generate.mjs` (writes `Translations.kt`). Both the Android `I18nTest`
  and `packages/i18n/src/android.test.ts` check the two stay in step.

## 4. What is done, in detail

### 4.1 Kharcha on Android (`ui/KharchaTab.kt`)
Models/API/ViewModel state added (`data/Models.kt`, `SaathiApi.kt`, `FamilyViewModel.kt`:
`Tab.KHARCHA`, `kharcha`, `kharchaAction`). The tab shows: nudges, "ready to book" (open-network
ride, with the share-your-name-and-phone checkbox before Book), "to pay" (opens the vendor's own
pay link), "is this right?" proposals (Yes/No), this/next month with spent/booked/expected and the
working ("based on your last 3 visits"), a two-month bar chart, add-a-spend form (words and/or
amount and category), and the monthly-limit form. Verified live on an emulator in Hindi.
Not exercised on a device: pay-link opening, Book, the add/confirm forms (built, compile, not tapped).

### 4.2 Ways to go (bus/train step by step) - **built, not yet run on real data**
- `domain/itinerary.py`: `RouteOption`, `Step` (line, board_at, get_off_at, stops, departs/arrives),
  `FareBasis`, `Weighed`, `Guidance`.
- `ports/routes.py`: `RoutePlanner` protocol, `RoutesUnavailable`.
- `adapters/routes/google.py`: **Google Routes API v2** `computeRoutes` (the Directions API is closed
  to new projects). Field-masked, `regionCode=IN`, transit + drive. Fare only when the response has
  one. The key never appears in a log or error text.
  `adapters/routes/demo.py`: three invented options, labelled "sample timetable - not real".
- `orchestrator/trip_options.py` (pure): drops options that cannot arrive by the given time; sets aside
  options whose *known* cost exceeds what is left of the family's monthly limit; among the rest
  prefers fewest changes, then least walking, then fastest. Emits reason codes
  (`fits_budget`, `some_over_budget`, `all_over_budget`, `cost_unknown`, `say_what_you_can_manage`,
  `fewest_changes`, ...) that the app translates. An unknown cost is never called cheap or dear.
- `GET /api/patients/{id}/trip/options?leg=far|near&origin=...&arrive_by=...` (family only).
  `far` starts at the patient's home district; `near` at a typed place. A car option carries a
  seller's quote only if the family has one for this ride.
- Android: `ui/WayPlanner.kt` inside `RouteCard` (`ui/JourneySections.kt`): per-leg "Show ways to go",
  recommended card first, each step spelled out, cost with its basis, tags, leave-by time, reasons.
  The older Maps mode buttons stay below it as a fallback.
- Tests: `tests/test_trip_options.py` (weighing + parsing a recorded-shape Routes response).

### 4.3 Near you (`ui/NearYou.kt`, `api/nearby.py`)
- `domain/places.py`: `PlaceKind` (pharmacy, jan_aushadhi, lab, equipment, clinic, physio),
  `Place` with opening-hours `Period`s and `open_at(when)` (IST, handles past-midnight and 24h).
- `ports/places.py`: `PlaceFinder`. Adapters in `adapters/places/`: `osm.py` (Overpass),
  `google.py` (Places API New, text search, no ratings), `demo.py`.
- `adapters/places/osm.py` has a real parser for OSM `opening_hours` (common shapes only; anything
  stranger -> "hours not known", never guessed), 12-hour in-memory cache, mirror fallback, and a
  polite `warm()` that stops after two failures. Startup warms hospital doors (`bootstrap/lifespan.py`).
- `orchestrator/nearby_needs.py`: ranks by open-when-they-arrive, then Jan Aushadhi first if the
  family stated a limit, then straight-line distance.
- `GET /api/patients/{id}/nearby?need=medicine|tests|equipment|clinic&near=hospital|home|place`.
- Attribution: "(c) OpenStreetMap contributors" / "Places from Google" are shown.
- Tests: `tests/test_nearby.py`.

### 4.4 Map (`ui/TripMap.kt`, `data/Routing.kt`)
osmdroid map (OSM tiles). Pins: hospital, nearby places for the chosen need, your position.
Tap a pin -> line from you (or from the hospital when no location) with Walk/Car toggle and
"6.2 km - 83 min"; "Start directions in Maps" fires `google.navigation:` with a `geo:` fallback; Call
dials. Routing is from `routing.openstreetmap.de` (`routed-foot`/`routed-car`), called from the
phone. Verified on an emulator: real Parel tiles, a real walking route drawn.
Gotchas already fixed (do not reintroduce): osmdroid needs `ACCESS_NETWORK_STATE` or it thinks it is
offline; a bounding box of one point zooms to level 29 where no tiles exist (see the framing code).

### 4.5 Smaller pieces
- Open-in-app buttons and clipboard of the hospital address (`ui/Handoff.kt`; apps ignore outside
  destinations unless the sender is a registered partner, so we copy the address instead).
- Hospital entrance lat/lng/address (migration `0014_hospital_entrance.py`, `domain/registry.py`,
  `bootstrap/seed.py` `top_up_entrances`), exposed as a `trip` block on the guide (`api/guide.py`).
- `.env.example` documents the new settings.

## 5. What is blocked, and on whom

| Blocker | State | Owner |
|---|---|---|
| **Google Routes/Places return HTTP 403 `PERMISSION_DENIED`** for every call, even driving | Routes, Places (New), Geocoding are enabled; project is linked to a free-trial billing account with credit; key `saathi-routes` is restricted to those three APIs; the Maps metrics page shows zero requests, so calls are refused before counting. Cause unknown. Leading guess: a **free-trial account cannot use Maps Platform until upgraded to a full account** (unverified). | Account owner: click Upgrade (credit is meant to carry over - read the prompt), or Google Cloud support. Then re-run the check in 7.1. |
| **ABDM sandbox account** (for the Health Facility Registry / professionals registry) | Signed up, "under review". Registration for the HFR itself is for facility managers only; read access comes through the sandbox/production onboarding. UHI (Beckn-based discovery of consultations/ambulance/blood banks) is on the same sandbox and fits our Beckn BAP adapter. | Account owner, then a dev to build the registry adapter. |
| **Overpass public servers** are overloaded (502/504, 30-40 s answers) | Adapter degrades to "could not load" and the app says so. Not acceptable for production. | Dev: build the local-data option in 6.1. |
| **Render env vars** | None of the new vars are set on Render. | Account owner pastes the key themselves; never commit or paste a key into chat. |

## 6. What to build next, in priority order

### 6.1 Local healthcare places table (replaces live Overpass) - highest value
Do not ship the 1.7 GB India extract to Render. Filter it elsewhere and load only healthcare points:
1. Migration `0015`: a `places` table (osm id, kind, name, address, lat, lon, phone, opening_hours,
   loaded_at) with an index on (kind, lat, lon).
2. `adapters/places/sql.py`: `SqlPlaces` implementing `PlaceFinder` with a bounding-box query.
   `SAATHI_PLACES_PROVIDER=local`.
3. Loader tool (`python -m saathi.tools.load_places FILE`, upsert by osm id, uses `SAATHI_RECORDS_URL`).
4. A scheduled GitHub Action (monthly): download Geofabrik `india-latest.osm.pbf`, filter with
   `osmium tags-filter` for `amenity=pharmacy|clinic|doctors`, `healthcare=*`, `shop=medical_supply`,
   name~Jan Aushadhi, then run the loader against Supabase (needs a repo secret with the DB URL).
5. Tests: radius query, upsert, the no-ratings rule. ~100-150 MB in Postgres; fits Supabase free tier.
Licence: ODbL; the credit string is already shown.

### 6.2 Get Google working (see section 5), then
- Run the real-API check (7.1). Compare an actual Mumbai Central -> Tata Memorial transit response
  with `tests/test_trip_options.py::DIRECTIONS` and fix the parser against reality.
- Add Route Matrix: rank nearby places by real travel time instead of straight-line metres.
- Optional: Autocomplete for the "starting from" box; Geocoding to replace Nominatim.
- Set on Render: `SAATHI_ROUTES_PROVIDER=google`, `SAATHI_PLACES_PROVIDER=google` (or `local`),
  `SAATHI_GOOGLE_MAPS_API_KEY` (secret). Keep the key restricted to the three APIs.

### 6.3 Map polish
- Tile provider for production (MapTiler/Stadia with a key, or self-hosted); the public OSM tile
  server is for light use.
- Show the user's position marker inside the visible frame; add an "I am here" re-centre button.
- Show the bus/train legs on the map once the route planner returns them (currently walk/drive only).
- Make map pins distinguish kinds (pharmacy vs lab) with the existing `Glyph` icons.
- Run on a real phone: the emulator's network is slow and its Maps app crashes, so Maps hand-off and
  GPS were not verified there. Real-device pass needed for: `google.navigation:` launch, location
  permission flow, dial, Maps hand-off.

### 6.4 Android gaps
- Kharcha forms and Book/pay have not been tapped through on a device.
- No Android UI test coverage for the new screens (unit tests cover parsing/ranking only).
- `OpenInApp` Uber deep link only sets pickup=my_location; destinations need partner status.
- The family-web app does not have the route planner / near-you / map yet (Android only).

### 6.5 ABDM
- When the sandbox is approved: HFR/HPR adapter behind a new port; use it to mark map results as
  "registered facility" and to verify a doctor's chamber the hospital has approved. Never show a
  Google/OSM listing as "verified" on its own.
- UHI: add a Beckn provider (`adapters/beckn/`) for consultations/ambulance/blood bank discovery.

### 6.6 Hospital-side curation (control centre)
A page where staff review nearby candidates and promote one into the partner directory
(`Organisation`, mode PEOPLE) so it can be asked through the Partner app. Doctor chambers should be
staff-approved only. Pharmacies/labs can stay automatic.

## 7. How to verify things

### 7.1 Is Google working? (from the Cloud console page, key never leaves the browser)
Open the Credentials page, Show key, then from the console tab's JS console POST to
`https://routes.googleapis.com/directions/v2:computeRoutes` with headers `X-Goog-Api-Key` and
`X-Goog-FieldMask: routes.duration`, body
`{"origin":{"address":"Mumbai Central Station"},"destination":{"address":"Tata Memorial Hospital, Parel, Mumbai"},"travelMode":"DRIVE"}`.
A 200 with a duration means it is live. 403 `ACCESS_DENIED` means it is still blocked (section 5).
Do the same against `https://places.googleapis.com/v1/places:searchText`.

### 7.2 Are the OSM places real?
`curl -A "saathi-care-navigator/1.0" --data-urlencode 'data=[out:json][timeout:25];(nwr["amenity"="pharmacy"](around:1500,19.0046,72.843););out center tags 5;' https://overpass-api.de/api/interpreter`
returned a real Parel pharmacy with `opening_hours` and a `mobile` tag (and took 39 s). If you get
502/504 the server is busy; that is why 6.1 exists.

## 8. Decisions to keep in mind (from the product owner)
- Vendors collect payment through their own pay links; Saathi never holds money.
- Finance is agentic: no staff in the money loop. The family is the only human who confirms.
  Staff only get a `NEEDS_HELP` alert with no amounts.
- Beckn/vendors and the budget portal were built in parallel and meet in the spends ledger.
- Prototype stance for demos: real sign-ins and OTPs are typed by the human; nobody makes real
  payments or bookings during a demo.
- Secrets: API keys are pasted by the account owner into Render, never into chat, code or the repo.

---

# Picked up 25 Nov 2026: the local places table, and what a device still has to prove

Written by the next pair of hands, against the handoff above.

## What is now done

**§6.1, the local places table — built and running.** This was the top of your
own priority list and it removes the Overpass blocker entirely.

- Migration `0015` creates `places` (osm id, kind, name, address, lat, lon,
  phone, opening_hours, loaded_at) with an index on `(kind, latitude, longitude)`.
- `adapters/places/sql.py:SqlPlaces` implements `PlaceFinder` against it.
  `SAATHI_PLACES_PROVIDER=local`.
- `python -m saathi.tools.load_places FILE --write` loads a GeoJSON export,
  upserting on OpenStreetMap's own id so a monthly reload updates rather than
  duplicates. Nothing is ever deleted: a place missing from this month's
  extract is far more often a mapping edit than a closed shop.
- `tests/test_sql_places.py` — 25 tests, each one teeth-checked by breaking
  the behaviour it protects.

Measured against 428 real places around Tata Memorial: **13 ms**, where
Overpass was taking thirty to forty seconds. A pharmacy 941 m away with its
real Dadar address now renders on the Tamil phone.

Three things worth knowing if you touch it:

1. **It reads `records_url`, not `database_url`.** They are two different
   SQLite files. The first version used `db.session.get_sessionmaker()` and
   wrote to the app database — a full table and an empty screen, with nothing
   to say why. The adapter follows `adapters/spends/sql.py`: take a URL, own a
   synchronous engine, run the one query in a thread.
2. **The bounding box scales longitude by `cos(latitude)`.** A degree of
   longitude is about 5% shorter at Mumbai than at the equator, and a box that
   forgets it silently misses places at the edge of the radius. The exact
   radius is then applied in Python, because a box drawn round a 3 km circle
   reaches 4.2 km at its corners.
3. **`open_now` is always `None` from this adapter.** It means "open at the
   instant the service was asked", and this table was written weeks ago.
   `Place.open_at(when)` answers from the stored hours instead, parsed by
   `osm.parse_opening_hours` — the same function the live reader uses, because
   two parsers for one format drift and the day they disagree a family is told
   a shop is open when it is closed.

**Your Jan Aushadhi matcher was missing about a third of them.** `jan\s?aushadhi`
allows one space; real entries carry "Jan  Aushadhi" with two, "JanAushadhi"
with none, and both spellings of the last syllable. Now `jan\s*aushadh?i`.
Each miss was a government generic-medicine shop a family was never offered,
which is exactly the kind they should be offered first.

## What a real device still has to prove

The emulator was used, and it genuinely proved these: all four tabs render in
Tamil, "Near you" returns real places at real distances from the live API,
Spends shows the honest "cannot say yet" rather than a fabricated figure, the
language switcher works, and the app builds and installs clean.

It cannot prove the following, and nobody should claim it has:

| Needs a handset | Why the emulator cannot |
|---|---|
| `google.navigation:` hand-off | The emulator's Maps app crashes on launch |
| Location permission flow and the GPS fix | No real fix; the mock provider does not exercise the prompt |
| Dial (`tel:`) from a place card | No dialler |
| Map tiles under a moving position | Emulator network is too slow to judge |
| Kharcha "add a spend" and Book/pay end to end | Never tapped through on hardware (your §6.4) |

`./demo/phone-tour.sh` drives the four tabs and records them, so a device pass
is: plug in a phone, `adb install -r`, run the tour, then do the five rows
above by hand.

## Still open from your list

§6.2 (Google) is still blocked on the billing upgrade — unchanged, and the
local table means it is no longer on the demo's critical path. §6.3 map
polish, §6.5 ABDM and §6.6 curation are untouched. The family **web** app
still lacks the route planner, Near you and the map; that was a deliberate
call, since the phone is the family's surface and a second copy of three
screens is a second place for every future change to be made twice.

One housekeeping note: `ruff check backend` reports 39 long-line errors in
`adapters/routes/demo.py`, `adapters/places/osm.py`, `orchestrator/trip_options.py`,
`api/trip.py` and `api/nearby.py`. They pre-date this work and were left alone
rather than reformatted underneath you.
