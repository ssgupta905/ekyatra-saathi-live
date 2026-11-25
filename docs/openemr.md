# Talking to OpenEMR

Everything below was established against a running OpenEMR 8.6, by trying it.
None of it is in the FHIR spec, and most of it is not in OpenEMR's docs either.

## Why OpenEMR

It is the only HMS we evaluated whose **actual UI can appear in the demo**,
because it is ours on localhost rather than someone else's hosted box. It also
does what Bahmni could not: approval `Task` resources that actually write
(Bahmni 500s on every `POST /Task`), and `ServiceRequest`/`Observation` for the
lab beat.

The trade is name-recognition. Bahmni is the HMS an Indian hospital judge
knows. Say that out loud rather than hoping nobody asks.

## The thing that had to be true

A judge cancels an appointment in OpenEMR's own calendar. The calendar writes
`pc_apptstatus = 'x'` to `openemr_postcalendar_events` — it does not go near
FHIR. The question was whether our connector, which reads FHIR, would see it.

It does. Verified:

    FHIR status before:  booked
    UPDATE openemr_postcalendar_events SET pc_apptstatus='x'
    FHIR status after:   cancelled

FHIR is a live projection of the same tables the UI writes, so anything a
person does in the UI is visible to the connector on the next poll. This is the
single fact the whole demo rests on.

## One-time instance setup

The API is **off by default** and a registered client is **disabled by
default**. Both are silent: you get `API is disabled` and then
`invalid_client`, neither of which says what to turn on.

    UPDATE globals SET gl_value='1'
      WHERE gl_name IN ('rest_api','rest_fhir_api','rest_system_scopes_api');
    UPDATE globals SET gl_value='http://localhost:8300' WHERE gl_name='site_addr_oath';
    -- after registering a client:
    UPDATE oauth_clients SET is_enabled=1, client_role='system';

## Auth: SMART Backend Services

`client_credentials` requires `private_key_jwt` — a client secret is refused
with `jwks is invalid`. The flow:

1. Generate an RSA keypair.
2. `POST /oauth2/default/registration` with an inline `jwks`, a
   `redirect_uris` array (**required even for client_credentials**, otherwise
   `redirect_uris is invalid`), and every scope you will ever ask for. Scopes
   are fixed at registration: asking for `system/Patient.write` later when you
   registered only `.read` fails as a bare `401 Unauthorized`.
3. Enable the client (above).
4. Sign an `RS384` assertion (`iss`/`sub` = client_id, `aud` = the token URL)
   and exchange it.

**Tokens last 300 seconds.** A connector polling for minutes needs a provider
that re-mints, not a token fetched once at startup.

## Writing resources

Every one of these was a 400 before it was a 201.

**Patient** — `name[].use` must be `"official"`. Without it the validator
reports `fname`/`lname` empty, having not read the name at all.

**Patient identifiers are not yours.** We send `EKY-KAMLA`; OpenEMR stores its
own auto-assigned PID (`"1"`) and discards ours. `HospitalLinks.patient_for`
matches families on identifier, so the seed must record OpenEMR's id rather
than assume ours survives.

**Appointment** needs all of:
- a `Patient` participant that resolves, and
- a `Location` participant whose UUID is a row in the **`facility`** table.
  The FHIR `Location` search also returns patient home addresses, and those
  resolve to nothing. Get the real one from
  `SELECT id, name, HEX(uuid) FROM facility`.
- a `comment` — maps to `pc_hometext`, which is `NotEmpty`. `description`
  does not satisfy it.

`Appointment` supports `create` but **not `update`**. Cancelling through FHIR
is not possible; cancelling through the UI is, which is what the demo needs
anyway.

## Search parameters

`Appointment` supports exactly `patient, _id, date, _lastUpdated`. There is
**no `_include`**, so the trick our HAPI adapter uses — pulling the patient
into the same bundle to get the identifier — does not work here. Resolve
`Patient/{id}` separately and cache it.

## Local instance

    cd /tmp/hms-eval && docker compose -f openemr-min.yml up -d
    # UI:   http://localhost:8300   admin / pass
    # FHIR: http://localhost:8300/apis/default/fhir

## Driving the calendar UI

Every one of these was found by failing at it first.

**The appointment must have a provider.** `pc_aid` is NULL after a FHIR
create, and the calendar lays appointments out in per-provider columns — so a
provider-less appointment is in the database, readable over FHIR, and
**invisible on the calendar**. Include a `Practitioner` participant, or the
demo has nothing to click.

