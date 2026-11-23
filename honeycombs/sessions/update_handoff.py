"""Replace one chat's handoff in the shared file using an expected revision."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def revision(data):
    return hashlib.sha256(data).hexdigest()


def save(path, chat_id, expected, block):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", chat_id):
        raise ValueError("Invalid chat ID")
    if "title" in block and (not isinstance(block["title"], str) or not block["title"].strip()):
        raise ValueError("Expected a nonempty chat title")
    for field in ("role", "focus", "updated", "status", "result", "next_step"):
        if not isinstance(block.get(field), str) or not block[field].strip():
            raise ValueError(f"Missing field: {field}")
    for field in ("affects", "sources"):
        if not isinstance(block.get(field), list) or not all(isinstance(item, str) and item.strip() for item in block[field]):
            raise ValueError(f"Expected a list of strings: {field}")
    if not block["sources"] or block.get("mode") not in {"local", "external"}:
        raise ValueError("Expected sources and a valid mode")
    if block["status"] not in {"active", "paused", "cancelled"}:
        raise ValueError("Invalid handoff status")

    lock = path.with_suffix(".lock")
    candidate = path.with_suffix(".tmp")
    with lock.open("x"):
        pass
    try:
        original = path.read_bytes()
        if revision(original) != expected:
            raise ValueError("Handoffs changed. Read the latest revision before retrying.")
        document = json.loads(original)
        if document["schema_version"] != 1 or not isinstance(document["chats"], dict):
            raise ValueError("Unsupported handoff format")
        if document["chats"].get(chat_id) == block:
            return
        document["chats"][chat_id] = block
        candidate.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        os.replace(candidate, path)
    finally:
        candidate.unlink(missing_ok=True)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path(__file__).with_name("chat_handoffs.json"))
    parser.add_argument("--chat")
    parser.add_argument("--expect")
    args = parser.parse_args()
    try:
        if args.chat is None and args.expect is None:
            print(revision(args.file.read_bytes()))
        elif args.chat and args.expect:
            block = json.load(sys.stdin.buffer)
            if not isinstance(block, dict):
                raise ValueError("Expected a JSON object")
            save(args.file, args.chat, args.expect, block)
        else:
            parser.error("--chat and --expect must be supplied together")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
