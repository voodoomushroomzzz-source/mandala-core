#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — Gentle Companion module assembler
Phase 7: all modules extracted, assembly from source files.

Location: honeycombs/fruits/gentle_companion/build.py
Run from repo root: python honeycombs/fruits/gentle_companion/build.py
Output: gentle_companion.py (repo root)
"""

import os
import sys
import ast
import hashlib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
MODULE_DIR  = SCRIPT_DIR
BOT_SRC     = os.path.join(REPO_ROOT, "bot.py")
BOT_BUILT   = os.path.join(REPO_ROOT, "gentle_companion.py")

# Build order — all "ready"
BUILD_ORDER = [
    ("config.py",              2, "ready"),
    ("store.py",               3, "ready"),
    ("github_api.py",          2, "ready"),
    ("helpers.py",             3, "ready"),
    ("ui.py",                  4, "ready"),
    ("sr_prompts.py",          2, "ready"),
    ("sr_search.py",           2, "ready"),
    ("sr_context.py",          5, "ready"),
    ("sr_memory.py",           5, "ready"),
    ("handlers/tasks.py",      6, "ready"),
    ("handlers/features.py",   6, "ready"),
    ("handlers/system.py",     6, "ready"),
    ("sr_conversation.py",     5, "ready"),
    ("main.py",                7, "ready"),
]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _syntax_check(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        src = f.read()
    try:
        ast.parse(src)
        return True
    except SyntaxError as e:
        print(f"  ❌ Syntax error: {e}")
        return False


def _strip_shebang(content: str) -> str:
    lines = content.split("\n")
    if lines[0].startswith("#!"):
        return "\n".join(lines[1:])
    return content


def build():
    print("=" * 60)
    print("  Gentle Companion — build.py  Phase 7")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check all modules exist
    missing = []
    for module_file, phase, status in BUILD_ORDER:
        full_path = os.path.join(MODULE_DIR, module_file)
        if not os.path.exists(full_path):
            missing.append(module_file)

    if missing:
        print(f"\n  ❌ Missing modules:")
        for m in missing:
            print(f"     {m}")
        sys.exit(1)

    # Check for pending modules
    pending = [(f, p) for f, p, s in BUILD_ORDER if s == "pending"]
    if pending:
        print(f"\n  ⚠️  {len(pending)} modules still pending — falling back to Phase 1 mode")
        if not os.path.exists(BOT_SRC):
            print(f"  ❌ bot.py not found")
            sys.exit(1)
        with open(BOT_SRC, encoding="utf-8") as f:
            src = f.read()
        header = (
            f"\n# ── BUILT by build.py ──────────────────────────────────────\n"
            f"# Built: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# Source: bot.py (Phase 1 mode — pending modules)\n"
            f"# ───────────────────────────────────────────────────────────\n"
        )
        lines = src.split("\n")
        output = lines[0] + "\n" + header + "\n".join(lines[1:])
        with open(BOT_BUILT, "w", encoding="utf-8", newline="\n") as f:
            f.write(output)
        print(f"  ✅ gentle_companion.py written (Phase 1 mode)")
        return

    # Phase 7: assemble all modules
    print(f"\n  Assembling {len(BUILD_ORDER)} modules...\n")

    parts = [
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        f"# ── BUILT by build.py ── {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ──\n"
        f"# Phases complete: 7/7 — all modules assembled\n"
        "# ────────────────────────────────────────────────────────────\n"
    ]

    for module_file, phase, status in BUILD_ORDER:
        full_path = os.path.join(MODULE_DIR, module_file)
        with open(full_path, encoding="utf-8") as f:
            content = f.read()

        # Strip shebang + module docstring header (keep only code)
        content = _strip_shebang(content)

        # Strip module-level docstring (everything between first """ and """)
        stripped = content.lstrip("\n")
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            end = stripped.find(quote, 3)
            if end != -1:
                content = stripped[end+3:]

        parts.append(
            f"\n# {'─' * 55}\n"
            f"# MODULE: {module_file}  (Phase {phase})\n"
            f"# {'─' * 55}\n"
            + content.strip("\n") + "\n"
        )
        print(f"  ✅ {module_file}")

    output = "\n".join(parts)

    with open(BOT_BUILT, "w", encoding="utf-8", newline="\n") as f:
        f.write(output)

    print(f"\n  Running syntax check...")
    if not _syntax_check(BOT_BUILT):
        print("  ❌ Build FAILED")
        sys.exit(1)

    src_size   = os.path.getsize(BOT_SRC) if os.path.exists(BOT_SRC) else 0
    built_size = os.path.getsize(BOT_BUILT)
    built_sha  = _sha256(output)

    print(f"\n  ✅ gentle_companion.py assembled")
    print(f"     Modules: {len(BUILD_ORDER)}")
    print(f"     Output:  {built_size:,} bytes  (SHA: {built_sha})")
    if src_size:
        diff = built_size - src_size
        print(f"     vs bot.py: {src_size:,} bytes  (diff: {diff:+,})")
    print(f"\n  To switch server:")
    print(f'    ssh root@91.99.149.226 "sed -i \'s|bot.py|gentle_companion.py|\' /etc/systemd/system/mandala-bot.service && systemctl daemon-reload && systemctl restart mandala-bot"')


if __name__ == "__main__":
    build()