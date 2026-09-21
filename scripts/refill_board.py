"""Refill hosted board after rebuild — one email per /api/demo/seed call."""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "https://harbormaster-1.vercel.app"


def post(path: str, body: dict, timeout: int = 90) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def board() -> dict:
    with urllib.request.urlopen(BASE + "/api/board", timeout=90) as r:
        return json.loads(r.read())


def main() -> None:
    b = board()
    print("start", b.get("counts"), "runs", len(b.get("runs") or []), flush=True)
    fails = 0
    n = 0
    while True:
        b = board()
        runs = len(b.get("runs") or [])
        if runs >= 520:
            print("complete", b.get("counts"), flush=True)
            break
        try:
            seed = post("/api/demo/seed", {"use_ai": False}, timeout=55)
            queued = seed.get("queued") or 0
            have = seed.get("have")
            n += 1
            fails = 0
            print(
                f"fill #{n} have={have} queued={queued} counts={b.get('counts')}",
                flush=True,
            )
            if queued == 0 and have and have >= 520:
                break
            time.sleep(0.15)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("seed err", fails, exc, flush=True)
            if fails >= 20:
                print("abort", flush=True)
                break
            time.sleep(min(30, 1.5 * fails))
    b = board()
    print("final", b.get("counts"), "runs", len(b.get("runs") or []), flush=True)


if __name__ == "__main__":
    main()
