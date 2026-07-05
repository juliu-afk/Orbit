"""Build-time API smoke test — verify exe core endpoints work.

Usage: python scripts/smoke_test.py [--port 18888] [--timeout 30]
Exit code: 0=pass, 1=fail
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 18888
TIMEOUT = 30
EXIT = 0


def fail(msg: str) -> None:
    global EXIT
    print(f"  FAIL: {msg}")
    EXIT = 1


def ok(msg: str) -> None:
    print(f"  OK: {msg}")


async def _wait_ready(host: str, timeout: int) -> bool:
    """Poll startup-probe until 200 or timeout."""
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"http://{host}:{PORT}/api/v1/observability/startup-probe"
            resp = urllib.request.urlopen(url, timeout=5)
            if resp.status == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


async def _test_chat(host: str) -> bool:
    """WebSocket chat: send message, verify ChatterAgent responds with real content."""
    import websockets

    async with websockets.connect(f"ws://{host}:{PORT}/api/v1/chat") as ws:
        await ws.send(json.dumps({"type": "chat", "text": "hello"}))
        resp = json.loads(await ws.recv())
        if resp.get("code") != 0:
            return False
        data = resp.get("data", {})
        # Check response comes from an agent
        if data.get("type") not in ("chat", "clarify"):
            return False
        reply = data.get("reply", "")
        # Real LLM reply is >20 chars, fallback "sorry" msg is shorter
        if len(reply) < 10:
            return False
        return True


async def _test_health(host: str) -> bool:
    """Health endpoint returns 200."""
    import urllib.request

    url = f"http://{host}:{PORT}/api/v1/observability/health"
    resp = urllib.request.urlopen(url, timeout=10)
    return resp.status == 200


async def run_smoke(host: str = "127.0.0.1", timeout: int = TIMEOUT) -> bool:
    """Run all smoke tests. Returns True if all pass."""
    print("=== Orbit smoke test ===")
    print(f"Target: {host}:{PORT}")

    # 1. Startup probe
    print("\n1. Startup probe...")
    if await _wait_ready(host, timeout):
        ok("startup-probe OK")
    else:
        fail(f"startup-probe not ready after {timeout}s")
        return False

    # 2. Health check
    print("\n2. Health check...")
    try:
        if await _test_health(host):
            ok("health endpoint OK")
        else:
            fail("health endpoint failed")
    except Exception as e:
        fail(f"health endpoint: {e}")

    # 3. Chat WebSocket (ChatterAgent)
    print("\n3. Chat WebSocket...")
    try:
        if await _test_chat(host):
            ok("chat WS: ChatterAgent responds")
        else:
            fail("chat WS: response invalid (fallback/no-LLM reply)")
    except Exception as e:
        fail(f"chat WS: {e}")

    print(f"\n{'=' * 40}")
    if EXIT == 0:
        print("PASS: all smoke tests passed")
    else:
        print(f"FAIL: {EXIT} test(s) failed")
    return EXIT == 0


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=18888)
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    PORT = args.port
    success = asyncio.run(run_smoke(args.host, args.timeout))
    sys.exit(0 if success else 1)
