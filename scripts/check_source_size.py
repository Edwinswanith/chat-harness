from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
EXTENSIONS = {".py", ".ts", ".tsx", ".css"}
files = [path for path in ROOT.rglob("*") if path.suffix in EXTENSIONS and "node_modules" not in path.parts]
oversized = [(path.relative_to(ROOT), len(path.read_text(encoding="utf-8").splitlines())) for path in files
             if len(path.read_text(encoding="utf-8").splitlines()) > 700]
if oversized:
    for path, lines in oversized:
        print(f"{path}: {lines} lines", file=sys.stderr)
    raise SystemExit(1)
print(f"Checked {len(files)} source files; all are at most 700 lines.")
