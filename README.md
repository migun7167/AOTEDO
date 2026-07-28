# Paperless AOT — FWB / FHL Matching Portal

ระบบนำเข้าและจับคู่ข้อความ IATA Cargo-IMP (FWB / FHL / FFM / FSU) พร้อม Dashboard,
หน้าดู Raw Data จาก database แบบ multi-condition filter สำหรับงาน analysis,
หน้ารายละเอียดการจับคู่รายฉบับ, การจับคู่ด้วยมือ, ตั้งค่ากฎการ match ได้จากหน้าจอ
และ export เป็น Excel / CSV / JSON / ไฟล์ต้นฉบับ

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
cd backend && python3 -m pytest tests/ -q      # 58 tests
```

### บัญชีเริ่มต้น

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | ADMINISTRATOR |
| `operator` | `operator123` | OPERATOR |
| `viewer` | `viewer123` | VIEWER |

บัญชีเหล่านี้สร้างอัตโนมัติตอน database ว่างเปล่า **ต้องเปลี่ยนรหัสผ่านก่อนใช้งานจริง**
(ดูหัวข้อ "ก่อนขึ้น production" ท้ายไฟล์)

---

## สิทธิ์ตามบทบาท (เอกสารออกแบบ §4)

| | ADMINISTRATOR | OPERATOR | VIEWER |
|---|:---:|:---:|:---:|
| ดู Dashboard / Match Result / Raw Data | ✓ | ✓ | ✓ |
| Export ทุกรูปแบบ | ✓ | ✓ | ✓ |
| Import ไฟล์ / paste text | ✓ | ✓ | |
| Mark as Reviewed + หมายเหตุ | ✓ | ✓ | |
| Re-match | ✓ | | |
| Manual link / unlink FHL | ✓ | | |
| Resolve / Reject (override สถานะ) | ✓ | | |
| ตั้งค่า Matching Rule | ✓ | | |
| ดู Audit Log | ✓ | | |

Session เก็บใน cookie แบบ HttpOnly อายุ 12 ชั่วโมง รหัสผ่าน hash ด้วย
PBKDF2-HMAC-SHA256 120,000 รอบ พร้อม salt ต่อผู้ใช้

---

## ข้อมูลตัวอย่างที่ seed ไว้

`scripts/seed.py` นำเข้าไฟล์จริงทั้ง 4 ไฟล์ใน `samples/` บวกชุดสาธิตใน
`samples/demo/` เพื่อให้เห็นครบทุกสถานะบนหน้าจอ:

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
(`IMP-YYYYMMDD-NNNNNN`) และลิงก์ไปดูผล match ทันที ไฟล์ที่ซ้ำจะชี้กลับไปยัง
รายการเดิมให้ตรวจสอบได้

**Match Results** — ตารางผลจับคู่พร้อม filter: สถานะ, origin, destination,
airline prefix, flight, FWB version, มี/ไม่มี duplicate, ช่วงวันที่ และ reviewed
ส่วน search ครอบ MAWB / HAWB / shipper / consignee / flight / reference /
ชื่อไฟล์ / batch number

คลิกแถวเพื่อเปิดรายละเอียด 6 แท็บ:
- **Overview** — ข้อมูลหลักพร้อม FSU timeline
- **Houses** — รายการ house พร้อมป้าย AUTO/MANUAL, ปุ่ม link/unlink (admin)
- **Comparison** — ผล validation ครบ 10 กฎ
- **Raw** — ข้อความต้นฉบับทุกฉบับของ MAWB นั้น พร้อมปุ่ม copy
- **Parsed** — JSON ที่ parse ได้
- **History** — ทุกการเปลี่ยนสถานะ

**Raw Data / Analysis** — ดูตารางดิบทั้ง 11 ตารางจาก database
- ต่อเงื่อนไขได้ไม่จำกัด รวมแบบ **AND หรือ OR**
- operator: `= ≠ contains starts-with > ≥ < ≤ is-empty not-empty`
- ช่องกรอกค่ามี dropdown แนะนำค่าที่มีจริงในคอลัมน์นั้น (พร้อมจำนวนแถว)
- เลือกซ่อน/แสดงคอลัมน์, sort ทุกคอลัมน์, คลิกแถวดูค่าเต็มทุก field
- **Group by** — สรุป COUNT / SUM / AVG / MIN / MAX ตามคอลัมน์ใดก็ได้
  โดยใช้ filter ชุดเดียวกับตาราง
- Export CSV ตาม filter ปัจจุบัน

**Errors** — ไฟล์ที่ parse ไม่สำเร็จ, validation rule ที่ไม่ผ่าน (คลิกไปหน้ารายละเอียดได้)
และรายการข้อความซ้ำ

**History** — ไทม์ไลน์การเปลี่ยนสถานะทุก MAWB กรองด้วย MAWB ได้

**Audit Log** (admin) — ทุก write action พร้อม user, before/after, เหตุผล และ IP

**Settings** — ปรับ tolerance, คะแนนแต่ละกฎ, severity, version ที่รองรับ และ
ขนาดไฟล์สูงสุด กดบันทึกแล้วระบบ re-match ทุก MAWB ใหม่ทันทีและบันทึก audit log
(viewer/operator เห็นค่าได้แต่แก้ไม่ได้)

---

## โครงสร้างโปรเจกต์

```
backend/
  main.py                    REST API + host frontend
  app/
    database.py              schema + migration + connection (SQLite)
    parser/
      detector.py            ตรวจ type/version จากบรรทัดแรก
      segmenter.py           ตัด segment (รองรับทั้งไฟล์ word-wrap และ canonical)
      base.py                normalize MAWB / airport / ตัวเลข
      fwb_v16.py fhl_v4.py ffm.py fsu.py
      __init__.py            PARSER_REGISTRY
    matching/engine.py       MatchingConfig + scoring + validation rules
    services/
      import_service.py      import → parse → persist → re-match → audit
      auth.py                PBKDF2, session, RBAC dependency
      settings_service.py    matching rule ที่ปรับได้จากหน้าจอ
      export_service.py      Excel / CSV / JSON / raw zip
  tests/                     58 tests (parser, matching, API, RBAC)
