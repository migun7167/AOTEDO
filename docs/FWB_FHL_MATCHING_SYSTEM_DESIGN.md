# FWB–FHL Matching Portal

## 1. Project Overview

ระบบสำหรับนำเข้าไฟล์ข้อความมาตรฐาน IATA Cargo-IMP ประเภท:

- `FWB` — Master Air Waybill Message
- `FHL` — House Air Waybill Message

ระบบต้องสามารถ:

1. Import ไฟล์ข้อความ `.txt`
2. ตรวจจับประเภทข้อความอัตโนมัติ
3. Parse ข้อมูล Cargo-IMP
4. จัดเก็บ Raw Message และ Parsed Data
5. Match FWB กับ FHL ด้วย MAWB Number
6. รองรับ 1 FWB ต่อหลาย FHL
7. ตรวจสอบ Pieces, Weight, Route และ Duplicate
8. แสดงผลใน Dashboard และ Table
9. แสดงรายละเอียด Field-by-Field
10. Export ผลลัพธ์เป็น CSV หรือ Excel
11. รองรับ Manual Review และ Audit Log

---

## 2. Business Context

### 2.1 FWB

FWB เป็นข้อความระดับ Master Air Waybill

ตัวอย่าง:

```text
FWB/16
217-08722685HKGBKK/T1K149.0
FLT/TG601/16
RTG/BKKTG
SHP
/WM LOGISTICS WORLDWIDE LIMITED
/58 66 TAI LIN PAI ROAD KWAI CHUNG
/HONG KONG
/HK
CNE
/PLANET INTER LOGISTICS CO LTD
/2 59 60 BANGNA COMPLEX OFFICE TOWER
/BANGKOK
/TH
AGT//1316077
/NARITA EXPRESS HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P1/K149.0/CQ/W149.0/R10.76/T1603.240
/NG/CONSOL
/2/NV/MC0.44
/3/ND//NDA
OTH/P/AWC13MCC250.4MYC223.5
PPD/WT1603.24
/OC486.9/CT2090.14
ISU/16JUL26/HKG
REF/HKGFMCR
SPH/HEA/SPX
```

### 2.2 FHL

FHL เป็นข้อความระดับ House Air Waybill

ตัวอย่าง:

```text
FHL/4
MBI/217-08722685HKGBKK/T1K149.0
HBS/WM26070003/HKGBKK/1/K149.0//DRY BATTERY
HTS/85061012
OCI/TH/CNE/T/TAX 0105531040228
SHP/HARMONY ENTERPRISE COMPNAY LIMITED
/9F AMTEL BUILDING 148 DES VOEUX ROA
/HONG KONG
/HK/999077
CNE/SEIKO PRECISION THAILAND CO LTD
/NAVANAKORN INDUSTRIAL ESTATE ZONE 3
/PATHUMTHANI
/TH/12120/TE/66252921626
```

### 2.3 Relationship

ความสัมพันธ์หลัก:

```text
FWB.MAWB_NUMBER = FHL.MBI.MAWB_NUMBER
```

ตัวอย่าง:

```text
FWB MAWB: 217-08722685
FHL MBI : 217-08722685
```

โครงสร้าง:

```text
FWB: 217-08722685
│
├── FHL: WM26070003
├── FHL: WM26070004
└── FHL: WM26070005
```

---

## 3. Project Goals

ระบบต้องช่วยให้ผู้ใช้งาน:

- Import ไฟล์ FWB และ FHL ได้ง่าย
- เห็นผลการจับคู่ทันที
- รู้ว่าไฟล์ใด Match สำเร็จ
- รู้ว่าไฟล์ใดยังรอ FWB หรือ FHL
- เห็นความแตกต่างของ Pieces และ Weight
- ตรวจสอบข้อมูลผิดพลาดได้จากหน้าจอเดียว
- ลดการตรวจสอบไฟล์ด้วยมือ
- รองรับการขยายไปสู่ API, SFTP และ Message Queue ในอนาคต

---

## 4. User Roles

### 4.1 Administrator

สิทธิ์:

- Import ไฟล์
- ดูข้อมูลทั้งหมด
- Reprocess Message
- Manual Match
- Resolve Error
- Export Report
- จัดการ User
- ดู Audit Log
- ตั้งค่า Matching Rule

### 4.2 Operator

สิทธิ์:

- Import ไฟล์
- ดู Dashboard
- ดู Match Result
- Mark as Reviewed
- Export รายงาน
- เพิ่มหมายเหตุ

### 4.3 Viewer

สิทธิ์:

- ดู Dashboard
- ดู Match Result
- ดู Message Detail
- Export รายงานตามสิทธิ์

---

## 5. Functional Requirements

## FR-001: File Import

ระบบต้องรองรับ:

- Upload ไฟล์ `.txt`
- Upload หลายไฟล์พร้อมกัน
- Drag and Drop
- Paste Raw Cargo-IMP Message
- จำกัดขนาดไฟล์ได้จาก Configuration
- แสดง Import Progress
- แสดงผล Import รายไฟล์
- สร้าง Import Batch Number

ตัวอย่าง Batch Number:

```text
IMP-20260727-000001
```

---

## FR-002: Message Type Detection

ระบบต้องตรวจประเภทข้อความจากบรรทัดแรก

กฎ:

```text
FWB/{version} => FWB
FHL/{version} => FHL
```

ตัวอย่าง:

```text
FWB/16
FHL/4
```

ถ้าไม่พบรูปแบบที่รองรับ:

```text
Status = INVALID_FORMAT
Error Code = UNSUPPORTED_MESSAGE_TYPE
```

---

## FR-003: Raw Message Storage

ระบบต้องจัดเก็บ:

- Original Filename
- Original File Content
- Message Type
- Message Version
- File Size
- Import Time
- Imported By
- SHA-256 Hash
- Parsing Status
- Parsing Error
- Source Channel
- Import Batch ID

Source Channel:

```text
WEB_UPLOAD
PASTE_TEXT
API
SFTP
MESSAGE_QUEUE
```

---

## FR-004: FWB Parsing

ระบบต้อง Parse อย่างน้อย:

