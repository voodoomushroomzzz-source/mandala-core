#!/data/data/com.termux/files/usr/bin/bash
# Обёртка для sync. Запуск: bash notion_runner.sh <command>

set -e

# Всегда работаем от абсолютного пути
REPO="/storage/emulated/0/mandala-core"
KURTOCH_REL="honeycombs/personal/kurtoch"
SCRIPTS="$REPO/$KURTOCH_REL/scripts"
LOG_REL="$KURTOCH_REL/_logs/notion_sync.log"

if [ -z "$1" ]; then
  echo "Использование: bash notion_runner.sh <command>"
  echo "  full_sync       — archive + push + логи + коммит"
  echo "  pull_taskboard  — выгрузка Notion"
  echo "  push_taskboard  — push в Notion"
  exit 1
fi

CMD="$1"
LOG_ABS="$REPO/$LOG_REL"

log_start() {
  {
    echo ""
    echo "================================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] runner: $CMD"
    echo "================================================================"
  } >> "$LOG_ABS"
}

filter_token() {
  sed 's/ntn_[A-Za-z0-9_]*/ntn_***REDACTED***/g'
}

cd "$SCRIPTS"

case "$CMD" in
  full_sync)
    log_start
    echo "[1/3] archive_done.py" | tee -a "$LOG_ABS"
    python3 archive_done.py 2>&1 | tee -a "$LOG_ABS" | filter_token
    echo "" | tee -a "$LOG_ABS"
    echo "[2/3] push_taskboard.py" | tee -a "$LOG_ABS"
    python3 push_taskboard.py 2>&1 | tee -a "$LOG_ABS" | filter_token
    echo "" | tee -a "$LOG_ABS"
    echo "[3/3] git commit + push" | tee -a "$LOG_ABS"
    cd "$REPO"
    git add "$KURTOCH_REL/taskboard.json" "$KURTOCH_REL/taskboard_archive.json" "$LOG_REL"
    if ! git diff --cached --quiet 2>/dev/null; then
      git commit -m "chore(kurtoch): full_sync $(date '+%Y-%m-%d %H:%M')" >/dev/null
      git pull --rebase origin main >/dev/null 2>&1 || true
      git push >/dev/null 2>&1 || true
      echo "✓ закоммичено и запушено"
    else
      echo "  нечего коммитить"
    fi
    ;;
  pull_taskboard)
    log_start
    python3 notion_sync.py pull_taskboard 2>&1 | tee -a "$LOG_ABS" | filter_token
    ;;
  push_taskboard)
    log_start
    python3 push_taskboard.py 2>&1 | tee -a "$LOG_ABS" | filter_token
    ;;
  *)
    log_start
    python3 notion_sync.py "$@" 2>&1 | tee -a "$LOG_ABS" | filter_token
    ;;
esac