frontend/                    index.html + css/ + js/app.js + fonts/ (self-hosted)
scripts/seed.py              โหลดข้อมูลตัวอย่าง
scripts/fetch_fonts.py       ดาวน์โหลด web font มาเก็บในโปรเจกต์
samples/                     ไฟล์ตัวอย่างจริง + demo/ ชุดสาธิต
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

Key หลักคือ `FWB.MAWB = FHL.MAWB` — การจับคู่อัตโนมัติจะไม่ข้าม MAWB เด็ดขาด
คะแนนเริ่มต้น: MAWB 50 + Origin 10 + Destination 10 + Pieces 15 + Weight 15
(น้ำหนักตรงพอดี 15, อยู่ใน tolerance 10) ทุกค่าปรับได้จากหน้า Settings

Validation ครบ 10 กฎ: `MAWB_MATCH`, `ORIGIN_MATCH`, `DESTINATION_MATCH`,
`PIECES_MATCH`, `WEIGHT_MATCH`, `WEIGHT_UNIT_MATCH`, `DUPLICATE_HAWB`,
`HAWB_PRESENT`, `MASTER_PRESENT`, `VERSION_SUPPORTED`

สามกฎที่ทำให้ข้อมูลเทียบกันไม่ได้เลย (`WEIGHT_UNIT_MATCH`, `HAWB_PRESENT`,
`MASTER_PRESENT`) จะทำให้สถานะเป็น `REJECTED` ส่วน route ไม่ตรงยังนับเป็น
`PARTIAL_MATCH` เพราะ pieces/weight ยังมีความหมายให้คนตรวจต่อได้

Re-match ทำงานอัตโนมัติเมื่อ: import ข้อความใหม่ของ MAWB นั้น, กด Re-match,
link/unlink house หรือเปลี่ยนค่าใน Settings — และบันทึกลง `match_history` ทุกครั้ง

## Manual match (FR-014)

Administrator link/unlink house ได้จากแท็บ Houses โดยต้องระบุเหตุผล
การตัดสินใจเก็บใน `house_link_overrides` แยกจากผลการ match จึง**อยู่รอดข้าม
การ re-match** ทุกครั้ง — re-match จะไม่ล้างสิ่งที่คนตั้งใจทำไว้ กด "คืนค่าอัตโนมัติ"
เพื่อลบ override แล้วกลับไปใช้ผลที่ระบบคำนวณ

ถ้า link house ที่ MAWB ต่างกัน กฎ `MAWB_MATCH` จะขึ้น FAIL ตามความจริง
ไม่ถูกกลบ และ house นั้นจะติดป้าย MANUAL ในตาราง

## Duplicate

- **Exact** — SHA-256 ของ raw message ตรงกัน → สถานะ `DUPLICATE`
  ไม่สร้าง parsed record ซ้ำ แต่ raw message ยังเก็บไว้เพื่อ audit
  และรายงาน MAWB ของรายการเดิมให้กดไปดูได้
- **Business key** — `type + MAWB + (HAWB) + version` ซ้ำแต่เนื้อไฟล์ต่าง
  ถือเป็น revision จึง parse และเก็บตามปกติ เพียงแต่ติดธง `BUSINESS_KEY`
  ให้เห็นในหน้า Errors

---

## API