| Segment | Field |
|---|---|
| FWB | Message Version |
| Header line | MAWB Number |
| Header line | Origin |
| Header line | Destination |
| Header line | Pieces |
| Header line | Weight |
| FLT | Flight Number |
| FLT | Flight Date |
| RTG | Routing |
| SHP | Master Shipper |
| CNE | Master Consignee |
| AGT | Agent Code |
| AGT | Agent Name |
| CVD | Currency |
| CVD | Prepaid/Collect |
| RTD | Pieces |
| RTD | Gross Weight |
| RTD | Chargeable Weight |
| RTD | Rate |
| RTD | Total Freight |
| NG | Nature of Goods |
| OTH | Other Charges |
| PPD | Prepaid Charge |
| ISU | Issue Date |
| ISU | Issue Place |
| REF | Reference |
| SPH | Special Handling Codes |

---

## FR-005: FHL Parsing

ระบบต้อง Parse อย่างน้อย:

| Segment | Field |
|---|---|
| FHL | Message Version |
| MBI | MAWB Number |
| MBI | Origin |
| MBI | Destination |
| MBI | Master Pieces |
| MBI | Master Weight |
| HBS | HAWB Number |
| HBS | Origin |
| HBS | Destination |
| HBS | House Pieces |
| HBS | House Weight |
| HBS | Commodity |
| HTS | HS Code |
| OCI | Country |
| OCI | Party Type |
| OCI | Information Type |
| OCI | Tax ID |
| SHP | House Shipper |
| CNE | House Consignee |
| CNE | Postal Code |
| CNE | Telephone |

---

## FR-006: Data Normalization

ระบบต้อง Normalize ก่อน Match

### MAWB Number

รูปแบบมาตรฐาน:

```text
217-08722685
```

ระบบต้องรองรับ Input:

```text
21708722685
217-08722685
217 08722685
```

ผลลัพธ์หลัง Normalize:

```text
217-08722685
```

### Airport Code

- แปลงเป็นตัวพิมพ์ใหญ่
- ตัด Space
- ต้องมี 3 ตัวอักษร

### Weight Unit

รองรับอย่างน้อย:

```text
K = Kilogram
L = Pound
```

### Numeric Fields

- Remove comma
- Parse เป็น Decimal
- เก็บ Precision ตาม Configuration

### Text Fields

- Trim Space
- Normalize Line Break
- Preserve Raw Original Value
- สร้าง Normalized Value แยกต่างหาก

---

## FR-007: Duplicate Detection

ระบบต้องตรวจ Duplicate ด้วย:

```text
SHA-256(raw_message)
```

และ Business Key:

### FWB Duplicate Key

```text
message_type + mawb_number + version + raw_message_hash
```

### FHL Duplicate Key

```text
message_type + mawb_number + hawb_number + version + raw_message_hash
```

สถานะ:

```text
DUPLICATE_EXACT
DUPLICATE_BUSINESS_KEY
NOT_DUPLICATE
```

---

## FR-008: Matching Engine

Primary Matching Key:

```text
FWB.MAWB_NUMBER = FHL.MAWB_NUMBER
```

Matching Flow:

```text
1. Parse Message
2. Normalize MAWB
3. Find related FWB/FHL
4. Group by MAWB
5. Aggregate FHL Pieces
6. Aggregate FHL Weight
7. Validate Route
8. Validate Duplicate HAWB
9. Calculate Match Score
10. Assign Match Status
11. Persist Result
```

---

## FR-009: Matching Rules

### Mandatory Rule

| Rule | Description |
|---|---|
| MAWB_MATCH | MAWB ต้องตรงกัน |

ถ้า MAWB ไม่ตรง ห้าม Match

### Validation Rules

| Rule Code | Description | Severity |
|---|---|---|
| ORIGIN_MATCH | Origin ต้องตรงกัน | Error |
| DESTINATION_MATCH | Destination ต้องตรงกัน | Error |
| PIECES_MATCH | ผลรวม FHL Pieces เท่ากับ FWB Pieces | Warning/Error |
| WEIGHT_MATCH | ผลรวม FHL Weight เท่ากับ FWB Weight | Warning/Error |
| WEIGHT_UNIT_MATCH | หน่วยน้ำหนักต้องตรงกัน | Error |
| DUPLICATE_HAWB | HAWB ห้ามซ้ำใน MAWB เดียวกัน | Error |
| VERSION_SUPPORTED | Version ต้องรองรับ | Error |
| HAWB_PRESENT | FHL ต้องมี HAWB | Error |
| MASTER_PRESENT | FHL ต้องอ้างอิง MAWB | Error |

---

## FR-010: Weight Tolerance

ระบบต้องตั้งค่า Weight Tolerance ได้

ตัวอย่าง:

```text
Absolute Tolerance = 0.5 KG
Percentage Tolerance = 0.5%
```

กฎ:

```text
difference = abs(fwb_weight - fhl_total_weight)
percentage = difference / fwb_weight * 100
```

ผลลัพธ์:

```text
MATCHED
MATCHED_WITH_TOLERANCE
WEIGHT_MISMATCH
```

---

## FR-011: Match Status

รองรับสถานะ:

| Status | Description |
|---|---|
| MATCHED | ข้อมูลตรงครบ |
| MATCHED_WITH_TOLERANCE | น้ำหนักต่างแต่ยังอยู่ในค่าที่ยอมรับ |
| PARTIAL_MATCH | MAWB ตรง แต่ Field สำคัญบางรายการไม่ตรง |
| WAITING_FOR_FHL | มี FWB แต่ยังไม่มี FHL |
| WAITING_FOR_FWB | มี FHL แต่ยังไม่มี FWB |
| MULTIPLE_HOUSES | มีหลาย FHL และอยู่ระหว่างตรวจผลรวม |
| DUPLICATE | พบข้อมูลซ้ำ |
| INVALID_FORMAT | รูปแบบไฟล์ไม่ถูกต้อง |
| PARSE_ERROR | Parse ไม่สำเร็จ |
| NEEDS_REVIEW | ต้องตรวจสอบโดยผู้ใช้ |
| RESOLVED | ผู้ใช้ตรวจสอบและยืนยันแล้ว |
| REJECTED | ไม่ผ่านกฎสำคัญ |

---

## FR-012: Match Score

Default Score:

