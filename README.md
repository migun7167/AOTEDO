# Paperless AOT — FWB / FHL Matching Portal

ระบบนำเข้าและจับคู่ข้อความ IATA Cargo-IMP (FWB / FHL / FFM / FSU) พร้อม Dashboard,
หน้าดู Raw Data จาก database แบบ multi-condition filter สำหรับงาน analysis
และหน้ารายละเอียดการจับคู่รายฉบับ

Stack: **FastAPI + SQLite + vanilla JS SPA** — ไม่ต้องมี build step, ไม่ต้องต่อ
internet ตอนใช้งาน (web font ถูก self-host ไว้ในโปรเจกต์แล้ว)

---

## เริ่มใช้งาน

```bash
./run.sh
# เปิด http://127.0.0.1:8000
```

`run.sh` จะติดตั้ง dependency ให้ถ้ายังไม่มี และ seed ข้อมูลตัวอย่างให้อัตโนมัติ
ถ้า database ยังว่าง หรือจะสั่งเองทีละขั้นก็ได้:

```bash
pip install -r backend/requirements.txt
python3 scripts/seed.py --reset          # ล้างแล้ว seed ใหม่
cd backend && python3 -m uvicorn main:app --port 8000
```

รัน test:

```bash
cd backend && python3 -m pytest tests/ -q      # 34 tests
```

---

## ข้อมูลตัวอย่างที่ seed ไว้

`scripts/seed.py` นำเข้าไฟล์จริงทั้ง 4 ไฟล์ใน `samples/` บวกข้อมูลสังเคราะห์
เพื่อให้เห็นครบทุกสถานะบนหน้าจอ:

| MAWB | สถานะ | ที่มา |
|---|---|---|
| 217-08722685 | `MATCHED` (score 100) | FWB + FHL + FFM + FSU ตัวอย่างจริง |
| 217-08722686 | `PARTIAL_MATCH` (70) | 2 house, pieces 8/10 และ weight 320/400 |
| 217-08722687 | `WAITING_FOR_FHL` (50) | มี FWB ยังไม่มี FHL |
| 217-08722688 | `WAITING_FOR_FWB` (0) | มี FHL ยังไม่มี FWB |
| 217-08722689 | `MATCHED_WITH_TOLERANCE` (95) | น้ำหนักต่าง 0.2 KG อยู่ใน tolerance |
| — | `INVALID_FORMAT` | ไฟล์ที่ไม่ใช่ Cargo-IMP |

---

## หน้าจอ

**Dashboard** — summary card 6 ใบ (Imported Today / Matched / Waiting /
Partial / Errors / Duplicates) คลิกแต่ละใบเพื่อ filter ต่อได้, donut chart
สัดส่วนสถานะ, กราฟ import ย้อนหลัง 14 วัน และ recent activity

**Import** — drag & drop หลายไฟล์พร้อมกัน หรือ paste raw message
ระบบตรวจประเภทข้อความเอง แสดงผลรายไฟล์พร้อม batch number
(`IMP-YYYYMMDD-NNNNNN`) และลิงก์ไปดูผล match ทันที

**Match Results** — ตารางผลจับคู่พร้อม filter (สถานะ, origin, destination,
reviewed) และ full-text search ครอบ MAWB / HAWB / shipper / consignee / flight
คลิกแถวเพื่อเปิดรายละเอียด 6 แท็บ: Overview (พร้อม FSU timeline), Houses,
Comparison (ผล validation รายกฎ), Raw, Parsed JSON, History

**Raw Data / Analysis** — ดูตารางดิบทั้ง 10 ตารางจาก database
- ต่อเงื่อนไขได้ไม่จำกัด รวมแบบ **AND หรือ OR**
- operator: `= ≠ contains starts-with > ≥ < ≤ is-empty not-empty`
- ช่องกรอกค่ามี dropdown แนะนำค่าที่มีจริงในคอลัมน์นั้น (พร้อมจำนวนแถว)
- เลือกซ่อน/แสดงคอลัมน์, sort ทุกคอลัมน์, คลิกแถวดูค่าเต็มทุก field
- **Group by** — สรุป COUNT / SUM / AVG / MIN / MAX ตามคอลัมน์ใดก็ได้
  โดยใช้ filter ชุดเดียวกับตาราง
- Export CSV ตาม filter ปัจจุบัน

---

## โครงสร้างโปรเจกต์

```
backend/
  main.py                    REST API + host frontend
  app/
    database.py              schema + connection (SQLite)
    parser/
      detector.py            ตรวจ type/version จากบรรทัดแรก
      segmenter.py           ตัด segment (รองรับทั้งไฟล์ word-wrap และ canonical)
      base.py                normalize MAWB / airport / ตัวเลข
      fwb_v16.py fhl_v4.py ffm.py fsu.py
      __init__.py            PARSER_REGISTRY
    matching/engine.py       scoring + validation rules
    services/import_service.py  import → parse → persist → re-match → audit
  tests/                     34 tests (parser, matching, API end-to-end)
frontend/                    index.html + css/ + js/app.js + fonts/ (self-hosted)
scripts/seed.py              โหลดข้อมูลตัวอย่าง
scripts/fetch_fonts.py       ดาวน์โหลด web font มาเก็บในโปรเจกต์
samples/                     ไฟล์ตัวอย่าง FWB / FHL / FFM / FSU
docs/                        design document ต้นทาง
```

