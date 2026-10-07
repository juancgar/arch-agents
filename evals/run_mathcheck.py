#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "httpx>=0.28,<1"]
# ///
"""Math/number checking bake-off on the local router: which model catches planted errors in paper excerpts?

    uv run --script evals/run_mathcheck.py --models qwen3.6-35b,gpt-oss-20b,deepseek-r1-8b,glm-4.7-flash [--cases a,b]

Pure model reasoning (no tools), temperature 0, one call per excerpt. Scores per model: planted errors caught,
false alarms (findings that match no planted error, incl. anything on the clean controls), seconds per case.
Results: evals/results/<stamp>-mathcheck.jsonl
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
BASE = os.environ.get("ARCH_LLM_BASE", "http://omen:8080").rstrip("/")
KEY_FILE = os.path.expanduser(os.environ.get("ARCH_LLM_KEY_FILE", "~/.config/llama-server/api-key"))

SYSTEM = (
    "You are a meticulous reviewer checking the mathematics and numbers in an excerpt from a research paper. "
    "Recompute every number from the inputs given in the text, re-derive every equation, and check units, ranges "
    "and internal consistency. Report only genuine errors: do not flag style, missing context or things you cannot "
    "verify from the text. If everything is correct, return an empty list.\n"
    'Reply with only JSON: {"findings": [{"location": "<what/where>", "issue": "<what is wrong>", '
    '"stated": "<value in text>", "expected": "<correct value or form>"}]}'
)


def extract_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    for m in re.finditer(r"\{", text):
        depth = 0
        for i in range(m.start(), len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[m.start():i + 1])
                        if isinstance(obj, dict) and "findings" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
    return None


def ask(client: httpx.Client, model: str, text: str, headers: dict, max_tokens: int) -> tuple[str, dict]:
    body = {
        "model": model, "temperature": 0, "max_tokens": max_tokens, "stream": False,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Excerpt:\n\n{text}"}],
    }
    if model.startswith("gpt-oss"):
        body["chat_template_kwargs"] = {"reasoning_effort": "high"}
    deadline = time.monotonic() + 900
    while True:
        r = client.post(f"{BASE}/v1/chat/completions", json=body, headers=headers, timeout=900)
        if r.status_code == 503 and time.monotonic() < deadline:  # model swap in progress
            time.sleep(3)
            continue
        r.raise_for_status()
        payload = r.json()
        msg = payload["choices"][0]["message"]
        return (msg.get("content") or msg.get("reasoning_content") or ""), payload


def score(case: dict, findings: list[dict]) -> dict:
    texts = [" ".join(str(f.get(k, "")) for k in ("location", "issue", "stated", "expected")).lower() for f in findings]
    caught, matched = [], set()
    for p in case["planted"]:
        hit = next((i for i, t in enumerate(texts) if any(k.lower() in t for k in p["keywords"])), None)
        caught.append(hit is not None)
        if hit is not None:
            matched.add(hit)
    return {"caught": caught, "false_alarms": len(texts) - len(matched)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--cases", default="")
    ap.add_argument("--max-tokens", type=int, default=12000)
    args = ap.parse_args()
    cases = yaml.safe_load((HERE / "mathcheck" / "cases.yaml").read_text())["cases"]
    if args.cases:
        want = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in want]
    key = Path(KEY_FILE).read_text().strip() if Path(KEY_FILE).exists() else ""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-mathcheck.jsonl"
    summary = {}
    with httpx.Client() as client, out.open("w") as fh:
        for model in args.models.split(","):
            tot_planted = tot_caught = tot_fa = parse_fail = 0
            secs = 0.0
            for case in cases:
                t0 = time.monotonic()
                try:
                    text, payload = ask(client, model, case["text"], headers, args.max_tokens)
                    err = None
                except Exception as exc:  # noqa: BLE001
                    text, payload, err = "", {}, f"{type(exc).__name__}: {exc}"
                dt = time.monotonic() - t0
                secs += dt
                obj = extract_json(text)
                findings = obj["findings"] if obj and isinstance(obj.get("findings"), list) else []
                if obj is None:
                    parse_fail += 1
                sc = score(case, findings)
                tot_planted += len(case["planted"])
                tot_caught += sum(sc["caught"])
                tot_fa += sc["false_alarms"]
                row = {"model": model, "id": case["id"], "seconds": round(dt, 1), "error": err, "parsed": obj is not None,
                       "caught": sc["caught"], "false_alarms": sc["false_alarms"], "findings": findings,
                       "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
                       "completion_tokens": (payload.get("usage") or {}).get("completion_tokens")}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                mark = "OK " if all(sc["caught"]) and sc["false_alarms"] == 0 else "   "
                print(f"[{model:14s}] {mark} {case['id']:28s} {dt:6.1f}s caught={sum(sc['caught'])}/{len(case['planted'])} "
                      f"fa={sc['false_alarms']}{' PARSE-FAIL' if obj is None else ''}{' ' + err if err else ''}", flush=True)
            summary[model] = {"caught": f"{tot_caught}/{tot_planted}", "false_alarms": tot_fa, "parse_fail": parse_fail,
                              "s_per_case": round(secs / max(len(cases), 1), 1)}
    print("\n== summary (pure reasoning, no tools)")
    for m, s in summary.items():
        print(f"  {m:14s} caught {s['caught']:6s} false alarms {s['false_alarms']:2d} parse fails {s['parse_fail']} "
              f"{s['s_per_case']:6.1f} s/case")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