| Rule | Score |
|---|---:|
| MAWB Match | 50 |
| Origin Match | 10 |
| Destination Match | 10 |
| Pieces Match | 15 |
| Weight Match | 15 |

ผลรวม:

```text
100
```

การแปลผล:

| Score | Status |
|---:|---|
| 100 | MATCHED |
| 90-99 | MATCHED_WITH_TOLERANCE |
| 70-89 | PARTIAL_MATCH |
| 50-69 | NEEDS_REVIEW |
| < 50 | UNMATCHED |

หมายเหตุ:

```text
ถ้า MAWB ไม่ตรง Match Score ต้องเป็น 0
```

---

## FR-013: Re-Matching

ระบบต้อง Re-Match อัตโนมัติเมื่อ:

- Import FWB ใหม่
- Import FHL ใหม่
- แก้ไข Parsed Data
- เปลี่ยน Matching Rule
- Resolve Duplicate
- Manual Link/Unlink

ระบบต้องเก็บ Match History ทุกครั้ง

---

## FR-014: Manual Match

Administrator สามารถ:

- เลือก FWB
- เลือก FHL
- Link FHL เข้ากับ FWB
- Unlink FHL
- ระบุเหตุผล
- Mark as Resolved

ระบบต้องเก็บ:

- User
- Date Time
- Before Value
- After Value
- Reason

---

## FR-015: Dashboard

Dashboard ต้องแสดง Summary Cards:

| Card | Description |
|---|---|
| Imported Today | จำนวนไฟล์ที่นำเข้าวันนี้ |
| Matched | จำนวน MAWB ที่ Match สำเร็จ |
| Waiting | จำนวนที่รอ FWB หรือ FHL |
| Partial Match | จำนวนรายการที่ข้อมูลไม่ตรง |
| Error | จำนวน Parse/Validation Error |
| Duplicate | จำนวนข้อความซ้ำ |

ผู้ใช้คลิก Card เพื่อ Filter ตารางได้

---

## FR-016: Match Result Table

Columns:

| Column |
|---|
| Status |
| MAWB Number |
| Airline Prefix |
| Route |
| Flight |
| FWB Version |
| FHL Count |
| HAWB Numbers |
| FWB Pieces |
| FHL Total Pieces |
| Piece Difference |
| FWB Weight |
| FHL Total Weight |
| Weight Difference |
| Match Score |
| Import Date |
| Last Matched At |
| Reviewed By |
| Actions |

Actions:

```text
View
Compare
Re-Match
Review
Export
View Raw
View History
```

---

## FR-017: Search and Filter

Search:

- MAWB
- HAWB
- Shipper
- Consignee
- Flight
- Filename
- Batch Number
- Reference Number

Filter:

- Status
- Message Type
- Import Date
- Airline Prefix
- Origin
- Destination
- Flight
- Version
- Duplicate
- Reviewed/Unreviewed

---

## FR-018: Match Detail Screen

หน้ารายละเอียดแบ่งเป็น Tab:

### Tab 1: Overview

แสดง:

- MAWB
- Route
- Flight
- Pieces
- Weight
- Commodity
- Match Status
- Match Score

### Tab 2: House List

Columns:

| HAWB | Shipper | Consignee | Commodity | Pieces | Weight | HS Code | Status |
|---|---|---|---|---:|---:|---|---|

### Tab 3: Comparison

| Validation Rule | FWB Value | FHL Aggregate | Difference | Result |
|---|---|---|---|---|

### Tab 4: Raw Message

- Raw FWB
- Raw FHL
- Copy Button
- Download Button
- Syntax Highlight

### Tab 5: Parsed Data

แสดง Parsed JSON

### Tab 6: History

แสดง:

- Import
- Parse
- Match
- Re-Match
- Manual Review
- Export

---

## FR-019: Export

รองรับ:

- CSV
- Excel
- JSON
- Raw Text Package

Export Filters ต้องตรงกับหน้าจอปัจจุบัน

Excel ควรมี Sheets:

```text
Summary
FWB
FHL
Validation Results
Errors
Audit Log
```

---

## FR-020: Audit Log

ต้องเก็บ Event อย่างน้อย:

```text
LOGIN
IMPORT_FILE
PARSE_MESSAGE
MATCH_MESSAGE
REMATCH_MESSAGE
MANUAL_MATCH
MANUAL_UNMATCH
MARK_REVIEWED
RESOLVE_ERROR
EXPORT_DATA
UPDATE_RULE
```

Audit Fields:

| Field |
|---|
| Event ID |
| Event Type |
| User |
| Timestamp |
| Entity Type |
| Entity ID |
| Before Value |
| After Value |
| Reason |
| IP Address |
| User Agent |

---

## 6. User Interface Design

## 6.1 Design Principles

- Modern
- Clean
- Easy to scan
- Minimal clicks
- Large clickable area
- Comfortable spacing
- Responsive
- Accessible
- Error shown at field level
- Do not use color as the only status indicator

---

## 6.2 Layout

Desktop Layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ Header: Logo | Search | Notification | User                 │
├───────────────┬─────────────────────────────────────────────┤
│ Sidebar       │ Main Content                                │
│               │                                             │
│ Dashboard     │ Summary Cards                               │
│ Import        │ Filter Bar                                  │
│ Match Result  │ Match Table                                 │
│ Errors        │                                             │
│ History       │                                             │
│ Settings      │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

---

## 6.3 Import Screen

Components:

```text
Import Mode Tabs:
- Upload Files
- Paste Text

Upload Area:
- Drag & Drop
- Browse Files
- Supported Format
- Maximum File Size

Import Queue:
- Filename
- Detected Type
- File Size
- Status
- Progress
- Error
- Remove

Buttons:
- Validate
- Import & Match
- Clear
```

---

## 6.4 Status Design

| Status | Icon | Visual |
|---|---|---|
| MATCHED | Check Circle | Success |
| MATCHED_WITH_TOLERANCE | Check + Info | Success/Info |
| PARTIAL_MATCH | Warning Triangle | Warning |
| WAITING_FOR_FWB | Clock | Pending |
| WAITING_FOR_FHL | Clock | Pending |
| DUPLICATE | Copy | Warning |
| INVALID_FORMAT | File X | Error |
| PARSE_ERROR | Bug/File Alert | Error |
| NEEDS_REVIEW | Eye | Review |

