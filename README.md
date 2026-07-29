# Paperless AOT — FWB / FHL Matching Portal

ระบบนำเข้าและจับคู่ข้อความ IATA Cargo-IMP (FWB / FHL / FFM / FSU) พร้อม Dashboard,
หน้าดู Raw Data จาก database แบบ multi-condition filter สำหรับงาน analysis,
หน้ารายละเอียดการจับคู่รายฉบับ, การจับคู่ด้วยมือ, ตั้งค่ากฎการ match ได้จากหน้าจอ
, ออกใบ Delivery Order สำหรับศุลกากร
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
cd backend && python3 -m pytest tests/ -q      # 177 tests
```

### บัญชีเริ่มต้น

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | ADMINISTRATOR |
| `operator` | `operator123` | OPERATOR |
| `viewer` | `viewer123` | VIEWER |

บัญชีเหล่านี้สร้างอัตโนมัติตอน database ว่างเปล่า และ **ระบบบังคับให้ตั้งรหัสผ่านใหม่
ตอนเข้าระบบครั้งแรก** — ปิดหน้าต่างหรือกด Escape ข้ามไม่ได้ รหัสที่ประกาศไว้ข้างบน
จึงใช้ได้ครั้งเดียวเท่านั้น

รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัว มีทั้งตัวอักษรและตัวเลข ไม่ซ้ำชื่อผู้ใช้
และไม่อยู่ในรายการรหัสที่เดาง่าย (รวมรหัสเริ่มต้นทั้งสามข้างบน)

ใส่รหัสผิดเกิน 5 ครั้งใน 15 นาที บัญชีนั้นจะถูกล็อกชั่วคราว (นับแยกรายบัญชี)
ทุกครั้งที่ลองเข้าระบบถูกบันทึกไว้ในตาราง `login_attempts` ดูได้จากหน้า Raw Data

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
| ออก Delivery Order (เดี่ยว / รวม / บางส่วน) | ✓ | ✓ | |
| แยก DO รวมออกเป็นหลายใบ | ✓ | ✓ | |
| ข้ามกฎผู้รับ / แทนที่ / ยกเลิก DO | ✓ | | |
| แก้ไข DO ที่ออกไปแล้ว | ✓ | | |
| พิมพ์ DO ที่ออกแล้ว | ✓ | ✓ | ✓ |
| ดู Audit Log | ✓ | | |
| จัดการผู้ใช้ (เพิ่ม / เปลี่ยนบทบาท / ปิดใช้งาน / ตั้งรหัสใหม่) | ✓ | | |
| เปลี่ยนรหัสผ่านของตัวเอง | ✓ | ✓ | ✓ |

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
| 217-08722690 | `MATCHED` (100) | 2 house ของผู้รับรายเดียวกัน — ใช้ลองรวมเป็น DO ใบเดียว |
| — | `INVALID_FORMAT` | ไฟล์ที่ไม่ใช่ Cargo-IMP |

อีกสองชุดวางไว้ให้ import เองผ่านหน้า Import ไม่ถูก seed อัตโนมัติ:

| โฟลเดอร์ | MAWB | ไว้ทดสอบอะไร |
|---|---|---|
| `samples/testset/` | 217-08722700 | ชุด FWB + FHL x2 + FFM + FSU ที่ match 100 % (ขาออก BKK → NRT) |
| `samples/splitset/` | 217-08722734 | ชุด 5 house ที่ match 100 % สำหรับทดสอบ **แยก DO** และ **ปล่อยของบางส่วน** |

`splitset` จัด house ไว้ให้ครบทุกเคส — 3 house เป็นผู้รับรายเดียวกันแต่สะกดชื่อ
บริษัทมาคนละแบบ (ทดสอบการรวมแล้วแยก 1 + 2), อีก 2 house เป็นผู้รับอีกราย และ
house ที่ใหญ่ที่สุดมี 12 ชิ้น / 480 K หารเป็น 5 + 4 + 3 ได้พอดีสำหรับทยอยปล่อยของ
รายละเอียดและขั้นตอนทดสอบอยู่ใน `samples/splitset/README.txt`

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

**Raw Data / Analysis** — ดูตารางดิบทั้ง 16 ตารางจาก database
- ต่อเงื่อนไขได้ไม่จำกัด รวมแบบ **AND หรือ OR**
- operator: `= ≠ contains starts-with > ≥ < ≤ is-empty not-empty`
- ช่องกรอกค่ามี dropdown แนะนำค่าที่มีจริงในคอลัมน์นั้น (พร้อมจำนวนแถว)
- เลือกซ่อน/แสดงคอลัมน์, sort ทุกคอลัมน์, คลิกแถวดูค่าเต็มทุก field
- **Group by** — สรุป COUNT / SUM / AVG / MIN / MAX ตามคอลัมน์ใดก็ได้
  โดยใช้ filter ชุดเดียวกับตาราง
- Export CSV ตาม filter ปัจจุบัน

**Delivery Orders** — ออกใบ DO (Delivery Order / Customs Manifestation) จากข้อมูลที่
match ได้ ดูรายละเอียดหัวข้อถัดไป

**Errors** — ไฟล์ที่ parse ไม่สำเร็จ, validation rule ที่ไม่ผ่าน (คลิกไปหน้ารายละเอียดได้)
และรายการข้อความซ้ำ

**History** — ไทม์ไลน์การเปลี่ยนสถานะทุก MAWB กรองด้วย MAWB ได้

**Audit Log** (admin) — ทุก write action พร้อม user, before/after, เหตุผล และ IP

**Users** (admin) — เพิ่มผู้ใช้ เปลี่ยนบทบาท ปิด/เปิดการใช้งาน และตั้งรหัสผ่านใหม่ให้
ผู้ใช้ (ผู้ใช้คนนั้นต้องเปลี่ยนเองอีกครั้งตอนเข้าระบบ) ระบบกันไม่ให้ปิดบัญชีตัวเอง
และกันไม่ให้เหลือระบบไว้โดยไม่มี Administrator ที่ใช้งานได้เลย

ทุกบทบาทเปลี่ยนรหัสผ่านตัวเองได้จากปุ่ม 🔑 มุมขวาบน — เปลี่ยนแล้ว session ทั้งหมด
ของบัญชีนั้นถูกยกเลิก ต้องเข้าระบบใหม่

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
      do_service.py          Delivery Order — mapping, Code 39, HTML และ PDF
  tests/                     177 tests (parser, matching, API, RBAC, DO, combine, split, users)
frontend/                    index.html + css/ + js/app.js + fonts/ (self-hosted)
scripts/seed.py              โหลดข้อมูลตัวอย่าง
scripts/fetch_fonts.py       ดาวน์โหลด web font มาเก็บในโปรเจกต์
samples/                     ไฟล์ตัวอย่างจริง + demo/ ชุดสาธิต +
                             testset/ และ splitset/ ชุดที่ match 100 %
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

## Delivery Order

DO เป็นเอกสารระดับ house ออกได้จากปุ่ม **🧾 สร้าง DO** ในแท็บ Houses ของหน้า
รายละเอียด MAWB — ปกติหนึ่งใบต่อหนึ่ง HAWB แต่รวมหลาย house ไว้ใบเดียว
([Combine](#รวมหลาย-house-ไว้ใน-do-ใบเดียว-combine)) หรือแยก/ทยอยปล่อยของ
([Split & Part Delivery](#แยก-do-split-และการปล่อยของบางส่วน-part-delivery)) ก็ได้

ทุกช่องบนเอกสารเติมจากข้อมูลที่ match มาแล้ว:

| ช่องบน DO | มาจาก |
|---|---|
| บาร์โค้ด + เลขใต้บาร์โค้ด | HAWB (Code 39 วาดเองใน SVG/PDF ไม่ต้องใช้ library ภายนอก) |
| Station | เมืองของสนามบินปลายทาง (BKK → BANGKOK) |
| CNEE + ที่อยู่ | consignee จาก FHL พร้อมรหัสไปรษณีย์และชื่อประเทศ |
| Air Waybill No | MAWB (ไม่มีขีด) และ HAWB |
| Pieces / Weight | ของ house เทียบกับของ master — `1 of 1`, `149 of 149K` (ใบปล่อยบางส่วนเทียบกับของ house แทน) |
| Brd. Pnt / Off. Pnt | origin / destination |
| Flight No | เที่ยวบินจาก FWB เติมศูนย์เป็น 4 หลัก (TG601 → TG0601) |
| Landed on Date/ATA | FSU เหตุการณ์ RCF หรือ ARR (เลือกใบที่มีเวลานาฬิกาก่อน) |
| Date and time of expiry | ATA + 48 ชั่วโมง |
| Nature of Goods | commodity จาก FHL |
| ชื่อสายการบิน + ข้อความท้ายเอกสาร | จาก airline prefix (217 → Thai Airways) |

สามช่องที่ข้อความ Cargo-IMP ไม่มีข้อมูลให้ ระบบจะถามในกล่องก่อนออกเอกสาร:
**Aircraft Registration**, **Customer Code** และ **ATA** (กรณี FSU ส่งมาแต่วันที่ไม่มีเวลา)

เลข DO เดินอัตโนมัติจากค่าเริ่มต้นที่ตั้งในหน้า Settings เอกสารที่ออกแล้วถูกเก็บไว้
กดออกซ้ำจะได้**เลขเดิม**พร้อมลายน้ำ REPRINT ถ้าข้อมูลผิดจริง ๆ Administrator
ติ๊ก "แก้ไข DO ที่ออกไปแล้ว" เพื่อเขียนทับเนื้อหาโดยคงเลขเดิมได้ (บันทึก audit log ทุกครั้ง)

ผลลัพธ์เลือกได้สองแบบ: **หน้าพิมพ์ HTML** (สั่ง Print → Save as PDF จากเบราว์เซอร์
ได้ทุกเครื่อง) หรือ **ดาวน์โหลด PDF** ขนาด A4 ที่ระบบสร้างเอง

### รวมหลาย House ไว้ใน DO ใบเดียว (Combine)

ผู้รับรายเดียวกันที่มีของหลาย house ไม่ต้องถือ DO หลายใบมารับของ — รวมเป็นใบเดียวได้
โดยตารางบนเอกสารจะมีหนึ่งบรรทัดต่อหนึ่ง HAWB พร้อมแถวรวมท้ายตาราง

ทำได้สองทาง:
- **แท็บ Houses** ของ MAWB — ติ๊กเลือก house ที่ต้องการแล้วกด "รวมเป็น DO ใบเดียว"
- **หน้า Delivery Orders** — ระบบไล่หาผู้รับที่มีของมากกว่า 1 house และยังไม่ได้ออก DO
  มาแสดงเป็นรายการให้กดรวมได้ทันที (รวมข้าม MAWB และข้ามเที่ยวบินได้)

กฎที่ระบบบังคับ:

| กฎ | ข้ามได้ไหม |
|---|---|
| ต้องเลือกอย่างน้อย 2 house | ไม่ได้ |
| ปลายทางต้องเป็นสถานีเดียวกัน | ไม่ได้ — ส่งของไปสองที่ด้วยใบเดียวไม่ได้ |
| ผู้รับปลายทางต้องเป็นรายเดียวกัน | Administrator ข้ามได้พร้อมระบุเหตุผล |
| house ต้องยังไม่มี DO ที่ใช้งานอยู่ | Administrator เลือก "แทนที่ DO เดิม" ได้ |

การเทียบชื่อผู้รับตัดคำต่อท้ายอย่าง CO / LTD / COMPANY / LIMITED / (THAILAND) และ
เครื่องหมายวรรคตอนออกก่อน ทำให้ `SEIKO PRECISION THAILAND CO LTD` กับ
`SEIKO PRECISION (THAILAND) COMPANY LIMITED` ถือเป็นรายเดียวกันโดยไม่ต้องข้ามกฎ

**สิ่งที่ต่างจาก DO เดี่ยว:**
- บาร์โค้ดเป็น **เลข DO** แทน HAWB เพราะเอกสารครอบหลาย house
- วันหมดอายุ 48 ชั่วโมงนับจาก **เที่ยวบินที่ลงหลังสุด** ไม่งั้นบรรทัดที่มาก่อนจะหมดอายุ
  ก่อนที่ผู้รับจะมารับได้
- มีแถว TOTAL รวมจำนวนชิ้นและน้ำหนักท้ายตาราง

ช่อง SHC บนเอกสารต้นแบบเว้นว่าง ระบบจึงเว้นว่างเป็นค่าเริ่มต้น (`do_shc_source = HOUSE`)
ถ้าต้องการให้พิมพ์ SPH ของใบแม่ (เช่น HEA SPX) เปลี่ยนเป็น `MASTER` ในหน้า Settings

### แยก DO (Split) และการปล่อยของบางส่วน (Part Delivery)

คำว่า "แยก DO" ในงานจริงหมายถึงสองเรื่องคนละแบบ ระบบทำไว้ทั้งสองอย่าง

**1. แยกตาม house** — DO รวมที่ออกไปแล้วต้องแตกออกเป็นหลายใบ เพราะผู้รับส่ง
ตัวแทนมารับคนละคน หรือของบางส่วนติดพิธีการศุลกากร กดปุ่ม **✂ แยก** ในหน้า
Delivery Orders (ขึ้นเฉพาะใบที่มีมากกว่า 1 house) แล้วติ๊กว่า house ใบไหนไป
เอกสารใหม่ใบที่ 1 ส่วนที่เหลือรวมเป็นใบที่ 2 โดยอัตโนมัติ

- ต้องแบ่งให้ครบ — house ทุกใบบนเอกสารเดิมต้องไปอยู่ในกลุ่มใดกลุ่มหนึ่ง
  ไม่มีตกหล่นและไม่ซ้ำ (ปุ่มบันทึกจะยังกดไม่ได้ถ้าเหลือกลุ่มว่าง)
- กลุ่มที่ได้ house เดียวออกมาเป็น DO เดี่ยว กลุ่มที่ได้ตั้งแต่ 2 ใบยังเป็น DO รวม
- ใบใหม่ทุกใบได้**เลข DO ใหม่** ส่วนใบเดิมเปลี่ยนเป็น `SUPERSEDED` ไม่ถูกแก้ทับ
  เอกสารปล่อยของที่ออกจากเคาน์เตอร์ไปแล้วต้องอ่านย้อนได้ตรงกับที่พิมพ์ไป
- แต่ละใบใหม่บันทึก `split_from` ชี้กลับไปที่ใบเดิม และ audit log เก็บเหตุผลที่กรอก

**2. ปล่อยบางส่วน (part delivery)** — house ใบเดียวแต่ผู้รับมารับไม่หมดในครั้งเดียว
ในกล่องสร้าง DO ติ๊ก "ปล่อยของบางส่วน" แล้วกรอกจำนวนชิ้น/น้ำหนักที่ปล่อยรอบนี้
กล่องจะแสดงยอดคงเหลือของ house ให้เห็นก่อนเสมอ

- ช่อง Pieces / Weight บนเอกสารเปลี่ยนไปเทียบกับ**ของ house** แทนของ master
  (`1 of 4`, `40 of 160K`) เพราะเลข master ไม่บอกอะไรกับคนที่รับของบางส่วน
- ช่อง Nature of Goods ต่อท้ายด้วย **PART DELIVERY** และมีกล่องสรุปยอดคงเหลือ
  ใต้ตาราง ("ยอดคงเหลือของ House: UC26070040 เหลือ 3 ชิ้น / 120K")
- DO เต็มจำนวนยังพิมพ์เหมือนเดิมทุกตัวอักษร — เทียบกับ master และไม่มีคำว่า
  PART DELIVERY (มี test ตรึงไว้)

**บัญชีของที่ปล่อยแล้ว** แทนกฎเดิม "1 house ต่อ 1 DO" ด้วยกฎที่ตรงกับงานจริงกว่า:
*ปล่อยรวมกันเกินที่ house มีไม่ได้* ระบบรวมยอดจาก DO ที่ยัง ACTIVE ทุกใบของ
house นั้น แล้วเทียบกับจำนวนใน FHL

| สถานการณ์ | ผลลัพธ์ |
|---|---|
| ออกใบเต็มจำนวนซ้ำ | ได้เลขเดิม + ลายน้ำ REPRINT (ไม่นับซ้ำในบัญชี) |
| ปล่อยบางส่วนแล้วขอต่ออีกส่วน | ออกใบใหม่ได้จนกว่ายอดจะครบ |
| ขอเกินยอดคงเหลือ | ปฏิเสธด้วย `409 DO_OVER_RELEASE` บอกว่าเหลือเท่าไร |
| ของถูกปล่อยครบแล้ว | ปฏิเสธ พร้อมชื่อ DO ที่ปล่อยไป |
| ใบถูก `CANCELLED` / `SUPERSEDED` | ยอดคืนเข้าบัญชีทันที ออกใหม่ได้ |

การปฏิเสธเพราะของหมดเป็นคนละเรื่องกับการหา house ไม่เจอ ระบบจึงตอบ `409`
(ของถูกจองไปแล้ว) ไม่ใช่ `404` (ไม่มีของชิ้นนี้)

เฉพาะใบที่ปล่อย**เต็มจำนวน**เท่านั้นที่จองเลข HAWB ไว้บนหัวเอกสาร ใบปล่อยบางส่วน
เว้นช่องนั้นว่าง หลายใบของ house เดียวกันจึงอยู่ร่วมกันได้

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
| POST | `/api/v1/auth/password` | เปลี่ยนรหัสผ่านตัวเอง | ทุกบทบาท |
| GET/POST | `/api/v1/users` | ดู / เพิ่มผู้ใช้ | admin |
| PATCH | `/api/v1/users/{id}` | เปลี่ยนบทบาท / เปิด-ปิดใช้งาน | admin |
| POST | `/api/v1/users/{id}/password` | ตั้งรหัสผ่านใหม่ให้ผู้ใช้ | admin |
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
| POST | `/api/v1/matches/{mawb}/houses/{id}/do` | ออก / พิมพ์ซ้ำ / แก้ไข DO | admin, operator (แก้ไข = admin) |
| GET | `/api/v1/do/combinable` | ผู้รับที่มีของหลาย house และยังไม่มี DO | ทุกบทบาท |
| POST | `/api/v1/do/combine` | ออก DO รวมหลาย house | admin, operator (ข้ามกฎ = admin) |
| POST | `/api/v1/do/{id}/split` | แยก DO รวมออกเป็นหลายใบตาม house | admin, operator |
| GET | `/api/v1/do/houses/{id}/balance` | ยอดคงเหลือของ house และใบที่ปล่อยไปแล้ว | ทุกบทบาท |
| POST | `/api/v1/do/{id}/cancel` | ยกเลิก DO เพื่อคืนยอดให้ house | admin |
| GET | `/api/v1/do` | รายการ DO ที่ออกแล้ว | ทุกบทบาท |
| GET | `/api/v1/do/{id}/preview` \| `/pdf` | หน้าพิมพ์ HTML / ไฟล์ PDF | ทุกบทบาท |
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

1. **ให้บริการผ่าน HTTPS** แล้วเปิด flag `secure` ของ session cookie
   (`SESSION_COOKIE` ใน `backend/app/services/auth.py`)
2. **ย้ายไป PostgreSQL** ถ้าต้องรองรับ concurrent write สูง — schema ออกแบบตาม
   เอกสารเดิมไว้แล้ว
3. **ลบหรือปิดบัญชีสาธิต** ที่ไม่ได้ใช้ (operator / viewer) จากหน้า Users
4. ยังไม่ได้ทำ: antivirus scan hook, การเข้ารหัสข้อมูลที่ rest
   และการรับข้อมูลทาง SFTP / message queue (Phase 3 ในเอกสาร)
   ส่วน rate limiting ตอนนี้มีเฉพาะหน้า login ยังไม่ได้ครอบ API อื่น
