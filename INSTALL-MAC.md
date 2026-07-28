# ติดตั้ง Paperless AOT บน Mac

ใช้เวลาประมาณ 2–3 นาที ต้องต่ออินเทอร์เน็ตเฉพาะตอนติดตั้งครั้งแรก
หลังจากนั้นใช้งานแบบออฟไลน์ได้ทั้งหมด

---

## ขั้นตอน

### 1. แตกไฟล์ zip

ดับเบิลคลิก `paperless-aot.zip` จะได้โฟลเดอร์ `paperless-aot`
ย้ายไปไว้ที่ไหนก็ได้ เช่น `Documents` หรือหน้า Desktop

### 2. ดับเบิลคลิก `install-mac.command`

macOS จะเปิดหน้าต่าง Terminal แล้วติดตั้งให้อัตโนมัติ (สร้าง `.venv`,
ลง dependency, โหลดข้อมูลตัวอย่าง) รอจนขึ้นข้อความ **"ติดตั้งเสร็จแล้ว"**

> **ถ้า macOS ขึ้นเตือนว่าเปิดไม่ได้** (เพราะไฟล์ดาวน์โหลดมาจากอินเทอร์เน็ต)
> ให้ **คลิกขวา** ที่ไฟล์ → เลือก **Open** → กด **Open** ยืนยันอีกครั้ง
> ทำแบบนี้ครั้งเดียวพอ ครั้งต่อไปดับเบิลคลิกได้ตามปกติ
>
> หรือสั่งจาก Terminal ทีเดียว (cd ไปที่โฟลเดอร์ก่อน):
> ```bash
> xattr -dr com.apple.quarantine .
> chmod +x install-mac.command start-mac.command run.sh
> ```

### 3. ดับเบิลคลิก `start-mac.command`

ระบบจะเริ่มทำงานและเปิดเบราว์เซอร์ไปที่ <http://127.0.0.1:8000> ให้เอง

เข้าระบบด้วย:

| Username | Password | สิทธิ์ |
|---|---|---|
| `admin` | `admin123` | ทำได้ทุกอย่าง |
| `operator` | `operator123` | import + review |
| `viewer` | `viewer123` | ดูอย่างเดียว |

**ปิดระบบ:** กด `Control + C` ในหน้าต่าง Terminal ที่เปิดอยู่ (หรือปิดหน้าต่างไป)

---

## ข้อกำหนดของเครื่อง

- macOS 12 (Monterey) ขึ้นไป — ใช้ได้ทั้ง Apple Silicon (M1/M2/M3/M4) และ Intel
- Python 3.9 ขึ้นไป

ตัวติดตั้งจะตรวจ Python ให้เอง ถ้าไม่พบจะบอกวิธีติดตั้ง สรุปคือ:

```bash
# วิธีที่แนะนำ ถ้ามี Homebrew อยู่แล้ว
brew install python@3.12
```

หรือดาวน์โหลดตัวติดตั้งจาก <https://www.python.org/downloads/macos/>

เช็กว่ามี Python อยู่แล้วหรือยัง:

```bash
python3 --version
```

---

## ปัญหาที่พบบ่อย

**"install-mac.command" cannot be opened because it is from an unidentified developer**
คลิกขวาที่ไฟล์ → Open → Open (ดูข้อ 2 ด้านบน)

**ติดตั้ง dependency ไม่ผ่าน / ค้างตอนดาวน์โหลด**
เครื่องน่าจะต่อเน็ตไม่ได้หรืออยู่หลัง proxy ขององค์กร ลองสั่งจาก Terminal:

```bash
cd /path/to/paperless-aot
export HTTPS_PROXY=http://proxy.company:8080     # แก้เป็น proxy จริง
./install-mac.command
```

**พอร์ต 8000 ถูกใช้งานอยู่**
`start-mac.command` จะแจ้งให้ทราบและเปิดเบราว์เซอร์ไปที่ระบบที่รันอยู่แทน
ถ้าอยากรันคนละพอร์ต สั่งจาก Terminal:

```bash
PORT=8100 ./start-mac.command
```

**อยากล้างข้อมูลแล้วเริ่มใหม่**

```bash
rm data/paperless_aot.db
./start-mac.command          # จะ seed ข้อมูลตัวอย่างให้ใหม่
```

**ถอนการติดตั้ง**
ลบโฟลเดอร์ทิ้งได้เลย ไม่มีไฟล์ไปวางที่อื่นในเครื่อง ทุกอย่างอยู่ในโฟลเดอร์นี้
(`.venv` คือ Python packages, `data/paperless_aot.db` คือฐานข้อมูล)

---

## ใช้งานผ่าน Terminal

ถ้าถนัด command line มากกว่า:

```bash
cd /path/to/paperless-aot

# ติดตั้ง
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python scripts/seed.py

# เปิดใช้งาน
./run.sh                     # run.sh จะหยิบ .venv ให้เองถ้ามี

# รัน test
.venv/bin/python -m pytest backend/tests/ -q
```

---

## นำเข้าไฟล์ของจริง

ไฟล์ตัวอย่างอยู่ใน `samples/` (ของจริง 4 ไฟล์) และ `samples/demo/` (ชุดสาธิต)
ลองลากไฟล์เหล่านี้เข้าไปในหน้า **Import** ได้เลย ระบบรองรับ `.txt`
ประเภท FWB, FHL, FFM และ FSU และตรวจประเภทให้เองจากบรรทัดแรก

รายละเอียดฟีเจอร์ทั้งหมดอ่านได้ใน [README.md](README.md)