---

## 6.5 Example Table

| Status | MAWB | Route | FHL | Pieces | Weight | Score | Action |
|---|---|---|---:|---|---|---:|---|
| Matched | 217-08722685 | HKG-BKK | 1 | 1/1 | 149/149 KG | 100 | View |
| Partial | 217-08722686 | HKG-BKK | 2 | 8/10 | 320/400 KG | 75 | Review |
| Waiting FHL | 217-08722687 | HKG-BKK | 0 | 0/5 | 0/250 KG | 50 | View |
| Waiting FWB | 217-08722688 | HKG-BKK | 1 | 3/? | 120/? KG | 0 | View |

---

## 7. Example Match Result

### FWB

```json
{
  "messageType": "FWB",
  "version": "16",
  "mawbNumber": "217-08722685",
  "origin": "HKG",
  "destination": "BKK",
  "pieces": 1,
  "weight": 149.0,
  "weightUnit": "K",
  "flightNumber": "TG601",
  "flightDate": "16",
  "natureOfGoods": "CONSOL"
}
```

### FHL

```json
{
  "messageType": "FHL",
  "version": "4",
  "mawbNumber": "217-08722685",
  "hawbNumber": "WM26070003",
  "origin": "HKG",
  "destination": "BKK",
  "pieces": 1,
  "weight": 149.0,
  "weightUnit": "K",
  "commodity": "DRY BATTERY",
  "hsCode": "85061012",
  "consigneeTaxId": "0105531040228"
}
```

### Matching Result

```json
{
  "mawbNumber": "217-08722685",
  "status": "MATCHED",
  "score": 100,
  "fhlCount": 1,
  "fwbPieces": 1,
  "fhlTotalPieces": 1,
  "pieceDifference": 0,
  "fwbWeight": 149.0,
  "fhlTotalWeight": 149.0,
  "weightDifference": 0.0,
  "validationResults": [
    {
      "rule": "MAWB_MATCH",
      "result": "PASS"
    },
    {
      "rule": "ORIGIN_MATCH",
      "result": "PASS"
    },
    {
      "rule": "DESTINATION_MATCH",
      "result": "PASS"
    },
    {
      "rule": "PIECES_MATCH",
      "result": "PASS"
    },
    {
      "rule": "WEIGHT_MATCH",
      "result": "PASS"
    }
  ]
}
```

---

## 8. Data Model

## 8.1 import_batches

