"""评测 runner。

  python -m evals                         # 跑全部 step，被测 agent 默认用 Claude
  python -m evals --step draft --step publish --agent deepseek
  python -m evals --trials 3              # 每个用例跑 3 次，看稳定性（pass^3）
  python -m evals --step risk_engine      # 只跑确定性的风控引擎用例，不需要任何 key
  python -m evals --replay evals/results/xxx.json   # 用上次保存的输出重新评分，不调用 agent
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from harness import risk
from harness.config import load_niche

from . import agents, models
from .graders import run_grader
from .judge import judge_backend, make_judge
from .sandbox import sandbox

EVALS_DIR = Path(__file__).resolve().parent
CASES_DIR = EVALS_DIR / "cases"
RESULTS_DIR = EVALS_DIR / "results"

# 顺序即流水线顺序
STEP_ORDER = ["draft", "select", "cards", "risk_engine", "risk_fix", "risk_review", "publish"]
OFFLINE_STEPS = {"risk_engine"}


def load_cases(step: str) -> dict:
    return json.loads((CASES_DIR / f"{step}.json").read_text(encoding="utf-8"))


def run_engine(case: dict) -> dict:
    final = case["input"]["final"]
    return {"issues": risk.check(final, load_niche(final.get("niche")), None, mode=case["input"].get("mode", "B"))}


def call_agent(step: str, backend: str, case: dict) -> dict:
    t0 = time.time()
    try:
        out = agents.STEPS[step](backend, case["input"])
        err = None
    except Exception as e:
        out, err = None, f"{type(e).__name__}: {e}"
    return {"output": out, "error": err, "seconds": round(time.time() - t0, 1)}


def grade(step_meta: dict, case: dict, output, judge, judge_pool) -> list:
    inp = case["input"]
    base = inp.get("final") or {k: inp[k] for k in ("title", "body", "tags") if k in inp}
    ctx = {"input": inp, "task_desc": step_meta["task"], "niche": inp.get("niche"), "base_final": base}
    code_specs = [g for g in case["graders"] if g["type"] != "judge"]
    judge_specs = [g for g in case["graders"] if g["type"] == "judge"]
    with sandbox(published=case.get("published")):
        results = [run_grader(g, output, ctx) for g in code_specs]
    futures = [judge_pool.submit(run_grader, g, output, ctx, judge) for g in judge_specs]
    return results, futures


def case_passed(results: list) -> bool:
    return all(r["passed"] is not False for r in results)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m evals", description="agent 各步骤的能力评测")
    ap.add_argument("--step", action="append", choices=STEP_ORDER, help="只跑某些 step，可重复")
    ap.add_argument("--case", action="append", help="只跑某些用例 id，可重复")
    ap.add_argument("--agent", default="claude", choices=models.BACKENDS, help="被测 agent 用哪个模型")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4, help="并发调用数")
    ap.add_argument("--no-judge", action="store_true", help="只用代码评分，不调用 judge")
    ap.add_argument("--replay", help="用保存的结果文件里的输出重新评分")
    ap.add_argument("--fail-under", type=float, help="总通过率低于这个值（0–1）时返回非 0")
    args = ap.parse_args(argv)

    steps = args.step or STEP_ORDER
    replay = None
    if args.replay:
        replay = {(r["step"], r["case"], r["trial"]): r for r in json.loads(Path(args.replay).read_text(encoding="utf-8"))["runs"]}

    need_agent = not replay and any(s not in OFFLINE_STEPS for s in steps)
    if need_agent and not models.available(args.agent):
        print(f"被测 agent「{args.agent}」没有配置 API key，只能跑 risk_engine。见 evals/README.md。")
        steps = [s for s in steps if s in OFFLINE_STEPS]
        if not steps:
            return 2

    judge = None if args.no_judge else make_judge()
    print(f"被测 agent：{args.agent}（{models.model_name(args.agent) if need_agent else '-'}）  "
          f"judge：{judge_backend() + '（' + models.model_name(judge_backend()) + '）' if judge else '无，judge 项跳过'}")

    runs = []
    pool = ThreadPoolExecutor(max_workers=args.workers)
    for step in steps:
        meta = load_cases(step)
        cases = [c for c in meta["cases"] if not args.case or c["id"] in args.case]
        if not cases:
            continue
        print(f"\n== {step}：{meta['task']}（{len(cases)} 个用例 × {args.trials}）")

        jobs = {}
        for c in cases:
            for t in range(args.trials):
                if replay is not None:
                    r = replay.get((step, c["id"], t))
                    jobs[(c["id"], t)] = r and {"output": r["output"], "error": r.get("error"), "seconds": 0}
                elif step in OFFLINE_STEPS:
                    jobs[(c["id"], t)] = None
                else:
                    jobs[(c["id"], t)] = pool.submit(call_agent, step, args.agent, c)

        pending = []
        for c in cases:
            for t in range(args.trials):
                job = jobs[(c["id"], t)]
                if step in OFFLINE_STEPS and replay is None:
                    with sandbox(published=c.get("published")):
                        call = {"output": run_engine(c), "error": None, "seconds": 0}
                elif job is None:
                    print(f"  ? {c['id']}：结果文件里没有这条，跳过")
                    continue
                else:
                    call = job.result() if hasattr(job, "result") else job
                if call["error"] or call["output"] is None:
                    results, futures = [{"grader": "agent", "passed": False, "detail": call["error"] or "无输出"}], []
                else:
                    results, futures = grade(meta, c, call["output"], judge, pool)
                pending.append((c, t, call, results, futures))

        for c, t, call, results, futures in pending:
            results = results + [f.result() for f in futures]
            ok = case_passed(results)
            runs.append({"step": step, "case": c["id"], "trial": t, "passed": ok, "known_gap": c.get("known_gap", False),
                         "output": call["output"], "error": call["error"], "seconds": call["seconds"], "grades": results})
            mark = "✓" if ok else ("·" if c.get("known_gap") else "✗")
            print(f"  {mark} {c['id']}" + (f" [trial {t + 1}]" if args.trials > 1 else ""))
            for r in results:
                if r["passed"] is False:
                    print(f"      ✗ {r['grader']}：{r['detail']}")
    pool.shutdown()

    summary = summarize(runs, steps, args.trials)
    print("\n" + summary["text"])
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.agent}.json"
    out.write_text(json.dumps({"agent": args.agent, "agent_model": models.model_name(args.agent),
                               "judge": judge_backend() if judge else None, "trials": args.trials,
                               "summary": summary["table"], "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果：{out}")
    if args.fail_under is not None and summary["overall"] < args.fail_under:
        return 1
    return 0


def summarize(runs: list, steps: list, trials: int) -> dict:
    table, lines = [], ["step            用例  pass@1   pass^k  已知缺口"]
    total_pass = total = 0
    for step in steps:
        rs = [r for r in runs if r["step"] == step and not r["known_gap"]]
        gaps = [r for r in runs if r["step"] == step and r["known_gap"]]
        if not rs and not gaps:
            continue
        ids = sorted({r["case"] for r in rs})
        p1 = sum(r["passed"] for r in rs) / len(rs) if rs else 0
        pk = sum(all(r["passed"] for r in rs if r["case"] == i) for i in ids) / len(ids) if ids else 0
        gap_ids = sorted({r["case"] for r in gaps})
        gap_fixed = sum(all(r["passed"] for r in gaps if r["case"] == i) for i in gap_ids)
        total_pass += sum(r["passed"] for r in rs)
        total += len(rs)
        table.append({"step": step, "cases": len(ids), "pass@1": round(p1, 3), "pass^k": round(pk, 3),
                      "known_gaps": len(gap_ids), "known_gaps_now_passing": gap_fixed})
        gap_txt = f"{gap_fixed}/{len(gap_ids)} 已修复" if gap_ids else "-"
        lines.append(f"{step:<15} {len(ids):>4}  {p1:>6.0%}  {pk:>6.0%}  {gap_txt}")
    overall = total_pass / total if total else 0
    lines.append(f"{'总计':<14} {total:>4}  {overall:>6.0%}" + (f"   （k={trials}）" if trials > 1 else ""))
    return {"text": "\n".join(lines), "table": table, "overall": overall}
