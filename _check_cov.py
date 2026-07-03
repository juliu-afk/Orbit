"""Check coverage for target route files."""
import subprocess
import sys

files = [
    "src/orbit/api/routes/goal.py",
    "src/orbit/api/routes/observability.py",
    "src/orbit/api/routes/sessions.py",
    "src/orbit/api/routes/review.py",
    "src/orbit/api/routes/search_routes.py",
    "src/orbit/api/routes/terminal_routes.py",
    "src/orbit/api/routes/dream.py",
]

cmd = [
    sys.executable, "-m", "coverage", "report",
    "--include=" + ",".join(files),
    "--show-missing",
]
subprocess.run(cmd, cwd="d:/Orbit")
