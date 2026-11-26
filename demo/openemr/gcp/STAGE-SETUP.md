# Stage data setup against OpenEMR on the Google Cloud VM

What was done (26 Nov 2026) so the stage script can run with OpenEMR on the VM instead of local Docker.
Nothing here is in git except this file and `stage_arrivals.py`'s remote option; `demo.env` and the
signing key are git-ignored.

## One-time (already done)

1. `gcloud` signed in to project `project-44d0b1f7-f267-47b5-9b2` in an isolated profile
   (`CLOUDSDK_CONFIG=~/.config/gcloud-saathi`); the VM is `saathi-hms`, zone `asia-south1-c`.
2. On the VM, in OpenEMR's database (the three things OpenEMR does not allow over HTTP):
   ```sql
   UPDATE globals SET gl_value='1' WHERE gl_name IN ('rest_api','rest_fhir_api','rest_system_scopes_api');
   UPDATE globals SET gl_value='http://<VM IP>:8300' WHERE gl_name='site_addr_oath';
   UPDATE users SET npi='1234567893' WHERE username='admin';
   ```
3. `python -m saathi.bootstrap.openemr_seed --register --base-url http://<VM IP>:8300 --key demo/openemr/openemr-key.pem`
   then `UPDATE oauth_clients SET is_enabled=1, client_role='system' WHERE client_name='Saathi Connector';`
4. The first token request fails with "SystemUser was missing" (OpenEMR creates the system user's UUID on
   that first failed call); the second succeeds. Just retry.
5. `openemr_seed --write --local` (4 families, 5 appointments, 1 pending lab order) into OpenEMR and into our
   stage records database (`demo/openemr/stage.db`).
6. Languages set through `PATCH /api/patients/{id}/language`: EKY-SHANTI `bn`, EKY-RAMESH `ta` (the seeder writes
   everyone as Hindi).

## Every time

```bash
export CLOUDSDK_CONFIG=$HOME/.config/gcloud-saathi PATH=/opt/homebrew/share/google-cloud-sdk/bin:$PATH

# 1. the VM's firewall admits one IP: update it to the venue's first
gcloud compute firewall-rules update saathi-hms-ports --source-ranges "$(curl -s https://api.ipify.org)/32"

# 2. a tunnel so the arrival clock can read OpenEMR's MariaDB (SELECT-only account) on 127.0.0.1:3307
gcloud compute ssh saathi-hms --zone asia-south1-c --quiet -- -N -L 3307:127.0.0.1:3307 &

# 3. the stage API (needs GROQ_API_KEY in .env or the language layer is off)
set -a; [ -f .env ] && source .env; source demo/openemr/demo.env; set +a
.venv/bin/uvicorn saathi.main:app --app-dir backend --host 127.0.0.1 --port 8077

# 4. on the demo MORNING (it stages today's appointments; run it again if the laptop slept)
set -a; source demo/openemr/demo.env; set +a; make stage-arrivals

# the leftover-leave cleanup from the stage script, run on the VM
gcloud compute ssh saathi-hms --zone asia-south1-c --quiet --command \
  "sudo docker exec -i openemr-mysql-1 mariadb -uroot -proot openemr -N -B -e \"DELETE FROM openemr_postcalendar_events WHERE pc_hometext LIKE '%oncology leave%';\""
```

## Still needs a person

- `GROQ_API_KEY` in `.env` (the stage script's "actors/language true" check).
- Save the hospital's rules once on the Console's Configuration screen (`used_by_planner` must be true).
- OpenEMR's admin password is generated on the VM: `sudo cat /root/openemr-admin-password.txt`.
