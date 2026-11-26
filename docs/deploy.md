# Deploying Ekyatra Saathi: Render + Supabase + Android

Three pieces: a Postgres database on Supabase, the API and two web apps on Render, and an
Android APK that points at the API. Do them in this order, because each needs an address from
the one before.

You will handle two secrets yourself (the database password and the admin password). Neither
needs to be sent to anyone: they go straight into Render's dashboard.

## 1. Supabase: the database

1. New project, named `Ekyatri-saathi`. Pick a region and note it: the Render service in `render.yaml` should be in the nearest Render
   region (Frankfurt for Supabase's eu-west-1, Singapore for ap-southeast-1). Set a database password and keep it.
2. Open **Connect** and copy the **Session pooler** connection string. It looks like
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`.
3. Put your real password in place of `[YOUR-PASSWORD]`. If it contains `@ : / ? # %`, encode
   those characters (`@` is `%40`, `#` is `%23`) or the URL will not parse. The simplest fix is a
   password made only of letters and digits.

Why the **session pooler**: Render's free tier reaches IPv4 only, and Supabase's direct host
(`db.<ref>.supabase.co`) is IPv6 only. Use port 5432 (session mode). Port 6543 (transaction
mode) breaks the database driver's prepared statements.

The app creates its own tables on first start. Nothing to run in the Supabase SQL editor.

## 2. Render: the API

1. In Render: **New > Blueprint**, connect the GitHub repository, choose the branch to deploy.
   Render reads `render.yaml` and proposes three services.
2. Fill in the prompts for the API service (`ekyatra-saathi`):

   | Variable | What to put |
   |---|---|
   | `SAATHI_RECORDS_URL` | the session pooler string from step 1, password included |
   | `SAATHI_ADMIN_USERNAME` | the staff login you want, for example `admin` |
   | `SAATHI_ADMIN_PASSWORD` | a password of at least 8 characters |
   | `SAATHI_SEED_DEMO_PHONE` | your own phone number, for example `+919812345678` |
   | `SAATHI_CORS_ORIGINS` | leave empty for now; set in step 4 |
   | `GROQ_API_KEY` | optional; without it messages use templates |

   `SAATHI_AUTH_SECRET` is generated for you.
3. Deploy. When it is live, open `https://<your-api>.onrender.com/api/health`. You should see
   `"status":"ok"` and `"patients":12`.

The first start seeds 12 synthetic families into the empty database. It never seeds a database
that already holds a family, so a restart is safe.

It also adds a showcase of nine more families (prefix `SHOW-`) and three hospital resources, so
every screen has something to show: families on the dialysis and post-discharge pathways, a ride
that was cancelled, a pharmacy still pending, an insurer that has not answered, and two families
booked on `MRI-2`. The showcase tops up an existing database too, and never adds itself twice.

To see the approval loop, report an outage on `MRI-2` (Report an issue, "MRI-2 down for a week")
and open Approvals. Options that touch treatment timing can only be approved by a doctor, so create
one under Registries > Staff accounts first.

**The free plan sleeps** after 15 minutes without traffic, and the first request after that takes
about a minute. Wake it before a demo by opening the health URL.

That matters more here than it does for most services, and it is worth being plain about why.
The hospital connector is not a cron job or a webhook — it is an in-process loop
(`live/runner.py`, `while True: await sync.poll_once()`). A sleeping instance is not polling, so
the claim the whole demo rests on — *a doctor marks themselves away and seconds later the family
has been asked, with nobody touching anything* — is exactly what sleeping breaks. For an
unattended link, pay for an instance that does not sleep. A keep-alive pinger papers over it and
still leaves you a cold start on the day.

**One worker, deliberately.** The world, the clock and the ledger are in-process state, so a
second worker would serve a second, divergent reality. Scale this up, never out.

## 2a. What can and cannot live on Render

Render offers managed **Postgres** and Key Value. That one fact decides most of this.

| Piece | On Render? | Notes |
|---|---|---|
| The API | Yes, free | Docker, on the Supabase Postgres. |
| Console, family and partner apps | Yes, free | Three static sites. |
| HAPI FHIR, as the hospital system | **No** | Tried on a free instance with a capped heap and a Supabase schema; Render killed it for using over 512 MB. Runs on the Google Cloud VM instead (§2b). |
| **OpenEMR** | No | Needs MariaDB (Render's managed databases are Postgres only), disks and 1-2 GB. Runs on the Google Cloud VM instead (§2b). |
| **OpenEMR's arrival clock** | Not from Render | Read from OpenEMR's MariaDB, SELECT-only (`adapters/hospital/openemr_db.py`). The VM keeps that database closed to the internet, so a hosted API cannot reach it; without it the Console says a family arrived and claims no delay, which is the honest degradation. |
| Bahmni / OpenMRS | No | Same reason as OpenEMR: it needs MariaDB. |
| The Android app | n/a | It is an APK. Rebuild it pointing at the Render API and install it. |
| The film rig | n/a | `scrcpy`, `adb` and `ffmpeg` capture a local screen and an attached phone. |

**Two hospital systems, and neither is on Render.** HAPI proves the connector reads any conformant
FHIR server; OpenEMR is the one with its own clinical UI, the system a judge can be handed and
invited to click anything in. Both need more memory and disk than Render's free tier gives (HAPI
was tried there and was killed at 512 MB), so both run on a Google Cloud VM — §2b. Both are read through the same port, which is what
"plugs into any HMS" has to mean to be worth saying.

**Do not port OpenEMR to Postgres.** It is asked often enough to be worth answering with numbers
from the running instance: 293 tables and 3,932 columns, of which 178 are `AUTO_INCREMENT`, 267
are `tinyint`, 14 are `enum` and 33 carry `ON UPDATE CURRENT_TIMESTAMP` — none of which Postgres
has. In the PHP there are 391 files with backtick-quoted SQL (a syntax error in Postgres), 103
using `DATE_FORMAT`, 40 using `IFNULL`, 36 using `INSERT … ON DUPLICATE KEY UPDATE`, across
54,554 files, and the data layer pins its driver outright (`$ADODB_LASTDB = 'mysqli_log'`). That
is a fork of a twenty-year-old application, not a configuration change.

And it would cost the thing the architecture is actually for. The claim this project defends is
*OpenEMR runs unmodified; we read standard APIs and write back through them*. A forked HMS is a
different, much weaker claim, and a reviewer would be right to say so. **Medplum** (`2d8b95b`,
reverted in `7bb4666`) was tried as the FHIR-native way out of MariaDB — also paid, a 2 GB server
plus its own Postgres, and it is not the system anyone's staff actually use.

Set `SAATHI_HOSPITAL_SYSTEMS` accordingly, or the service runs with no HMS connector at all —
everything works and nothing watches a hospital, which is a quiet way to lose half the demo:

```
TMH-MUM=fhir|http://<the VM address>:8080/fhir
```

Two things a fresh deployment needs that are easy to forget, because both fail by being empty
rather than by erroring:

- **Places.** "Near you" reads our own table, not a live Overpass query. Run
  `make load-places FILE=<export>.geojson` against the deployed database or the panel is blank.
- **Hospital rules.** The option search needs a hospital's stated shift tolerance. Check
  `/api/admin/policy/<hospital>` says `"used_by_planner": true`; until it does, the planner
  refuses to offer dates rather than inventing a tolerance, and the screen looks broken when it
  is in fact being careful.

And note that the free API sleeps. A demo that wakes the API but not the hospital VM (or the other
way round) gets a connector reading a hospital that is not there.

## 2b. The hospital systems on Google Cloud

OpenEMR (with MariaDB) and the HAPI FHIR server run on one Compute Engine VM, from the stock
images and nothing of ours inside them. The script and the exact commands are in
`demo/openemr/gcp/` (`startup.sh`, `README.md`). In short: one VM in Mumbai (`asia-south1`), a
firewall rule that lets only your own IP reach OpenEMR (port 8300) and HAPI (port 8080), the
database kept closed to the internet, and a random admin password generated on the VM (read it
over SSH: `sudo cat /root/openemr-admin-password.txt`).

It runs on the Google Cloud free-trial credit, so it is free while the trial lasts; stop or delete
the VM before the credit ends. Render's free instance cannot host these (see §2a), and the paid
Render route was tried and dropped in favour of this.

Because the firewall admits only your IP, the hosted API (on Render) cannot reach the VM. Opening
that deliberately — HTTPS in front, strong passwords, an allow-list for the API's addresses — is a
separate piece of work; do not simply open the ports to the world with the demo defaults.

**Then three one-time steps, in this order.** None can be expressed in the blueprint.

1. **The read-only account.** The arrival clock reads MariaDB directly, and must do so with an
   account that can only read. `demo/openemr/readonly-user.sql` creates `saathi_ro` for the
   laptop; run the same two statements against the hosted database **with a different password**,
   from an SSH session on the VM (`sudo docker exec -it openemr-mysql-1 mariadb -uroot -p`):

   ```sql
   CREATE USER IF NOT EXISTS 'saathi_ro'@'%' IDENTIFIED BY '<a new password>';
   GRANT SELECT ON openemr.* TO 'saathi_ro'@'%';
   ```

   The connector's read-only claim rests on three independent things — every query in
   `openemr_db.py` is a SELECT and a test fails otherwise, the session is opened `SET SESSION
   TRANSACTION READ ONLY`, and this grant means even a bug could not write. The laptop password is
   in a committed file; do not reuse it on anything reachable.

2. **Register the SMART client**, against the deployed address rather than localhost:

   ```bash
   SAATHI_OPENEMR_BASE_URL=http://<the VM's address>:8300 \
     .venv/bin/python -m saathi.bootstrap.openemr_seed --register
   ```

   This prints a client id, a key id and a PEM. OpenEMR also needs its API and its
   `system/*` scopes enabled once in Administration → Config; `docs/openemr.md` has the list.

3. **Put the PEM in a Render Secret File** (on the API service), not an environment variable:
   filename `openemr.pem`, which Render mounts at `/etc/secrets/openemr.pem`. The code reads the
   key from a path on purpose — a private key pasted into a deployment variable ends up in logs,
   dashboards and shoulder-surfing range — and a secret file is exactly that path without the
   exposure.

Then set `SAATHI_HOSPITAL_SYSTEMS` on the API service. One line, six fields after the kind, and
the last three are what turn the arrival clock on:

```
TMH-MUM=openemr|http://<the VM's address>:8300|<client id>|<key id>|/etc/secrets/openemr.pem|<db host>:3307/openemr|saathi_ro|<the password from step 1>
```

The database is closed to the internet on the VM, so the hosted API cannot read it and the last
three fields do not apply there. Drop them and everything still works except the derived delay.

To read both hospitals at once, comma-separate the entries — one `openemr` line and one `fhir`
line pointing at HAPI.

## 3. Render: the two web apps

For `ekyatra-saathi-control-centre` and `ekyatra-saathi-family`, set `SAATHI_API_BASE` to
`https://<your-api>.onrender.com/api` (the API address plus `/api`), then deploy.

## 4. Allow the web apps to call the API

Back on the API service, set `SAATHI_CORS_ORIGINS` to the two static-site addresses, separated
by a comma, with no trailing slash and no spaces:

```
https://ekyatra-saathi-control-centre.onrender.com,https://ekyatra-saathi-family.onrender.com
```

Save, and Render redeploys. The Android app is not affected by this setting.

## 5. Signing in

- **Staff:** the control centre, with the admin username and password from step 2.
- **A family:** enter the email address you gave as `SAATHI_SEED_DEMO_EMAIL` (or the phone number
  from `SAATHI_SEED_DEMO_PHONE`), and a six-digit code is sent to it. Families can sign in by
  email or by phone; any family with an email on record can use it.

  **Email codes through Brevo (free, 300 a day).** Render's free tier blocks SMTP, so Gmail
  cannot be used directly. Brevo is called over HTTPS instead:
  1. Make a free account at brevo.com.
  2. Add your Gmail address as a sender (Senders, Domains & Dedicated IPs > Senders) and confirm the
     email Brevo sends you.
  3. Create an API key (SMTP & API > API Keys).
  4. On the API service in Render, set `SAATHI_BREVO_API_KEY` to that key,
     `SAATHI_EMAIL_FROM` to the verified sender address, and `SAATHI_SEED_DEMO_EMAIL` to the
     address that should receive the code. Redeploy.

  Check spam the first time: mail from a new sender often lands there.

  **Without Brevo,** the code is written to the API service's **Logs** tab on Render, as
  `one-time code for j***@gmail.com: 123456`.

  **Fixed demo code.** To sign in without any email at all, set `SAATHI_DEMO_OTP` to six digits (for
  example `246810`). The demo email and the demo phone, and only those, then accept that code.
  This is a demonstration arrangement; a real pilot should leave it unset.

## 6. The Android APK

The API address is fixed into the app when it is built, so build it once the API is live.

Needs JDK 17 and the Android SDK (Android Studio installs both). From `android/`:

```bash
JAVA_HOME=$(/usr/libexec/java_home -v 17) ./gradlew assembleDebug -PapiBase=https://<your-api>.onrender.com/api
```

(`JAVA_HOME=...` picks JDK 17 on a Mac that also has newer ones. Skip it if 17 is your default.)

The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`. Copy it to a phone and
install it (allow installs from your file manager when asked). It is a debug build, signed with
the debug key, which is fine for a demonstration and not for the Play Store.

Rebuild and reinstall if the API address ever changes.

## Troubleshooting

| Symptom | Cause |
|---|---|
| API deploy fails at start with a connection error | wrong password, an unencoded special character, or the direct host used instead of the session pooler |
| `"patients":0` on health | seeding is off, or the database already held data |
| Control centre loads but every call fails | `SAATHI_API_BASE` missing `/api`, or `SAATHI_CORS_ORIGINS` not set to the site's address |
| First request takes a minute | the free instance was asleep |
| App says it cannot reach the server | the APK was built with the wrong `apiBase`; rebuild |