```sql
CREATE TABLE import_batches (
    id UUID PRIMARY KEY,
    batch_no VARCHAR(50) NOT NULL UNIQUE,
    imported_by UUID NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    source_channel VARCHAR(30) NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    success_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

---

## 8.2 cargo_messages

```sql
CREATE TABLE cargo_messages (
    id UUID PRIMARY KEY,
    batch_id UUID REFERENCES import_batches(id),
    message_type VARCHAR(10),
    message_version VARCHAR(10),
    original_filename VARCHAR(255),
    content_type VARCHAR(100),
    file_size BIGINT,
    source_channel VARCHAR(30),
    raw_message TEXT NOT NULL,
    message_hash VARCHAR(64) NOT NULL,
    parse_status VARCHAR(30) NOT NULL,
    parse_error_code VARCHAR(100),
    parse_error_message TEXT,
    imported_by UUID,
    imported_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Indexes:

```sql
CREATE INDEX idx_cargo_messages_hash
ON cargo_messages(message_hash);

CREATE INDEX idx_cargo_messages_type
ON cargo_messages(message_type);

CREATE INDEX idx_cargo_messages_imported_at
ON cargo_messages(imported_at);
```

---

## 8.3 fwb_master

```sql
CREATE TABLE fwb_master (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES cargo_messages(id),
    mawb_number VARCHAR(20) NOT NULL,
    airline_prefix VARCHAR(3),
    serial_number VARCHAR(8),
    origin VARCHAR(3),
    destination VARCHAR(3),
    pieces INTEGER,
    gross_weight NUMERIC(18,3),
    weight_unit VARCHAR(3),
    chargeable_weight NUMERIC(18,3),
    flight_number VARCHAR(20),
    flight_date VARCHAR(20),
    routing TEXT,
    shipper_name TEXT,
    shipper_address TEXT,
    shipper_country VARCHAR(3),
    consignee_name TEXT,
    consignee_address TEXT,
    consignee_country VARCHAR(3),
    agent_code VARCHAR(50),
    agent_name TEXT,
    currency VARCHAR(3),
    payment_type VARCHAR(20),
    rate NUMERIC(18,4),
    freight_charge NUMERIC(18,2),
    other_charge NUMERIC(18,2),
    total_charge NUMERIC(18,2),
    nature_of_goods TEXT,
    issue_date VARCHAR(30),
    issue_place VARCHAR(10),
    reference_number VARCHAR(100),
    special_handling_codes JSONB,
    parsed_data JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Indexes:

```sql
CREATE INDEX idx_fwb_mawb
ON fwb_master(mawb_number);

CREATE INDEX idx_fwb_route
ON fwb_master(origin, destination);
```

---

## 8.4 fhl_house

```sql
CREATE TABLE fhl_house (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES cargo_messages(id),
    mawb_number VARCHAR(20) NOT NULL,
    hawb_number VARCHAR(50) NOT NULL,
    origin VARCHAR(3),
    destination VARCHAR(3),
    pieces INTEGER,
    gross_weight NUMERIC(18,3),
    weight_unit VARCHAR(3),
    commodity TEXT,
    hs_code VARCHAR(30),
    customs_country VARCHAR(3),
    customs_party_type VARCHAR(20),
    customs_info_type VARCHAR(20),
    consignee_tax_id VARCHAR(100),
    shipper_name TEXT,
    shipper_address TEXT,
    shipper_city VARCHAR(100),
    shipper_country VARCHAR(3),
    shipper_postal_code VARCHAR(30),
    consignee_name TEXT,
    consignee_address TEXT,
    consignee_city VARCHAR(100),
    consignee_country VARCHAR(3),
    consignee_postal_code VARCHAR(30),
    consignee_phone VARCHAR(50),
    parsed_data JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (mawb_number, hawb_number, message_id)
);
```

Indexes:

```sql
CREATE INDEX idx_fhl_mawb
ON fhl_house(mawb_number);

CREATE INDEX idx_fhl_hawb
ON fhl_house(hawb_number);

CREATE INDEX idx_fhl_mawb_hawb
ON fhl_house(mawb_number, hawb_number);
```

---

## 8.5 matching_results

```sql
CREATE TABLE matching_results (
    id UUID PRIMARY KEY,
    mawb_number VARCHAR(20) NOT NULL UNIQUE,
    fwb_id UUID REFERENCES fwb_master(id),
    match_status VARCHAR(40) NOT NULL,
    match_score INTEGER NOT NULL DEFAULT 0,
    fhl_count INTEGER NOT NULL DEFAULT 0,
    fwb_pieces INTEGER,
    fhl_total_pieces INTEGER,
    pieces_difference INTEGER,
    fwb_weight NUMERIC(18,3),
    fhl_total_weight NUMERIC(18,3),
    weight_difference NUMERIC(18,3),
    weight_difference_percentage NUMERIC(18,6),
    origin_match BOOLEAN,
    destination_match BOOLEAN,
    pieces_match BOOLEAN,
    weight_match BOOLEAN,
    duplicate_hawb BOOLEAN,
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_by UUID,
    reviewed_at TIMESTAMP,
    review_note TEXT,
    last_matched_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

---

## 8.6 matching_result_houses

```sql
CREATE TABLE matching_result_houses (
    matching_result_id UUID NOT NULL REFERENCES matching_results(id),
    fhl_id UUID NOT NULL REFERENCES fhl_house(id),
    linked_by VARCHAR(20) NOT NULL,
    linked_by_user UUID,
    linked_at TIMESTAMP NOT NULL,
    PRIMARY KEY (matching_result_id, fhl_id)
);
```

`linked_by`:

```text
AUTO
MANUAL
```

---

## 8.7 validation_results

```sql
CREATE TABLE validation_results (
    id UUID PRIMARY KEY,
    matching_result_id UUID NOT NULL REFERENCES matching_results(id),
    rule_code VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    result VARCHAR(20) NOT NULL,
    fwb_value TEXT,
    fhl_value TEXT,
    difference_value TEXT,
    message TEXT,
    created_at TIMESTAMP NOT NULL
);
```

---

## 8.8 match_history

```sql
CREATE TABLE match_history (
    id UUID PRIMARY KEY,
    mawb_number VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    previous_status VARCHAR(40),
    new_status VARCHAR(40),
    previous_score INTEGER,
    new_score INTEGER,
    details JSONB,
    performed_by UUID,
    performed_at TIMESTAMP NOT NULL
);
```

---

## 8.9 audit_logs

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    user_id UUID,
    entity_type VARCHAR(50),
    entity_id UUID,
    before_value JSONB,
    after_value JSONB,
    reason TEXT,
    ip_address VARCHAR(100),
    user_agent TEXT,
    created_at TIMESTAMP NOT NULL
);
```

---

## 9. Parser Design

## 9.1 Parser Interface

```python
from typing import Protocol

class CargoImpParser(Protocol):
    def supports(self, message_type: str, version: str) -> bool:
        ...

    def parse(self, raw_message: str) -> dict:
        ...
```

Implementations:

```text
FwbV16Parser
FhlV4Parser
```

---

## 9.2 Parser Pipeline

```text
Raw Text
↓
Normalize Line Ending
↓
Remove Empty Leading/Trailing Lines
↓
Detect Message Type
↓
Detect Version
↓
Split Segments
↓
Parse Segment Fields
↓
Validate Required Fields
↓
Normalize Values
↓
Return Parsed Object
```

---

## 9.3 Parsing Error Structure

```json
{
  "code": "INVALID_MBI_SEGMENT",
  "message": "Unable to parse MBI segment",
  "lineNumber": 2,
  "segment": "MBI",
  "rawValue": "MBI/...",
  "severity": "ERROR"
}
```

---

## 10. Matching Algorithm

```python
from decimal import Decimal
from typing import Iterable

def match_fwb_fhl(
    fwb,
    fhl_list: Iterable,
    absolute_weight_tolerance: Decimal,
    percentage_weight_tolerance: Decimal,
):
    if fwb is None:
        return {
            "status": "WAITING_FOR_FWB",
            "score": 0,
        }

    fhl_list = list(fhl_list)

    if not fhl_list:
        return {
            "status": "WAITING_FOR_FHL",
            "score": 50,
        }

    total_pieces = sum(item.pieces or 0 for item in fhl_list)
    total_weight = sum(
        Decimal(str(item.gross_weight or 0))
        for item in fhl_list
    )

    origin_match = all(
        item.origin == fwb.origin
        for item in fhl_list
    )

    destination_match = all(
        item.destination == fwb.destination
        for item in fhl_list
    )

    pieces_match = total_pieces == fwb.pieces

    weight_difference = abs(
        Decimal(str(fwb.gross_weight)) - total_weight
    )

    weight_percentage = (
        weight_difference / Decimal(str(fwb.gross_weight)) * 100
        if fwb.gross_weight
        else Decimal("0")
    )

    weight_exact_match = weight_difference == Decimal("0")

    weight_within_tolerance = (
        weight_difference <= absolute_weight_tolerance
        or weight_percentage <= percentage_weight_tolerance
    )

    duplicate_hawb = (
        len({item.hawb_number for item in fhl_list})
        != len(fhl_list)
    )

    score = 50

    if origin_match:
        score += 10

    if destination_match:
        score += 10

    if pieces_match:
        score += 15

    if weight_exact_match:
        score += 15
    elif weight_within_tolerance:
        score += 10

    if duplicate_hawb:
        return {
            "status": "DUPLICATE",
            "score": score,
        }

    if (
        origin_match
        and destination_match
        and pieces_match
        and weight_exact_match
    ):
        status = "MATCHED"

    elif (
        origin_match
        and destination_match
        and pieces_match
        and weight_within_tolerance
    ):
        status = "MATCHED_WITH_TOLERANCE"

    elif score >= 70:
        status = "PARTIAL_MATCH"

    else:
        status = "NEEDS_REVIEW"

    return {
        "status": status,
        "score": score,
        "fhl_count": len(fhl_list),
        "fwb_pieces": fwb.pieces,
        "fhl_total_pieces": total_pieces,
        "pieces_difference": total_pieces - (fwb.pieces or 0),
        "fwb_weight": fwb.gross_weight,
        "fhl_total_weight": total_weight,
        "weight_difference": weight_difference,
        "weight_difference_percentage": weight_percentage,
        "origin_match": origin_match,
        "destination_match": destination_match,
        "pieces_match": pieces_match,
        "weight_match": weight_exact_match,
        "duplicate_hawb": duplicate_hawb,
    }
```

---

## 11. API Design

Base Path:

```text
/api/v1
```

---

## 11.1 Import Files

```http
POST /api/v1/imports/files
Content-Type: multipart/form-data
```

Request:

```text
files[]
sourceChannel=WEB_UPLOAD
autoMatch=true
```

Response:

```json
{
  "batchId": "uuid",
  "batchNo": "IMP-20260727-000001",
  "totalFiles": 2,
  "results": [
    {
      "filename": "fwb.txt",
      "messageType": "FWB",
      "status": "IMPORTED"
    },
    {
      "filename": "fhl.txt",
      "messageType": "FHL",
      "status": "IMPORTED"
    }
  ]
}
```

---

## 11.2 Import Raw Text

```http
POST /api/v1/imports/text
Content-Type: application/json
```

Request:

```json
{
  "rawMessage": "FWB/16\n...",
  "autoMatch": true
}
```

---

## 11.3 Get Import Batch

```http
GET /api/v1/imports/{batchId}
```

---

## 11.4 List Match Results

```http
GET /api/v1/matches
```

Query Parameters:

```text
page
pageSize
search
status
origin
destination
airlinePrefix
dateFrom
dateTo
reviewed
sortBy
sortDirection
```

---

## 11.5 Get Match Detail

```http
GET /api/v1/matches/{mawbNumber}
```

---

## 11.6 Re-Match

```http
POST /api/v1/matches/{mawbNumber}/rematch
```

---

## 11.7 Mark Reviewed

```http
POST /api/v1/matches/{mawbNumber}/review
Content-Type: application/json
```

Request:

```json
{
  "reviewed": true,
  "note": "Verified by operation team"
}
```

---

## 11.8 Manual Link

```http
POST /api/v1/matches/{mawbNumber}/houses/{fhlId}/link
```

Request:

```json
{
  "reason": "Manual correction approved"
}
```

---

## 11.9 Manual Unlink

```http
POST /api/v1/matches/{mawbNumber}/houses/{fhlId}/unlink
```

---

## 11.10 Raw Message

```http
GET /api/v1/messages/{messageId}/raw
```

---

## 11.11 Parsed Message

```http
GET /api/v1/messages/{messageId}/parsed
```

---

## 11.12 Export

```http
POST /api/v1/exports
```

Request:

```json
{
  "format": "XLSX",
  "filters": {
    "status": ["MATCHED", "PARTIAL_MATCH"],
    "dateFrom": "2026-07-01",
    "dateTo": "2026-07-31"
  }
}
```

---

## 12. Frontend Structure

Recommended:

```text
frontend/
├── app/
│   ├── dashboard/
│   ├── import/
│   ├── matches/
│   │   ├── page.tsx
│   │   └── [mawb]/
│   ├── errors/
│   ├── history/
│   └── settings/
├── components/
│   ├── layout/
│   ├── dashboard/
│   ├── import/
│   ├── match-table/
│   ├── match-detail/
│   ├── status/
│   └── common/
├── services/
├── hooks/
├── types/
├── utils/
└── tests/
```

---

## 13. Backend Structure

Recommended:

```text
backend/
├── app/
│   ├── api/
│   ├── auth/
│   ├── config/
│   ├── database/
│   ├── import_service/
│   ├── parser/
│   │   ├── base.py
│   │   ├── detector.py
│   │   ├── fwb_v16.py
│   │   └── fhl_v4.py
│   ├── matching/
│   │   ├── engine.py
│   │   ├── rules.py
│   │   ├── scoring.py
│   │   └── tolerance.py
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   └── audit/
├── migrations/
├── tests/
│   ├── parser/
│   ├── matching/
│   ├── api/
│   └── integration/
└── main.py
```

---

## 14. Recommended Technology Stack

### Frontend

```text
Next.js
TypeScript
Tailwind CSS
shadcn/ui
TanStack Table
TanStack Query
React Hook Form
Zod
```

### Backend

Option A:

```text
Python
FastAPI
SQLAlchemy
Alembic
Pydantic
```

Option B:

```text
Java
Spring Boot
Spring Data JPA
Flyway
```

### Database

```text
PostgreSQL
```

### File Storage

Initial:

```text
PostgreSQL TEXT
```

Scale-up:

```text
S3 Compatible Object Storage
```

### Queue

Initial:

```text
Synchronous Processing
```

Scale-up:

```text
RabbitMQ
Kafka
```

### Authentication

```text
OIDC
OAuth 2.0
Keycloak
Microsoft Entra ID
```

---

## 15. Non-Functional Requirements

## NFR-001: Performance

- Import ไฟล์เดี่ยวไม่เกิน 2 วินาทีในภาวะปกติ
- Import 1,000 ไฟล์ต่อ Batch ได้
- ตารางต้องรองรับข้อมูลอย่างน้อย 100,000 Match Results
- API List ต้องรองรับ Pagination
- ใช้ Server-Side Filtering และ Sorting

## NFR-002: Availability

เป้าหมายเริ่มต้น:

```text
99.5%
```

## NFR-003: Security

- HTTPS เท่านั้น
- Role-Based Access Control
- Validate File Type
- Validate File Size
- Antivirus Scan Hook
- Prevent Path Traversal
- Sanitize Filename
- Encrypt Data at Rest
- Audit Log
- Sensitive Data Masking
- Rate Limiting
- CSRF Protection ตาม Framework
- Secure Headers

## NFR-004: Data Integrity

- ใช้ Database Transaction
- Unique Constraint
- Message Hash
- Idempotent Import
- Immutable Raw Message
- Match History
- Audit Log

## NFR-005: Observability

- Structured Log
- Request ID
- Batch ID
- Message ID
- MAWB Number
- Metrics
- Health Check
- Error Tracking

Endpoints:

```text
/health/live
/health/ready
/metrics
```

## NFR-006: Maintainability

- Parser แยกตาม Message Type และ Version
- Matching Rule Configurable
- Unit Test Coverage อย่างน้อย 80% ใน Parser และ Matching Engine
- OpenAPI Documentation
- Database Migration
- CI/CD Pipeline

---

## 16. Validation Error Codes

| Code | Description |
|---|---|
| EMPTY_FILE | ไฟล์ว่าง |
| UNSUPPORTED_FILE_TYPE | ประเภทไฟล์ไม่รองรับ |
| FILE_TOO_LARGE | ไฟล์ใหญ่เกินกำหนด |
| UNSUPPORTED_MESSAGE_TYPE | ไม่ใช่ FWB/FHL |
| UNSUPPORTED_VERSION | Version ไม่รองรับ |
| INVALID_HEADER | Header ไม่ถูกต้อง |
| INVALID_MAWB | MAWB ไม่ถูกต้อง |
| INVALID_MBI_SEGMENT | MBI ไม่ถูกต้อง |
| INVALID_HBS_SEGMENT | HBS ไม่ถูกต้อง |
| MISSING_MAWB | ไม่พบ MAWB |
| MISSING_HAWB | ไม่พบ HAWB |
| INVALID_ORIGIN | Origin ไม่ถูกต้อง |
| INVALID_DESTINATION | Destination ไม่ถูกต้อง |
| INVALID_WEIGHT | Weight ไม่ถูกต้อง |
| INVALID_PIECES | Pieces ไม่ถูกต้อง |
| DUPLICATE_MESSAGE | ข้อความซ้ำ |
| DUPLICATE_HAWB | HAWB ซ้ำ |
| INTERNAL_PARSE_ERROR | Parser Error |
| MATCHING_ERROR | Matching Engine Error |

---

## 17. Acceptance Criteria

## AC-001: Import FWB

Given:

```text
ไฟล์ขึ้นต้นด้วย FWB/16
```

When:

```text
ผู้ใช้ Upload ไฟล์
```

Then:

```text
ระบบตรวจพบ Message Type = FWB
ระบบ Parse MAWB ได้
ระบบจัดเก็บ Raw Message
ระบบแสดง Import Success
```

---

## AC-002: Import FHL

Given:

```text
ไฟล์ขึ้นต้นด้วย FHL/4
```

When:

```text
ผู้ใช้ Upload ไฟล์
```

Then:

```text
ระบบตรวจพบ Message Type = FHL
ระบบ Parse MAWB และ HAWB ได้
ระบบจัดเก็บ Raw Message
ระบบแสดง Import Success
```

---

## AC-003: Match One-to-One

Given:

```text
FWB MAWB = 217-08722685
FHL MBI  = 217-08722685
Pieces   = 1 เท่ากัน
Weight   = 149.0 เท่ากัน
Route    = HKG-BKK เท่ากัน
```

Then:

```text
Status = MATCHED
Score = 100
```

---

## AC-004: Match One-to-Many

Given:

```text
FWB Pieces = 10
FWB Weight = 400 KG
```

และมี FHL:

```text
FHL A = 3 Pieces / 100 KG
FHL B = 2 Pieces / 80 KG
FHL C = 5 Pieces / 220 KG
```

Then:

```text
FHL Total Pieces = 10
FHL Total Weight = 400 KG
Status = MATCHED
```

---

## AC-005: Waiting for FWB

Given:

```text
มี FHL แต่ไม่มี FWB ที่ MAWB ตรงกัน
```

Then:

```text
Status = WAITING_FOR_FWB
```

---

## AC-006: Waiting for FHL

Given:

```text
มี FWB แต่ไม่มี FHL
```

Then:

```text
Status = WAITING_FOR_FHL
```

---

## AC-007: Partial Match

Given:

```text
MAWB และ Route ตรง
Pieces ไม่ตรง
Weight ไม่ตรง
```

Then:

```text
Status = PARTIAL_MATCH หรือ NEEDS_REVIEW
Validation Result ต้องระบุ Difference
```

---

## AC-008: Duplicate

Given:

```text
Upload Raw Message เดิมซ้ำ
```

Then:

```text
ระบบต้องตรวจพบ SHA-256 เดิม
Status = DUPLICATE
ระบบต้องไม่สร้าง Parsed Record ซ้ำโดยไม่จำเป็น
```

---

## AC-009: Re-Match

Given:

```text
FWB เข้ามาก่อน
Status = WAITING_FOR_FHL
```

When:

```text
FHL ที่ MAWB ตรงกันถูก Import
```

Then:

```text
ระบบต้อง Re-Match อัตโนมัติ
Status เปลี่ยนตามผลตรวจ
Match History ต้องถูกสร้าง
```

---

## AC-010: Manual Review

When:

```text
Operator Mark as Reviewed
```

Then:

```text
ระบบเก็บ Reviewer
ระบบเก็บ Reviewed Time
ระบบเก็บ Note
ระบบสร้าง Audit Log
```

---

## 18. Test Cases

### Test Case 1: Exact Match

Input:

```text
FWB Pieces = 1
FWB Weight = 149
FHL Pieces = 1
FHL Weight = 149
```

Expected:

```text
MATCHED
Score = 100
```

### Test Case 2: Weight Tolerance

Input:

```text
FWB Weight = 149
FHL Weight = 148.8
Tolerance = 0.5 KG
```

Expected:

```text
MATCHED_WITH_TOLERANCE
```

### Test Case 3: Weight Mismatch

Input:

```text
FWB Weight = 149
FHL Weight = 140
```

Expected:

```text
PARTIAL_MATCH
WEIGHT_MATCH = FAIL
```

### Test Case 4: Duplicate HAWB

Input:

```text
MAWB = 217-08722685
HAWB = WM26070003
HAWB = WM26070003
```

Expected:

```text
DUPLICATE
DUPLICATE_HAWB = FAIL
```

### Test Case 5: Wrong Route

Input:

```text
FWB = HKG-BKK
FHL = HKG-SIN
```

Expected:

```text
PARTIAL_MATCH หรือ REJECTED
DESTINATION_MATCH = FAIL
```

### Test Case 6: Invalid File

Input:

```text
HELLO WORLD
```

Expected:

```text
INVALID_FORMAT
UNSUPPORTED_MESSAGE_TYPE
```

---

## 19. Seed Data

### FWB Seed

```text
FWB/16
217-08722685HKGBKK/T1K149.0
FLT/TG601/16
RTG/BKKTG
SHP
/WM LOGISTICS WORLDWIDE LIMITED
/58 66 TAI LIN PAI ROAD KWAI CHUNG
/HONG KONG
/HK
CNE
/PLANET INTER LOGISTICS CO LTD
/2 59 60 BANGNA COMPLEX OFFICE TOWER
/BANGKOK
/TH
AGT//1316077
/NARITA EXPRESS HK LTD
/HONG KONG
CVD/HKD/PP/PP/NVD/NCV/XXX
RTD/1/P1/K149.0/CQ/W149.0/R10.76/T1603.240
/NG/CONSOL
/2/NV/MC0.44
/3/ND//NDA
OTH/P/AWC13MCC250.4MYC223.5
PPD/WT1603.24
/OC486.9/CT2090.14
ISU/16JUL26/HKG
REF/HKGFMCR
SPH/HEA/SPX
```

### FHL Seed

```text
FHL/4
MBI/217-08722685HKGBKK/T1K149.0
HBS/WM26070003/HKGBKK/1/K149.0//DRY BATTERY
HTS/85061012
OCI/TH/CNE/T/TAX 0105531040228
SHP/HARMONY ENTERPRISE COMPNAY LIMITED
/9F AMTEL BUILDING 148 DES VOEUX ROA
/HONG KONG
/HK/999077
CNE/SEIKO PRECISION THAILAND CO LTD
/NAVANAKORN INDUSTRIAL ESTATE ZONE 3
/PATHUMTHANI
/TH/12120/TE/66252921626
```

Expected Result:

```json
{
  "mawbNumber": "217-08722685",
  "hawbNumber": "WM26070003",
  "status": "MATCHED",
  "score": 100,
  "route": "HKG-BKK",
  "fwbPieces": 1,
  "fhlTotalPieces": 1,
  "fwbWeight": 149.0,
  "fhlTotalWeight": 149.0
}
```

---

## 20. Suggested Development Phases

## Phase 1: MVP

- File Upload
- Paste Text
- FWB/16 Parser
- FHL/4 Parser
- PostgreSQL
- Auto Match by MAWB
- Match Table
- Match Detail
- Basic Validation
- CSV Export

## Phase 2: Operation Features

- Multi-file Upload
- Excel Export
- Manual Review
- Audit Log
- Duplicate Management
- Matching Rule Configuration
- Role-Based Access Control

## Phase 3: Integration

- REST API Inbound
- SFTP Polling
- Message Queue
- Event Notification
- External Cargo System Integration
- Cargo-XML Support

## Phase 4: Scale and Intelligence

- High-volume Asynchronous Processing
- Kafka
- Auto Error Classification
- Rule Recommendation
- Data Quality Dashboard
- Pattern Detection
- AI-assisted Exception Review

---

## 21. Definition of Done

Feature ถือว่าเสร็จเมื่อ:

- Code ผ่าน Review
- Unit Test ผ่าน
- Integration Test ผ่าน
- API Documentation อัปเดต
- Database Migration พร้อม
- Error Handling ครบ
- Audit Log ครบ
- UI รองรับ Loading, Empty, Error และ Success State
- Security Check ผ่าน
- Acceptance Criteria ผ่าน
- สามารถใช้ Seed FWB/FHL แล้วได้ผล `MATCHED`

---

## 22. Codex Implementation Instruction

ให้ Codex สร้างระบบตามลำดับ:

```text
1. สร้าง Monorepo
2. สร้าง PostgreSQL Schema
3. สร้าง Backend API
4. สร้าง FWB/16 Parser
5. สร้าง FHL/4 Parser
6. สร้าง Normalization Service
7. สร้าง Matching Engine
8. สร้าง Validation Engine
9. สร้าง Import API
10. สร้าง Match Query API
11. สร้าง Next.js Frontend
12. สร้าง Import Screen
13. สร้าง Dashboard
14. สร้าง Match Result Table
15. สร้าง Match Detail Screen
16. สร้าง Unit Tests
17. สร้าง Docker Compose
18. สร้าง README
```

### Mandatory Engineering Rules

- ใช้ TypeScript แบบ Strict
- ใช้ Python Type Hints หากเลือก FastAPI
- ห้ามเก็บ Business Logic ใน Controller
- Parser ต้องแยกตาม Message Version
- Raw Message ต้อง Immutable
- Import ต้อง Idempotent
- Matching Engine ต้องเขียน Unit Test
- ห้าม Match ถ้า MAWB ไม่ตรง
- ต้องรองรับ FHL มากกว่า 1 รายการต่อ FWB
- ใช้ Decimal สำหรับ Weight และ Charge
- ทุก API ต้องมี Validation และ Error Response มาตรฐาน
- ทุก List API ต้องมี Pagination
- ทุก Write Action ต้องมี Audit Log

### Recommended Initial Stack

```text
Frontend:
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Table
- TanStack Query

Backend:
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

Database:
- PostgreSQL

Development:
- Docker Compose
- Pytest
- Playwright
```

---

## 23. Standard API Error Response

```json
{
  "timestamp": "2026-07-27T15:30:00+07:00",
  "status": 400,
  "code": "INVALID_MBI_SEGMENT",
  "message": "Unable to parse MBI segment",
  "details": {
    "lineNumber": 2,
    "segment": "MBI",
    "rawValue": "MBI/..."
  },
  "requestId": "uuid"
}
```

---

## 24. Future Message Types

ออกแบบให้เพิ่ม Message Type ได้ในอนาคต:

```text
FSU
FFM
FMA
FNA
XFWB
XFHL
```

ตัวอย่าง Registry:

```python
PARSER_REGISTRY = {
    ("FWB", "16"): FwbV16Parser(),
    ("FHL", "4"): FhlV4Parser(),
}
```

เมื่อเพิ่ม Version ใหม่:

```python
PARSER_REGISTRY[("FWB", "17")] = FwbV17Parser()
```

โดยไม่กระทบ Parser เดิม
