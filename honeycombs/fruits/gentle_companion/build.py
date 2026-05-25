#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py — Gentle Companion module assembler
Phase 1: copies bot.py → bot_built.py (infrastructure ready, modules TBD)
Phase 2+: reads individual modules in build_order, concatenates into bot_built.py

Location: honeycombs/fruits/gentle_companion/build.py
Run from repo root: python honeycombs/fruits/gentle_companion/build.py
Output: bot_built.py (repo root)

Module migration status tracked in:
  honeycombs/fruits/gentle_companion/index.json
"""

import os
import sys
import ast
import hashlib
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
MODULE_DIR   = SCRIPT_DIR
BOT_SRC      = os.path.join(REPO_ROOT, "bot.py")
BOT_BUILT    = os.path.join(REPO_ROOT, "bot_built.py")

# ── Build order (matches index.json dependency_graph) ─────────────────────────
# Each entry: (module_file_relative_to_MODULE_DIR, phase, status)
# status: "ready" = use module file | "pending" = use slice from bot.py
BUILD_ORDER = [
    ("config.py",              2, "pending"),
    ("store.py",               3, "pending"),
    ("github_api.py",          2, "pending"),
    ("helpers.py",             3, "pending"),
    ("ui.py",                  4, "pending"),
    ("sr_prompts.py",          2, "pending"),
    ("sr_search.py",           2, "pending"),
    ("sr_context.py",          5, "pending"),
    ("sr_memory.py",           5, "pending"),
    ("handlers/tasks.py",      6, "pending"),
    ("handlers/features.py",   6, "pending"),
    ("handlers/system.py",     6, "pending"),
    ("sr_conversation.py",     5, "pending"),
    ("main.py",                7, "pending"),
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
        print(f"  ❌ Syntax error in {path}: {e}")
        return False


def build():
    print("=" * 60)
    print("  Gentle Companion — build.py")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Check which modules are ready ─────────────────────────────────────────
    ready_modules = []
    pending_modules = []
    for module_file, phase, status in BUILD_ORDER:
        full_path = os.path.join(MODULE_DIR, module_file)
        if os.path.exists(full_path) and status == "ready":
            ready_modules.append((module_file, full_path, phase))
        else:
            pending_modules.append((module_file, phase))

    print(f"\n  Ready modules:   {len(ready_modules)}")
    print(f"  Pending modules: {len(pending_modules)} (using bot.py)")
    print()

    # ── Phase 1: all modules pending → copy bot.py as-is ─────────────────────
    if not ready_modules:
        print("  Phase 1 mode: no modules extracted yet.")
        print(f"  Copying bot.py → bot_built.py")

        if not os.path.exists(BOT_SRC):
            print(f"  ❌ bot.py not found at: {BOT_SRC}")
            sys.exit(1)

        with open(BOT_SRC, encoding="utf-8") as f:
            src = f.read()

        # Inject build header after shebang
        header = (
            f"\n# ── BUILT by build.py ──────────────────────────────────────\n"
            f"# Built: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# Source: bot.py (monolith — Phase 1, no modules extracted yet)\n"
            f"# SHA256: {_sha256(src)}\n"
            f"# Phases complete: 1/7\n"
            f"# Next: Phase 2 — extract config.py, github_api.py, sr_prompts.py, sr_search.py\n"
            f"# ───────────────────────────────────────────────────────────\n"
        )

        # Insert after first line (shebang) if present
        lines = src.split("\n")
        if lines[0].startswith("#!"):
            output = lines[0] + "\n" + header + "\n".join(lines[1:])
        else:
            output = header + src

        with open(BOT_BUILT, "w", encoding="utf-8", newline="\n") as f:
            f.write(output)

        # Verify output syntax
        print(f"  Running syntax check on bot_built.py...")
        if not _syntax_check(BOT_BUILT):
            print("  ❌ Build FAILED — syntax error in output")
            sys.exit(1)

        src_sha = _sha256(src)
        built_size = os.path.getsize(BOT_BUILT)
        src_size   = os.path.getsize(BOT_SRC)

        print(f"\n  ✅ bot_built.py written")
        print(f"     Source:  {src_size:,} bytes  (SHA: {src_sha})")
        print(f"     Output:  {built_size:,} bytes  (+{built_size - src_size} header)")
        print(f"\n  Next step: switch systemd to bot_built.py")
        print(f"  Command:")
        print(f"    ssh root@91.99.149.226 \"sed -i 's|bot.py|bot_built.py|' /etc/systemd/system/mandala-bot.service && systemctl daemon-reload && systemctl restart mandala-bot\"")
        return

    # ── Phase 2+: assemble from ready modules + bot.py fallback ──────────────
    # (This branch activates when first modules are extracted)
    parts = []
    parts.append(
        f"#!/usr/bin/env python3\n"
        f"# -*- coding: utf-8 -*-\n"
        f"# ── BUILT by build.py ──────────────────────────────────────\n"
        f"# Built:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"# Modules: {len(ready_modules)} ready, {len(pending_modules)} pending\n"
        f"# ───────────────────────────────────────────────────────────\n"
    )

    for module_file, phase, status in BUILD_ORDER:
        full_path = os.path.join(MODULE_DIR, module_file)
        if os.path.exists(full_path) and status == "ready":
            print(f"  ✅ {module_file} (phase {phase})")
            with open(full_path, encoding="utf-8") as f:
                content = f.read()
            # Strip shebang from modules
            lines = content.split("\n")
            if lines[0].startswith("#!"):
                content = "\n".join(lines[1:])
            parts.append(f"\n# ── MODULE: {module_file} ──\n{content}\n")
        else:
            print(f"  ⏳ {module_file} (phase {phase}, pending)")

    if len(pending_modules) > 0:
        print(f"\n  ⚠️  {len(pending_modules)} modules still pending — cannot do partial build yet.")
        print(f"  Use Phase 1 mode (remove all module files) or complete all modules first.")
        sys.exit(1)

    output = "\n".join(parts)
    with open(BOT_BUILT, "w", encoding="utf-8", newline="\n") as f:
        f.write(output)

    print(f"\n  Running syntax check...")
    if not _syntax_check(BOT_BUILT):
        print("  ❌ Build FAILED")
        sys.exit(1)

    print(f"  ✅ bot_built.py assembled from {len(ready_modules)} modules")
    built_size = os.path.getsize(BOT_BUILT)
    print(f"     Output: {built_size:,} bytes")


if __name__ == "__main__":
    build()