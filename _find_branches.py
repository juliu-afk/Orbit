"""Find uncovered branches and missing lines, group by function."""
import json
import ast
import sys
import subprocess
from pathlib import Path

print("Regenerating coverage...")
subprocess.run([
    sys.executable, "-m", "pytest", "tests/unit/", "tests/integration/",
    "--cov=src/orbit", "--cov-report=json", "-q"
], cwd="d:/Orbit", capture_output=True)

with open("coverage.json") as f:
    cov = json.load(f)

files_data = []
for abspath, data in cov["files"].items():
    s = data["summary"]
    if s["missing_branches"] == 0:
        continue
    if s["num_statements"] < 10:
        continue

    # file-level missing_lines is a LIST of ints
    missing_line_list = data.get("missing_lines", [])
    if not isinstance(missing_line_list, list):
        missing_line_list = []

    # Normalize path for display
    parts = abspath.replace("\\", "/").split("/")
    try:
        idx = parts.index("orbit")
        rel = "/".join(parts[idx:])
    except ValueError:
        rel = abspath

    files_data.append({
        "rel": rel,
        "abspath": abspath,
        "missing_lines": set(missing_line_list),
        "missing_branches": s["missing_branches"],
        "num_branches": s["num_branches"],
        "pct_br": s.get("percent_branches_covered", 0),
        "pct_ln": s.get("percent_covered", 0),
        "num_statements": s["num_statements"],
    })

files_data.sort(key=lambda x: -x["missing_branches"])

print(f"\n=== Top 50 modules by uncovered branches ===\n")
for i, f in enumerate(files_data[:50]):
    print(f"{i+1:3d}. {f['rel']:60s} br={f['pct_br']:5.1f}%  "
          f"({f['missing_branches']}/{f['num_branches']})  "
          f"ln={f['pct_ln']:.0f}%  lines={f['num_statements']}")

# For top modules, show which functions have missing lines
print(f"\n=== Top 15: functions with missing lines ===\n")
for f in files_data[:15]:
    if not Path(f["abspath"]).exists():
        continue
    source = Path(f["abspath"]).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        continue

    func_lines = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_lines[node.lineno] = node.name

    func_missed = {}
    for line in sorted(f["missing_lines"]):
        func_name = "module_level"
        for start, name in sorted(func_lines.items()):
            if line >= start:
                func_name = name
        func_missed.setdefault(func_name, []).append(line)

    short = f["rel"]
    for func, lines in sorted(func_missed.items(), key=lambda x: -len(x[1])):
        line_range = f"{lines[0]}-{lines[-1]}" if len(lines) > 1 else str(lines[0])
        print(f"  {short}:{line_range:12s} {func}()  ({len(lines)} lines)")
    print()
