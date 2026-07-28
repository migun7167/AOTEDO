#!/usr/bin/env python3
"""Seed the Paperless AOT database.

Imports the four real sample messages plus a few synthetic MAWBs so the
dashboard, match table and raw-data explorer have something to show:

  217-08722685  MATCHED               (real FWB + FHL + FFM + FSU samples)
  217-08722686  PARTIAL_MATCH         (2 houses, pieces & weight short)
  217-08722687  WAITING_FOR_FHL       (FWB only)
  217-08722688  WAITING_FOR_FWB       (FHL only)
  217-08722689  MATCHED_WITH_TOLERANCE(weight off by 0.2 KG)
  invalid.txt   INVALID_FORMAT

Usage: python3 scripts/seed.py [--reset]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.database import db, init_db, DB_PATH  # noqa: E402
from app.services import import_service as svc  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")

SYNTHETIC = {
    # --- 217-08722686 : partial match (FWB 10 pcs / 400 KG vs FHL 8 pcs / 320 KG)
    "FWB_21708722686.txt": """FWB/16
217-08722686HKGBKK/T10K400.0
FLT/TG601/16
RTG/BKKTG
SHP
/EASTERN FORWARDING LIMITED
/12 KWAI FUNG CRESCENT
/HONG KONG
/HK
CNE
/SIAM CARGO SERVICE CO LTD
/999 BANGNA TRAD ROAD
/BANGKOK
/TH
AGT//1316077
/NARITA EXPRESS HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P10/K400.0/CQ/W400.0/R9.50/T3800.000
/NG/CONSOL
ISU/16JUL26/HKG
REF/HKGFMCR
SPH/SPX""",
    "FHL_EF26070010.txt": """FHL/4
MBI/217-08722686HKGBKK/T10K400.0
HBS/EF26070010/HKGBKK/5/K200.0//ELECTRONIC PARTS
HTS/85177000
OCI/TH/CNE/T/TAX 0105531040301
SHP/EASTERN SHIPPER ONE LIMITED
/ROOM 1201 KWAI CHUNG PLAZA
/HONG KONG
/HK/999077
CNE/THAI ELECTRONICS CO LTD
/BANGPOO INDUSTRIAL ESTATE
/SAMUTPRAKARN
/TH/10280/TE/6627091234""",
    "FHL_EF26070011.txt": """FHL/4
MBI/217-08722686HKGBKK/T10K400.0
HBS/EF26070011/HKGBKK/3/K120.0//MACHINE PARTS
HTS/84314990
OCI/TH/CNE/T/TAX 0105531040302
SHP/EASTERN SHIPPER TWO LIMITED
/8F TSUEN WAN INDUSTRIAL CENTRE
/HONG KONG
/HK/999077
CNE/SIAM MACHINERY CO LTD
/ROJANA INDUSTRIAL PARK
/AYUTTHAYA
/TH/13210/TE/6635226688""",
    # --- 217-08722687 : FWB only -> WAITING_FOR_FHL
    "FWB_21708722687.txt": """FWB/16
217-08722687HKGBKK/T5K250.0
FLT/TG603/17
RTG/BKKTG
SHP
/PACIFIC AIR CARGO LIMITED
/45 CHEUNG SHA WAN ROAD
/HONG KONG
/HK
CNE
/BANGKOK FREIGHT SOLUTIONS
/88 SILOM ROAD
/BANGKOK
/TH
AGT//1316099
/PACIFIC AGENT HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P5/K250.0/CQ/W250.0/R11.20/T2800.000
/NG/GENERAL CARGO
ISU/17JUL26/HKG
REF/HKGPAC
SPH/SPX""",
    # --- 217-08722688 : FHL only -> WAITING_FOR_FWB
    "FHL_PL26070020.txt": """FHL/4
MBI/217-08722688HKGBKK/T3K120.0
HBS/PL26070020/HKGBKK/3/K120.0//GARMENT
HTS/62034200
OCI/TH/CNE/T/TAX 0105531040455
SHP/PEARL TEXTILE TRADING LIMITED
/22F WING ON PLAZA TSIM SHA TSUI
/HONG KONG
/HK/999077
CNE/BANGKOK APPAREL IMPORT CO LTD
/128 PRACHACHUEN ROAD
/NONTHABURI
/TH/11000/TE/6621501234""",
    # --- 217-08722689 : weight off by 0.2 KG -> MATCHED_WITH_TOLERANCE
    "FWB_21708722689.txt": """FWB/16
217-08722689HKGBKK/T2K80.0
FLT/TG605/18
RTG/BKKTG
SHP
/GOLDEN STAR LOGISTICS LIMITED
/7 HOI YUEN ROAD KWUN TONG
/HONG KONG
/HK
CNE
/STAR IMPORT EXPORT CO LTD
/55 RAMA 9 ROAD
/BANGKOK
/TH
AGT//1316100
/GOLDEN AGENT HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P2/K80.0/CQ/W80.0/R12.00/T960.000
/NG/SPARE PARTS
ISU/18JUL26/HKG
REF/HKGGST
SPH/SPX""",
    "FHL_GS26070030.txt": """FHL/4
MBI/217-08722689HKGBKK/T2K80.0
HBS/GS26070030/HKGBKK/2/K79.8//SPARE PARTS
HTS/87089900
OCI/TH/CNE/T/TAX 0105531040599
SHP/GOLDEN STAR SHIPPER LIMITED
/7 HOI YUEN ROAD KWUN TONG
/HONG KONG
/HK/999077
CNE/STAR AUTO PARTS THAILAND CO LTD
/AMATA CITY INDUSTRIAL ESTATE
/CHONBURI
/TH/20000/TE/6638213344""",
    "invalid_message.txt": "HELLO WORLD\nTHIS IS NOT A CARGO IMP MESSAGE",
}


def main() -> None:
    if "--reset" in sys.argv and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"removed {DB_PATH}")
    init_db()

    payloads: list[tuple[str, str]] = []
    for name in ("FWB_21708722685.txt", "FHL_WM26070003.txt",
                 "FFM_TG601_16JUL26.txt", "FSU_21708722685.txt"):
        with open(os.path.join(SAMPLES, name)) as f:
            payloads.append((name, f.read()))
    payloads += list(SYNTHETIC.items())

    with db() as conn:
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
    print(f"\nDatabase: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()
