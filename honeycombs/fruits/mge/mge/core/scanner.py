"""Scanner: walk honeycombs/ and find all honeycombs."""
from pathlib import Path


def find_honeycombs(root: str = "honeycombs") -> list:
    result = []
    root_path = Path(root)
    if not root_path.exists():
        return result
    for entry in sorted(root_path.iterdir()):
        if entry.is_dir() and (entry / "index.json").exists():
            result.append(str(entry))
    return result
