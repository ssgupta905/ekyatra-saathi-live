# The hospital systems on Google Cloud

One Compute Engine VM runs both hospital systems from stock images (nothing of ours inside):

| System | Port | Notes |
|---|---|---|
| **OpenEMR** (with MariaDB) | 8300 | Has its own clinical UI. Login `admin`; the password is generated on the VM. |
| **HAPI FHIR** (with Postgres) | 8080 | FHIR API at `/fhir`, and HAPI's built-in test page at `/`. |

Both databases are closed to the internet. This replaces trying to host them on Render, where HAPI
was killed at 512 MB and OpenEMR needs paid instances and disks.

## Create it (Cloud Shell, or the console's Create instance form with the same settings)

```bash
PROJECT=project-44d0b1f7-f267-47b5-9b2
MYIP=$(curl -s https://api.ipify.org)           # the only address allowed in

gcloud services enable compute.googleapis.com --project $PROJECT

gcloud compute instances create saathi-hms \
  --project $PROJECT --zone asia-south1-a \
  --machine-type e2-standard-2 --boot-disk-size 40GB \
  --image-family debian-12 --image-project debian-cloud \
  --tags saathi-hms \
  --metadata-from-file startup-script=startup.sh

gcloud compute firewall-rules create saathi-hms-ports \
  --project $PROJECT --allow tcp:8300,tcp:8080 \
  --target-tags saathi-hms --source-ranges "$MYIP/32"
```

`e2-standard-2` (2 vCPU, 8 GB) because OpenEMR + MariaDB + HAPI + Postgres together need about
3 GB. It runs on the free-trial credit.

First boot takes 5-8 minutes (Docker install, image pulls, OpenEMR builds its schema, HAPI builds
its tables). Then open `http://<VM external IP>:8300` (OpenEMR) and `http://<VM external IP>:8080`
(HAPI), from the allowed address.

## Passwords

Nothing is typed or stored in the repo. The VM generates them on first boot:

```bash
# over SSH (the SSH button in the console)
sudo cat /root/openemr-admin-password.txt     # OpenEMR admin
sudo cat /root/hapi-db-password.txt           # HAPI's own database, not needed to use HAPI
```

## Things to know

- The firewall rule allows **only your current public IP**. If it changes, update it:
  `gcloud compute firewall-rules update saathi-hms-ports --source-ranges "<new ip>/32"`.
- Plain HTTP. Fine for a locked-down demo; put HTTPS in front before opening it up.
- The hosted API (on Render) cannot reach an IP-locked VM, so for now the VM is for the real
  OpenEMR/HAPI screens and for the local API. Wiring the hosted API to it means opening access
  deliberately (HTTPS, strong passwords, an allow-list). Do not open these ports to the world.
- MariaDB's root and the read-only user's passwords in `startup.sh` are demo defaults. The
  database is not reachable from outside the VM, but change them before anything real is loaded.
- Cost: runs on the trial credit; stop the VM when not in use
  (`gcloud compute instances stop saathi-hms --zone asia-south1-a`) and delete it before the credit
  ends.