| Method | Path | หน้าที่ | สิทธิ์ |
|---|---|---|---|
| POST | `/api/v1/auth/login` \| `/logout` | เข้า/ออกระบบ | — |
| GET | `/api/v1/auth/me` | ผู้ใช้ปัจจุบัน | ทุกบทบาท |
| POST | `/api/v1/imports/files` \| `/text` | นำเข้าไฟล์ / paste | admin, operator |
| GET | `/api/v1/imports/{batchId}` | รายละเอียด batch | ทุกบทบาท |
| GET | `/api/v1/matches` | list + filter + pagination | ทุกบทบาท |
| GET | `/api/v1/matches/{mawb}` | รายละเอียดครบทุกแท็บ | ทุกบทบาท |
| POST | `/api/v1/matches/{mawb}/rematch` | จับคู่ใหม่ | admin |
| POST | `/api/v1/matches/{mawb}/review` | mark reviewed + note | admin, operator |
| POST | `/api/v1/matches/{mawb}/status` | override เป็น RESOLVED/REJECTED | admin |
| POST | `/api/v1/matches/{mawb}/houses/{id}/link` \| `/unlink` | จับคู่ด้วยมือ | admin |
| DELETE | `/api/v1/matches/{mawb}/houses/{id}/link` | ล้าง override | admin |
| GET | `/api/v1/houses/unassigned` | house ที่เลือก link ได้ | ทุกบทบาท |
| GET | `/api/v1/dashboard/summary` | ตัวเลขทั้งหมดของ dashboard | ทุกบทบาท |
| GET | `/api/v1/errors` \| `/history` | หน้า Errors / History | ทุกบทบาท |
| GET | `/api/v1/audit` | audit log | admin |
| GET/PUT | `/api/v1/settings` | อ่าน/แก้ matching rule | อ่านทุกบทบาท, แก้ admin |
| GET | `/api/v1/data/tables` | รายชื่อตาราง + คอลัมน์ + จำนวนแถว | ทุกบทบาท |
| GET | `/api/v1/data/{table}` | query ดิบ `?filter=col:op:value&match=and\|or` | ทุกบทบาท |
| GET | `/api/v1/data/{table}/distinct` | ค่าที่มีจริงในคอลัมน์ | ทุกบทบาท |
| GET | `/api/v1/data/{table}/aggregate` | group by + COUNT/SUM/AVG/MIN/MAX | ทุกบทบาท |
| GET | `/api/v1/data/{table}/export` | CSV ของตารางตาม filter | ทุกบทบาท |
| POST/GET | `/api/v1/exports` | รายงาน XLSX / CSV / JSON / RAW zip | ทุกบทบาท |
| GET | `/api/v1/messages/{id}/raw` \| `/parsed` | ข้อความดิบ / JSON | ทุกบทบาท |
| GET | `/health/live` \| `/health/ready` \| `/metrics` | probe + Prometheus | เปิดสาธารณะ |

Excel ที่ export มี 6 sheet ตามเอกสาร (Summary, FWB, FHL, Validation Results,
Errors, Audit Log) บวก sheet Export Info และ RAW zip คือไฟล์ต้นฉบับแยกตาม MAWB
พร้อม `manifest.json`

ชื่อตารางและคอลัมน์ทุกตัวที่รับจาก client ถูกตรวจกับ allow-list
(`EXPLORER_TABLES` ใน `main.py`) ก่อนนำไปประกอบ SQL ส่วนค่าที่ผู้ใช้กรอกส่งเป็น
bound parameter เสมอ — ตาราง/คอลัมน์นอกรายการจะถูกปฏิเสธ ไม่ถูกนำไป execute

---

## ก่อนขึ้น production

โปรเจกต์นี้ทำครบ Phase 1–2 ของ design document สิ่งที่ยังต้องทำก่อนใช้งานจริง:

1. **เปลี่ยนรหัสผ่านบัญชีเริ่มต้นทั้งสาม** — ตอนนี้รหัสอยู่ในโค้ดและแสดงบนหน้า login
   เพื่อความสะดวกตอนสาธิต ยังไม่มีหน้าจัดการผู้ใช้/เปลี่ยนรหัสผ่าน ต้องแก้ผ่าน
   database โดยตรงหรือเพิ่มหน้าจอก่อน
2. **ให้บริการผ่าน HTTPS** แล้วเปิด flag `secure` ของ session cookie
   (`SESSION_COOKIE` ใน `backend/app/services/auth.py`)
3. **ย้ายไป PostgreSQL** ถ้าต้องรองรับ concurrent write สูง — schema ออกแบบตาม
   เอกสารเดิมไว้แล้ว
4. ยังไม่ได้ทำ: rate limiting, antivirus scan hook, การเข้ารหัสข้อมูลที่ rest
   และการรับข้อมูลทาง SFTP / message queue (Phase 3 ในเอกสาร)
