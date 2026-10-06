#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "httpx>=0.28,<1"]
# ///
"""How good is one routing vote? Samples plan_route's context-free router prompt on every routing case and
scores each sample (route, and difficulty after the deterministic checker) against the case expectations.

    uv run --script evals/vote_check.py --thinking off --samples 3 [--cases a,b] [--model qwen3.6-35b]

Prints single-vote accuracy, majority-of-N accuracy and seconds per vote, so the vote settings in plans.yaml
(route_samples, ARCH_ROUTE_THINKING) can be chosen from data.
"""
import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "mcp" / "arch-tools"))
from archeval.cases import load_routing_cases  # noqa: E402
from arch_tools import routing as R  # noqa: E402
from arch_tools.config import Config  # noqa: E402


def expected_route(case):  # eval cases say "architecture"; the checker says "architecture-change"
    return {"architecture-change" if r == "architecture" else r for r in case["route"]}


def score(case, sample):
    try:
        plan = R.check_plan({"route": sample.get("route"), "signals": sample.get("signals"), "agents": []})
    except Exception:  # noqa: BLE001 - unusable sample
        return False, False
    route_ok = plan["route"] in expected_route(case)
    diff_ok = not case["difficulty"] or plan["difficulty"] in case["difficulty"]
    return route_ok, route_ok and diff_ok


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thinking", choices=["on", "off"], default="off")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--cases", default="")
    ap.add_argument("--model", default="qwen3.6-35b")
    args = ap.parse_args()
    os.environ["ARCH_ROUTE_THINKING"] = args.thinking
    cases = load_routing_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    cfg = Config.from_env()
    single_route = single_full = maj_route = maj_full = n_votes = 0
    seconds = 0.0
    for i, case in enumerate(cases, 1):
        t0 = time.monotonic()
        samples, errors = await R.sample_routes(case["prompt"], args.samples, args.model, cfg)
        seconds += time.monotonic() - t0
        scored = [score(case, s) for s in samples]
        n_votes += args.samples  # failed samples count as wrong
        single_route += sum(r for r, _ in scored)
        single_full += sum(f for _, f in scored)
        if samples:
            merged, _ = R.vote(samples[0], samples[1:])
            r_ok, f_ok = score(case, merged)
        else:
            r_ok = f_ok = False
        maj_route += r_ok
        maj_full += f_ok
        routes = Counter(R.norm_route(s.get("route")) for s in samples)
        print(f"[{i:2d}/{len(cases)}] {'OK ' if f_ok else 'BAD'} {case['id']:34s} votes={dict(routes)} "
              f"{'errors=' + str(len(errors)) if errors else ''}", flush=True)
    n = len(cases)
    print(f"\nthinking={args.thinking} samples={args.samples} model={args.model} cases={n}")
    print(f"  single vote: route {single_route / n_votes:.0%}, route+difficulty {single_full / n_votes:.0%}")
    print(f"  majority of {args.samples}: route {maj_route / n:.0%}, route+difficulty {maj_full / n:.0%}")
    print(f"  {seconds / n:.1f} s per case ({args.samples} votes, run concurrently)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
