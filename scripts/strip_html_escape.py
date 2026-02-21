#!/usr/bin/env python3
"""Убирает HTML-escape (&amp;gt; &amp;lt; &amp;amp;) из файлов перед коммитом."""
import sys
from pathlib import Path

def strip_file(path: Path) -&gt; bool:
    text = path.read_text(encoding="utf-8")
    cleaned = text.replace("&amp;gt;", "&gt;").replace("&amp;lt;", "&lt;").replace("&amp;amp;", "&amp;")
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")
        print(f"[strip-html-escape] cleaned: {path}")
        return True
    return False

if __name__ == "__main__":
    changed = 0
    for file in sys.argv[1:]:
        if strip_file(Path(file)):
            changed += 1
    sys.exit(changed)  # 0 = success, &gt;0 = changed files