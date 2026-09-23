#!/data/data/com.termux/files/usr/bin/bash
# Обёртка для notion_sync.py — логирование + автокоммит лога.
# Использование: ./notion_runner.sh pull_taskboard

set -e
cd "$(dirname "$0")/../../../../.."  # в корень репы

SCRIPT="honeycombs/personal/kurtoch/scripts/notion_sync.py"
LOG="honeycombs/personal/kurtoch/_logs/notion_sync.log"

if [ -z "$1" ]; then
  echo "Использование: $0 <command>"
  exit 1
fi

{
  echo ""
  echo "================================================================"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] notion_sync.py $1"
  echo "================================================================"
} >> "$LOG"

if python3 "$SCRIPT" "$@" 2>&1 | tee -a "$LOG" | sed 's/ntn_[A-Za-z0-9_]*/ntn_***REDACTED***/g'; then
  STATUS="OK"
else
  STATUS="FAIL"
fi

echo "" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] status: $STATUS" >> "$LOG"

git add "$LOG" 2>/dev/null || true
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "chore(kurtoch): notion_sync $1 [$STATUS] $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1 || true
  git pull --rebase origin main >/dev/null 2>&1 || true
  git push >/dev/null 2>&1 || true
  echo "📝 Лог закоммичен и запушен."
fi