**Date navigation does not respond to URL parameters.** Neither
`?year=&month=&day=` on the calendar frame nor a direct
`interface/main/calendar/index.php?...&Date=` works; the frame reloads on
today regardless. Rather than fight it, put the appointment on *today* — the
calendar opens there, and a slot being cancelled today is a perfectly natural
demo anyway.

**The page is frames.** After login the calendar is a child frame:

    const cal = page.frames().find(f => f.url().includes("calendar/index.php"));

**Dismiss the registration modal first**, with "Ask again later" — not
"Submit", which opts the installation into telemetry.

**The appointment block is `div.event_appointment[data-eid]`, and it opens on
double click**, not click. Clicking the patient name inside it opens the
patient chart instead, which looks like the right thing happening and is not.

**A confirm dialog blocks the save.** "Provider not available, use it anyway?"
Without a handler the save silently never happens — the editor stays open, the
database is unchanged, and nothing reports an error:

    page.on("dialog", async d => { await d.accept(); });

Full flow, verified:

    log in → "Ask again later" → dblclick div.event_appointment
    → select[name=form_apptstatus] = 'x' → click #form_save → accept dialog

    FHIR status after: cancelled

## Patient identifiers: they can be ours after all

A first attempt sent `identifier: [{system: "https://ekyatra.org/id", value:
"EKY-KAMLA"}]` and OpenEMR stored its own auto-assigned PID instead, silently.
The identifier FHIR reports is OpenEMR's **External ID** (`patient_data.pubpid`),
and it is only written when the identifier carries the v2-0203 `PT` type coding:

    "identifier": [{
      "use": "official",
      "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                           "code": "PT"}]},
      "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
      "value": "EKY-KAMLA"
    }]

With that shape the seeder is pure FHIR and needs no database access, and the
Bahmni contract survives unchanged: **the identifier the hospital holds is the
patient id here**, which is what `HospitalLinks.patient_for` matches on.

## Reading provider leave

There is no `Schedule` and no `Slot`. Both routes return a hard
`404 {"message":"Route not found"}` — not in the capability statement, no service
class in `src/Services/FHIR/`. So "when is this doctor free" has to be computed
from events, and leave has to be read from the appointment stream.

A leave is an ordinary row in `openemr_postcalendar_events` with `pc_pid` NULL.
What distinguishes it is `openemr_postcalendar_categories.pc_cattype`: `0` is a
patient appointment, `1` a provider event, `2` facility-wide. Match on
`pc_constant_id` — `out_of_office`, `vacation`, `holidays`, `closed` — and never
on `pc_catid`, which is auto-increment and differs per installation.

It does come back from `GET /Appointment`: `AppointmentService::search()`
left-joins `patient_data` with no `IS NOT NULL` filter, so a patient-less event
is returned, and `FhirAppointmentService::parseOpenEMRRecord` emits the category
as `appointmentType.coding[0].code`.

Three traps, all found by entering a Vacation and reading it back:

- **Do not filter on status.** An all-day leave entered through the UI keeps the
  default `pc_apptstatus` of `-`, which maps to `proposed`, not `booked`.
  Filtering on a booked status returns no leave at all — which looks exactly
  like nobody being away.
- **The end date is invisible.** `FhirAppointmentService` reads `pc_endDate`;
  `AppointmentService::search()`'s SELECT list does not include it. A week of
  leave arrives looking like one day. `ProviderAway.end_is_known` is `False`
  against OpenEMR for this reason, and `covers()` answers only for the range it
  was actually given.
- **Leave arrives in `appointments()` too**, and must be filtered out there, or
  it reads as a booked slot with no patient and an unknown status. See
  `_is_provider_event`.

Also: the provider is a `Practitioner` participant **only if `users.npi` is
non-empty**. Otherwise `FhirAppointmentService` degrades it to a `Person`
reference, so matching on a reference prefix alone silently matches nobody for
exactly those providers. Give every seeded provider an NPI.

Recurrence is not expanded: `pc_recurrspec` is never read by the search, so a
recurring "out of office every Tuesday" shows as one occurrence.

## Reading order status: two traps

**`?status=` takes OpenEMR's vocabulary, not FHIR's.** The search parameter is
declared against the raw columns (`order_status`, `order_activity`) with no
reverse mapping. Measured against a live instance:

