#!/usr/bin/env python3
"""Seed the Paperless AOT database.

Imports the four real sample messages in samples/ plus the demo set in
samples/demo/, so the dashboard, match table and raw-data explorer have every
match status to show:

  217-08722685  MATCHED                 (real FWB + FHL + FFM + FSU samples)
  217-08722686  PARTIAL_MATCH           (2 houses, pieces & weight short)
  217-08722687  WAITING_FOR_FHL         (FWB only)
  217-08722688  WAITING_FOR_FWB         (FHL only)
  217-08722689  MATCHED_WITH_TOLERANCE  (weight off by 0.2 KG)
  217-08722690  MATCHED, 2 houses for one consignee -> combinable into one DO
  invalid_message.txt                   INVALID_FORMAT

Usage: python3 scripts/seed.py [--reset]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.database import db, db_path, init_db  # noqa: E402
from app.services import import_service as svc  # noqa: E402
from app.services.auth import DEFAULT_USERS, ensure_default_users  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
DEMO = os.path.join(SAMPLES, "demo")

# Order matters for the demo: the master arrives before its houses so the
# history shows a real WAITING_FOR_FHL -> MATCHED transition.
REAL_FILES = ["FWB_21708722685.txt", "FHL_WM26070003.txt",
              "FFM_TG601_16JUL26.txt", "FSU_21708722685.txt"]
DEMO_FILES = ["FWB_21708722686.txt", "FHL_EF26070010.txt", "FHL_EF26070011.txt",
              "FWB_21708722687.txt", "FHL_PL26070020.txt",
              "FWB_21708722689.txt", "FHL_GS26070030.txt",
              # one consignee with two houses — the case a combined DO exists for
              "FWB_21708722690.txt", "FHL_UC26070040.txt",
              "FHL_UC26070041.txt", "FSU_21708722690.txt",
              "invalid_message.txt"]


def load_payloads() -> list[tuple[str, str]]:
    payloads = []
    for name in REAL_FILES:
        with open(os.path.join(SAMPLES, name)) as f:
            payloads.append((name, f.read()))
    for name in DEMO_FILES:
        with open(os.path.join(DEMO, name)) as f:
            payloads.append((name, f.read()))
    return payloads


def main() -> None:
    if "--reset" in sys.argv and os.path.exists(db_path()):
        os.remove(db_path())
        print(f"removed {db_path()}")
    init_db()

    payloads = load_payloads()

    with db() as conn:
        ensure_default_users(conn)
        batch = svc.create_batch(conn, "WEB_UPLOAD", user="seed")
        ok = fail = 0
        for name, raw in payloads:
            r = svc.import_message(conn, raw, name, batch["id"], user="seed")
            state = "ok " if r["status"] in ("PARSED", "DUPLICATE") else "FAIL"
            if state == "ok ":
                ok += 1
            else:
                fail += 1
            print(f"  {state} {name:28} {r['messageType'] or '-':4} "
                  f"{r['status']:15} {','.join(r['mawbNumbers'])}")
        conn.execute(
            """UPDATE import_batches SET total_files=?, success_files=?,
               failed_files=?, status='COMPLETED', updated_at=? WHERE id=?""",
            (len(payloads), ok, fail, svc.now(), batch["id"]))

        print(f"\nBatch {batch['batch_no']}: {ok} imported, {fail} rejected\n")
        print(f"{'MAWB':<16}{'STATUS':<24}{'SCORE':>6}{'FHL':>5}"
              f"{'PCS(F/H)':>12}{'WEIGHT(F/H)':>18}")
        for r in conn.execute(
                "SELECT * FROM matching_results ORDER BY mawb_number"):
            print(f"{r['mawb_number']:<16}{r['match_status']:<24}"
                  f"{r['match_score']:>6}{r['fhl_count']:>5}"
                  f"{str(r['fwb_pieces'] or '-') + '/' + str(r['fhl_total_pieces'] or '-'):>12}"
                  f"{str(r['fwb_weight'] or '-') + '/' + str(r['fhl_total_weight'] or '-'):>18}")

    print(f"\nDatabase: {os.path.abspath(db_path())}")
    print("\nบัญชีเริ่มต้น (เปลี่ยนรหัสผ่านก่อนใช้งานจริง):")
    for username, password, role, _display in DEFAULT_USERS:
        print(f"  {username:<10} / {password:<12} {role}")


if __name__ == "__main__":
    main()
