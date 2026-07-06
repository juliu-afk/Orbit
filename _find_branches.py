"""Extract uncovered branches from coverage.json, group by function, show context."""
import json
import ast
import sys
from pathlib import Path

COV_PATH = "coverage.json"
SRC_ROOT = Path("src/orbit")

# Regenerate coverage if needed
import subprocess
print("Regenerating coverage...")
subprocess.run([
    sys.executable, "-m", "pytest", "tests/unit/", "tests/integration/",
    "--cov=src/orbit", "--cov-report=json", "-q"
], cwd="d:/Orbit", capture_output=True)

cov = json.load(open(f"d:/Orbit/{COV_PATH}"))

# Collect all files with their uncovered branch arcs
files_data = []
for filepath, data in cov["files"].items():
    s = data["summary"]
    if s["missing_branches"] == 0:
        continue
    if s["num_statements"] < 10:
        continue
    # Convert to relative path
    try:
        rel = Path(filepath).relative_to("d:/Orbit/src/orbit")
    except ValueError:
        continue
    files_data.append({
        "path": str(rel),
        "abspath": filepath,
        "missing_lines": set(s["missing_lines"]),
        "missing_branches": s["missing_branches"],
        "num_branches": s["num_branches"],
        "pct_br": s["percent_branches_covered"],
    })

# Sort by missing branches desc
files_data.sort(key=lambda x: -x["missing_branches"])

print(f"\n=== Top 50 modules by uncovered branches ===\n")
for i, f in enumerate(files_data[:50]):
    print(f"{i+1:3d}. {f['path']:55s}  br={f['pct_br']:5.1f}%  "
          f"({f['missing_branches']}/{f['num_branches']} uncovered)  "
          f"miss_lines={len(f['missing_lines'])}")

# For each top file, find which functions contain the missing lines
print(f"\n=== Top 10: functions with most missing branches ===\n")
for f in files_data[:10]:
    abspath = f["abspath"]
    if not Path(abspath).exists():
        continue
    source = Path(abspath).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        continue

    # Find all function/class definitions
    func_lines = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_lines[node.lineno] = node.name

    # Map missing lines to functions
    func_missed = {}
    for line in sorted(f["missing_lines"]):
        func_name = "module_level"
        for start, name in sorted(func_lines.items()):
            if line >= start:
                func_name = name
        func_missed.setdefault(func_name, []).append(line)

    short = f["path"]
    total_missed = sum(len(v) for v in func_missed.values())
    for func, lines in sorted(func_missed.items(), key=lambda x: -len(x[1])):
        line_range = f"{lines[0]}-{lines[-1]}" if len(lines) > 1 else str(lines[0])
        print(f"  {short}:{line_range}  {func}()  ({len(lines)} missed lines)")
    print()