```
ServiceRequest?status=pending    -> total 1
ServiceRequest?status=active     -> total 0   # but the body reads "status": "active"
ServiceRequest?status=completed  -> total 0
```

Passing the FHIR code a caller would reasonably pass is the quiet failure: a
clean 200 with an empty bundle, which reads as "nothing outstanding". Fetch
unfiltered and map in our own code.

**`_lastUpdated` maps to `date_ordered`.** From
`FhirServiceRequestProcedureOrderService::getLastModifiedSearchField()`. That
column is written once and never touched when the status changes, so a watermark
poller over orders runs forever and never sees a pending report become final.
This is unlike `Appointment`, whose `_lastUpdated` maps to `pc_time`, which
`add_edit_event.php` stamps `NOW()` on every insert and update — which is
precisely why the cancellation beat works on a cursor and this one must not.
Compare snapshots instead: `OrderSnapshot.diff`.

OpenEMR's own definition of pending, from `interface/orders/pending_orders.php`:
no `procedure_report` row, or one whose `report_status` is `prelim`.

Two more limits worth stating rather than discovering on stage:

- `DiagnosticReport.status` is **always** `final`. `ProcedureService` never
  selects `report_status`, so `FhirDiagnosticReportLaboratoryService` falls
  through to `setStatus('final')` whatever the report really says.
- `review_status` — the clinician's signature, written by "Sign Results" — is
  not in FHIR at all.

`DiagnosticReport` also needs `system/DiagnosticReport.read`, which means a new
client registration: scopes are fixed at registration time, and asking for one
the client was not registered with fails as a bare `401` that names nothing.
`Observation` works with the existing scopes and does expose `final` vs `prelim`.

A lab `Observation` **cannot be created over FHIR**:
`FhirObservationLaboratoryService` does not implement `IResourceCreatableService`,
and `POST /fhir/DiagnosticReport` is explicitly `fhirWriteNotImplemented`. Use
the orders UI, which is the better demo anyway — a human signing a result is the
story.

## Reading how late the clinic is running

This is the one thing that is not available over any API, and the reason
`adapters/hospital/openemr_db.py` exists.

`PatientTrackerService::manage_tracker_status()` inserts a new
`patient_tracker_element` row with `start_datetime = NOW()` on every status or
room change — it never updates in place — and it is called from
`interface/main/calendar/add_edit_event.php`, the same editor save that drives
the cancellation beat. So an append-only, timestamped log already exists as a
side effect of ordinary work, and nobody is asked to mark the clinic as late.

FHIR gives the state change and nothing else. `Appointment.status` flips to
`arrived`, and that flip *is* pollable via `pc_time`. But the time of arrival is
not in the resource, and `@ Arrived` and `~ Arrived late` map to the **same**
FHIR status — so over FHIR you cannot even tell that a clerk flagged somebody
late. `Encounter` is a dead end: `FhirEncounterService` hardcodes
`ENCOUNTER_STATUS_FINISHED` and its `period` gets only a `start`.

Which codes mean what is **data, not a guess**: `list_options` carries
`toggle_setting_1` for check-in and `toggle_setting_2` for check-out, and
OpenEMR's own `collect_checkin()`/`collect_checkout()` read them that way. On a
stock instance that gives `@`/`~` as arrival and `>`/`!` as departure, with
`<` (in exam room) carrying neither flag.

Two preconditions, or the tracker produces nothing:

- `manage_tracker_status()` returns early when `pc_recurrtype != 0`, so **a
  recurring appointment gets no tracker row at all.** Seed non-recurring ones.
- A tracker row requires a patient, so provider events never get one.

Configure it by appending to the `openemr` entry:

```
SAATHI_HOSPITAL_SYSTEMS=H1=openemr|http://localhost:8300|<client id>|<key id>|<pem path>|localhost:3306/openemr|<db user>|<db pass>
```

All three database parts are required together; a half-written spec is treated
as a typo and ignored with a warning rather than attached. Needs the `openemr`
extra (`pip install -e '.[openemr]'`) for PyMySQL. Leave it off entirely and the
Console reports that a family arrived and claims no delay — which is the correct
behaviour when nothing can tell it one. A guessed delay is worse than none,
because a family rearranges their day around it.

The connection is opened `SET SESSION TRANSACTION READ ONLY`, every statement in
the module is a `SELECT`, and `tests/test_clinic_flow.py` parses the module and
fails if any SQL string in it is not one. Writes continue to go through the
standard API.
