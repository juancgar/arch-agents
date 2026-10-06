#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Routing eval: ask the orchestrator to classify each case (ROUTE-ONLY mode) and score it.

    uv run --script evals/run_routing.py --plan offline [--cases id1,id2] [--timeout 600] [--dry-run]
"""
import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archeval import DEFAULT_RESULTS_DIR, REPO_ROOT, ROUTE_ONLY_PREFIX  # noqa: E402
from archeval.cases import load_routing_cases  # noqa: E402
from archeval.jsonextract import parse_launcher_stdout  # noqa: E402
from archeval.procs import run_process  # noqa: E402
from archeval.routing import score_routing, stub_output  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="offline")
    ap.add_argument("--cases", default="")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cases = load_routing_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = DEFAULT_RESULTS_DIR / f"{stamp}-{args.plan}-routing.jsonl"
    launcher = REPO_ROOT / "bin" / "arch"
    rows = []
    with out_path.open("w") as out:
        for i, case in enumerate(cases, 1):
            prompt = ROUTE_ONLY_PREFIX + case["prompt"]
            t0 = time.monotonic()
            if args.dry_run:
                stdout, err, code = stub_output(case), None, 0
            else:
                with tempfile.TemporaryDirectory() as work:
                    run_process(["git", "init", "-q"], cwd=work, timeout=30)
                    proc = run_process([str(launcher), args.plan, "-p", prompt], cwd=work, timeout=args.timeout)
                    stdout, err, code = proc.stdout, (proc.error or ("timeout" if proc.timed_out else None)), proc.exit_code
            answer = parse_launcher_stdout(stdout).answer_text
            score = score_routing(case, answer)
            row = {"id": case["id"], "plan": args.plan, "seconds": round(time.monotonic() - t0, 1), "exit": code,
                   "error": err, "pass": score["pass"], "score": score["score"],
                   "failed_checks": [k for k, v in score["checks"].items() if not v["ok"]],
                   "got": score["normalized"], "raw": answer[-3000:]}
            rows.append(row)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            mark = "PASS" if row["pass"] else "FAIL"
            print(f"[{i:2d}/{len(cases)}] {mark} {case['id']:34s} {row['seconds']:6.1f}s  "
                  f"route={row['got'].get('route')} diff={row['got'].get('difficulty')} "
                  f"{'failed=' + ','.join(row['failed_checks']) if row['failed_checks'] else ''}", flush=True)

    passed = sum(r["pass"] for r in rows)
    mean = sum(r["score"] for r in rows) / max(len(rows), 1)
    summary = f"\n{args.plan}: {passed}/{len(rows)} cases fully correct, mean check score {mean:.2f}, results: {out_path}"
    print(summary)
    fails = {}
    for r in rows:
        for c in r["failed_checks"]:
            fails[c] = fails.get(c, 0) + 1
    if fails:
        print("failed checks by type:", ", ".join(f"{k}={v}" for k, v in sorted(fails.items(), key=lambda x: -x[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
