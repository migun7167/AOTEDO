#!/bin/bash
# Paperless AOT — ตัวติดตั้งสำหรับ macOS
# ดับเบิลคลิกไฟล์นี้ใน Finder หรือรัน ./install-mac.command จาก Terminal
set -uo pipefail

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YEL=$'\033[33m'; OFF=$'\033[0m'

say()  { printf "%s\n" "$*"; }
ok()   { printf "${GREEN}✓${OFF} %s\n" "$*"; }
warn() { printf "${YEL}!${OFF} %s\n" "$*"; }
die()  { printf "${RED}✗ %s${OFF}\n" "$*"; printf "\nกด Enter เพื่อปิดหน้าต่างนี้"; read -r _; exit 1; }

say ""
say "${BOLD}╭──────────────────────────────────────────────╮${OFF}"
say "${BOLD}│   Paperless AOT — ติดตั้งบน macOS            │${OFF}"
say "${BOLD}╰──────────────────────────────────────────────╯${OFF}"
say ""
say "โฟลเดอร์: $ROOT"
say ""

# ---------------------------------------------------------------- Python ---
say "${BOLD}[1/4] ตรวจหา Python 3${OFF}"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || continue
    major="${version%%.*}"; minor="${version##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]; then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  say ""
  die "ไม่พบ Python 3.9 ขึ้นไปในเครื่อง

ติดตั้งด้วยวิธีใดวิธีหนึ่ง แล้วรันไฟล์นี้ใหม่:

  • Homebrew (แนะนำ):   brew install python@3.12
  • ดาวน์โหลดตัวติดตั้ง:  https://www.python.org/downloads/macos/
  • Xcode CLT:          xcode-select --install"
fi

PYVER="$("$PY" -c 'import sys; print(sys.version.split()[0])')"
ok "พบ $PY (เวอร์ชัน $PYVER)"
say ""

# ------------------------------------------------------------------ venv ---
say "${BOLD}[2/4] สร้าง virtual environment (.venv)${OFF}"
say "    ใช้ venv เพื่อไม่ให้ไปยุ่งกับ Python ของระบบ"

if [ -d "$ROOT/.venv" ]; then
  warn "มี .venv อยู่แล้ว — ใช้ตัวเดิม (ลบโฟลเดอร์ .venv ถ้าอยากติดตั้งใหม่หมด)"
else
  "$PY" -m venv "$ROOT/.venv" || die "สร้าง virtual environment ไม่สำเร็จ"
  ok "สร้าง .venv แล้ว"
fi

VENV_PY="$ROOT/.venv/bin/python"
[ -x "$VENV_PY" ] || die "ไม่พบ $VENV_PY"
say ""

# -------------------------------------------------------------- packages ---
say "${BOLD}[3/4] ติดตั้ง dependency${OFF}"
say "    fastapi, uvicorn, pydantic, openpyxl … (ใช้เน็ตครั้งเดียวตอนติดตั้ง)"
say ""

"$VENV_PY" -m pip install --upgrade pip --quiet 2>/dev/null
if ! "$VENV_PY" -m pip install -r "$ROOT/backend/requirements.txt"; then
  say ""
  die "ติดตั้ง dependency ไม่สำเร็จ

สาเหตุที่พบบ่อย:
  • เครื่องต่ออินเทอร์เน็ตไม่ได้ หรือติด proxy ขององค์กร
  • ถ้าอยู่หลัง proxy ให้ตั้งค่าก่อน:
      export HTTPS_PROXY=http://proxy.company:8080
    แล้วรันไฟล์นี้ใหม่"
fi
say ""
ok "ติดตั้ง dependency ครบแล้ว"
say ""

# ------------------------------------------------------------------ seed ---
say "${BOLD}[4/4] เตรียมฐานข้อมูลตัวอย่าง${OFF}"

if [ -f "$ROOT/data/paperless_aot.db" ]; then
  warn "มีฐานข้อมูลอยู่แล้วที่ data/paperless_aot.db — ข้ามขั้นตอนนี้"
  say "    (ถ้าอยากเริ่มใหม่: ลบไฟล์นั้นแล้วรัน install-mac.command อีกครั้ง)"
else
  "$VENV_PY" "$ROOT/scripts/seed.py" || die "โหลดข้อมูลตัวอย่างไม่สำเร็จ"
fi
say ""

chmod +x "$ROOT/start-mac.command" "$ROOT/run.sh" 2>/dev/null

# Files extracted from a downloaded zip carry com.apple.quarantine, which makes
# macOS 15 refuse to launch them on double-click. Getting this far means the
# user already cleared it for this script, so clear it for the rest of the
# folder and start-mac.command opens normally from Finder.
if xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null; then
  ok "ปลดล็อก Gatekeeper ให้ไฟล์ในโฟลเดอร์นี้แล้ว — start-mac.command ดับเบิลคลิกได้เลย"
  say ""
fi

say "${GREEN}${BOLD}╭──────────────────────────────────────────────╮${OFF}"
say "${GREEN}${BOLD}│   ติดตั้งเสร็จแล้ว                            │${OFF}"
say "${GREEN}${BOLD}╰──────────────────────────────────────────────╯${OFF}"
say ""
say "เปิดใช้งาน: ${BOLD}ดับเบิลคลิกไฟล์ start-mac.command${OFF}"
say "แล้วเบราว์เซอร์จะเปิดหน้า http://127.0.0.1:8000 ให้เอง"
say ""
say "บัญชีเข้าระบบ:"
say "  admin    / admin123      (ทำได้ทุกอย่าง)"
say "  operator / operator123   (import + review)"
say "  viewer   / viewer123     (ดูอย่างเดียว)"
say ""
printf "กด Enter เพื่อปิดหน้าต่างนี้"
read -r _
