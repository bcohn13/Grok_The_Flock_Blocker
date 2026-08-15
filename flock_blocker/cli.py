from __future__ import annotations

import argparse
import json

from flock_blocker.graph import run_turn
from flock_blocker.store import load_store


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grok the Flock Blocker — public ALPR awareness agents"
    )
    parser.add_argument("message", nargs="?", default="Find publicly mapped ALPR cameras near San Francisco")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--radius", type=int, default=None)
    args = parser.parse_args()
    load_store()
    result = run_turn(args.message, lat=args.lat, lon=args.lon, radius_meters=args.radius)
    print(result["response"])
    print("\nagents:", ", ".join(result["agent_trace"]) or "(none)")
    if result["alerts"]:
        print(json.dumps(result["alerts"], indent=2)[:4000])


if __name__ == "__main__":
    main()
