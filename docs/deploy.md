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
- **A family:** enter the phone number you gave as `SAATHI_SEED_DEMO_PHONE`. There is no SMS
  provider, so by default the one-time code is only written to the API service's **Logs** tab on
  Render, as `one-time code for ***NNNN: 123456`.
  To sign in without reading a log, add `SAATHI_DEMO_OTP` on the API service with six digits of your
  choosing (for example `246810`) and redeploy. That phone, and only that phone, then accepts
  that code. Every other family number still gets a random code. This is a demonstration
  arrangement; a real pilot needs an SMS provider and should leave `SAATHI_DEMO_OTP` unset.

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