---

## Parser

ตัว segmenter รองรับไฟล์สองรูปแบบให้ผลเหมือนกัน: แบบ canonical (segment ละบรรทัด
ขึ้นบรรทัดใหม่ด้วย `/`) และแบบที่ถูก word-wrap มาแล้วอย่างไฟล์ตัวอย่าง — โดยยุบ
whitespace ทั้งหมดเป็น space เดียวแล้วตัดที่ keyword ที่นำหน้าด้วย whitespace เท่านั้น
จุดนี้สำคัญ เพราะทำให้ `CNE` ที่อยู่กลาง `OCI/TH/CNE/T/TAX ...` ไม่ถูกตัดเป็น segment ใหม่

เพิ่ม version ใหม่โดยไม่กระทบของเดิม:

```python
# backend/app/parser/__init__.py
PARSER_REGISTRY[("FWB", "17")] = fwb_v17.parse
```

## Matching

Key หลักคือ `FWB.MAWB = FHL.MAWB` — ถ้า MAWB ไม่ตรงจะไม่จับคู่เด็ดขาด
คะแนน: MAWB 50 + Origin 10 + Destination 10 + Pieces 15 + Weight 15
(น้ำหนักตรงพอดี 15, อยู่ใน tolerance 10)

Tolerance ตั้งที่ `backend/app/matching/engine.py` — ปัจจุบัน 0.5 KG หรือ 0.5%
ผ่านอย่างใดอย่างหนึ่ง

Re-match จะทำงานอัตโนมัติทุกครั้งที่มีข้อความใหม่ของ MAWB นั้นเข้ามา และบันทึกลง
`match_history` ทุกครั้ง ถ้า FHL ตัวเดิม (HAWB ซ้ำ) ถูก import ใหม่ ระบบจะใช้แถวล่าสุด
แถวเดียวในการคำนวณ ไม่นับเป็น duplicate HAWB

## Duplicate

ตรวจด้วย SHA-256 ของ raw message — ไฟล์เดิมเป๊ะจะได้สถานะ `DUPLICATE` และไม่สร้าง
parsed record ซ้ำ แต่ raw message ยังถูกเก็บไว้ทุกครั้งเพื่อการ audit

---

## API

| Method | Path | หน้าที่ |
|---|---|---|
| POST | `/api/v1/imports/files` | upload หลายไฟล์ |
| POST | `/api/v1/imports/text` | paste raw message |
| GET | `/api/v1/matches` | list + filter + pagination |
| GET | `/api/v1/matches/{mawb}` | รายละเอียดพร้อม houses / validations / history / FSU |
| POST | `/api/v1/matches/{mawb}/rematch` | จับคู่ใหม่ |
| POST | `/api/v1/matches/{mawb}/review` | mark reviewed + note |
| GET | `/api/v1/dashboard/summary` | ตัวเลขทั้งหมดของ dashboard |
| GET | `/api/v1/data/tables` | รายชื่อตาราง + คอลัมน์ + จำนวนแถว |
| GET | `/api/v1/data/{table}` | query ดิบ `?filter=col:op:value&match=and\|or` |
| GET | `/api/v1/data/{table}/distinct` | ค่าที่มีจริงในคอลัมน์ (ใช้เติม dropdown) |
| GET | `/api/v1/data/{table}/aggregate` | group by + COUNT/SUM/AVG/MIN/MAX |
| GET | `/api/v1/data/{table}/export` | CSV ตาม filter |
| GET | `/api/v1/messages/{id}/raw` \| `/parsed` | ข้อความดิบ / JSON ที่ parse แล้ว |
| GET | `/health/live` \| `/health/ready` | health check |

ชื่อตารางและคอลัมน์ทุกตัวที่รับจาก client ถูกตรวจกับ allow-list
(`EXPLORER_TABLES` ใน `main.py`) ก่อนนำไปประกอบ SQL ส่วนค่าที่ผู้ใช้กรอกส่งเป็น
bound parameter เสมอ — ตาราง/คอลัมน์นอกรายการจะถูกปฏิเสธ ไม่ถูกนำไป execute

---

## หมายเหตุการนำไป production

โปรเจกต์นี้ทำถึงระดับ Phase 1–2 ของ design document สิ่งที่ยังต้องเพิ่มก่อนขึ้นจริง:

- Authentication / RBAC — ตอนนี้ทุก endpoint เปิดและ audit log บันทึกเป็น
  `system` / `operator` แบบ hard-code
- ย้ายไป PostgreSQL ถ้าต้องรองรับ concurrent write สูง (schema ออกแบบตามเอกสารเดิมไว้แล้ว)
- Manual link / unlink FHL (FR-014) และ export Excel หลาย sheet (FR-019)
  ยังไม่ได้ทำ — ตอนนี้ export เป็น CSV
