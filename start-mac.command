#!/bin/bash
# Paperless AOT — เปิดใช้งานระบบ (macOS)
# ดับเบิลคลิกไฟล์นี้ใน Finder แล้วเบราว์เซอร์จะเปิดให้เอง
# ปิดระบบด้วยการกด Control+C ในหน้าต่างนี้
set -uo pipefail

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; OFF=$'\033[0m'
die() { printf "${RED}✗ %s${OFF}\n" "$*"; printf "\nกด Enter เพื่อปิด"; read -r _; exit 1; }

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  die "ยังไม่ได้ติดตั้ง — ดับเบิลคลิก install-mac.command ก่อน"
fi
VENV_PY="$ROOT/.venv/bin/python"

# พอร์ตซ้ำ = มีอีก instance เปิดอยู่ ไม่ต้องเปิดซ้ำ
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  printf "${BOLD}พอร์ต %s ถูกใช้งานอยู่แล้ว${OFF} — เปิดเบราว์เซอร์ไปที่ระบบที่รันอยู่\n" "$PORT"
  open "http://${HOST}:${PORT}" 2>/dev/null
  printf "\nถ้าต้องการรันคนละพอร์ต ให้สั่งจาก Terminal:  PORT=8100 ./start-mac.command\n"
  printf "กด Enter เพื่อปิด"; read -r _; exit 0
fi

if [ ! -f "$ROOT/data/paperless_aot.db" ]; then
  printf "${BOLD}==> ฐานข้อมูลว่าง กำลังโหลดข้อมูลตัวอย่าง${OFF}\n"
  "$VENV_PY" "$ROOT/scripts/seed.py" || die "โหลดข้อมูลตัวอย่างไม่สำเร็จ"
fi

printf "\n${BOLD}╭──────────────────────────────────────────────╮${OFF}\n"
printf "${BOLD}│   Paperless AOT กำลังทำงาน                   │${OFF}\n"
printf "${BOLD}╰──────────────────────────────────────────────╯${OFF}\n\n"
printf "  ที่อยู่:  ${GREEN}${BOLD}http://%s:%s${OFF}\n" "$HOST" "$PORT"
printf "  บัญชี:   admin / admin123\n"
printf "  ปิดระบบ: กด ${BOLD}Control + C${OFF} ในหน้าต่างนี้\n\n"

# เปิดเบราว์เซอร์เมื่อ server พร้อมรับ request
(
  for _ in $(seq 1 40); do
    if curl -sf "http://${HOST}:${PORT}/health/ready" >/dev/null 2>&1; then
      open "http://${HOST}:${PORT}" 2>/dev/null
      exit 0
    fi
    sleep 0.5
  done
) &

cd "$ROOT/backend"
exec "$VENV_PY" -m uvicorn main:app --host "$HOST" --port "$PORT"
