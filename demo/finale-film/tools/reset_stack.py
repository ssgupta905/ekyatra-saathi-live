"""Put the deployed stack back to its seed state between film takes.

Deletes only what a take adds — never seed data, never the ledger:

  OpenEMR   leave entries ("oncology leave") and Saathi write-backs
            ("Rescheduled by Saathi…"); the 9 seed appointments stay.
  Saathi    family messages, approvals and option sets for the EKY families
            written since --since, and every stay quote/deal/booking.
  Steps     the EKY families' step dates go back onto the seed appointments,
            through the records API so the running server agrees.
  Memory    POST /live/control {"action": "clear"}.

Then restart the API (a push to the branch redeploys it): sent messages live
in the server's memory and only a restart drops them.

    set -a; source .env; set +a
    .venv/bin/python -I demo/finale-film/tools/reset_stack.py --since "2026-11-27 15:24:00+00"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request

API = os.environ.get("SAATHI_API_URL", "https://ekyatra-saathi-ueoa.onrender.com") + "/api"

#: Where each EKY step sits on a clean stack: on the earliest seed appointment
#: the hospital holds for it (see bootstrap/bahmni_seed._realign), or the seed
#: offset from demo/openemr/seed_stories.py. Dates are the seed of 27 Nov 2026.
SEED_STEPS = {
    "EKY-KAMLA-scan": "2026-11-29",
    "EKY-SHANTI-scan": "2026-11-29",
    "EKY-RAMESH-dialysis_session": "2026-11-27",
    "EKY-JOSEPHINE-review_consult-4d1dd2": "2026-11-29",
    "EKY-PRIYA-review_consult-d961a4": "2026-12-09",
}


def openemr() -> None:
    env = dict(os.environ, CLOUDSDK_PYTHON="/opt/homebrew/bin/python3.11",
               CLOUDSDK_CONFIG=os.path.expanduser("~/.config/gcloud-saathi"))
    sql = ("DELETE FROM openemr_postcalendar_events WHERE pc_hometext LIKE '%oncology leave%' "
           "OR pc_hometext LIKE 'Rescheduled by Saathi%'; SELECT ROW_COUNT();")
    cmd = ["gcloud", "compute", "ssh", "saathi-hms", "--zone", "asia-south1-c", "--quiet", "--command",
           f'sudo docker exec -i openemr-mysql-1 mariadb -uroot -proot openemr -N -B -e "{sql}"']
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True).stdout.strip()
    print("openemr rows deleted:", out.splitlines()[-1] if out else "?")


def records(since: str) -> None:
    import sqlalchemy as sa

    engine = sa.create_engine(os.environ["SAATHI_RECORDS_URL"])
    with engine.begin() as c:
        for label, sql in (
            ("family_messages", "delete from family_messages where patient_id like 'EKY-%' and sent_at >= :t"),
            ("approvals", "delete from approvals where patient_id like 'EKY-%' and approved_at >= :t"),
            ("option_sets", "delete from option_sets where patient_id like 'EKY-%'"),
            ("stay spends", "delete from spend_entries where source_ref like 'stay-%'"),
        ):
            print(f"{label}:", c.execute(sa.text(sql), {"t": since}).rowcount)


def call(method: str, path: str, body: dict) -> int:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method=method,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.status


def steps_and_memory() -> None:
    for step, day in SEED_STEPS.items():
        print(step, "->", day, call("PATCH", f"/steps/{step}", {"scheduled_for": day}))
    print("clear:", call("POST", "/live/control", {"action": "clear"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True, help="UTC time the take started, e.g. '2026-11-27 15:24:00+00'")
    args = p.parse_args()
    openemr()
    records(args.since)
    steps_and_memory()
    print("now restart the API (push to the branch, or restart the Render service)")
