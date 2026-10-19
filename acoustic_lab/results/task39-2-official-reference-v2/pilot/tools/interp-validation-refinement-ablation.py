#!/usr/bin/env python3
"""nearest 精化轮消融对照：同一判据在“开/关精化轮”下的结果比较（只读、诊断）。

目的：量化 pilot-partial-analysis.analyze_unit 的 nearest 精化轮对 amendment-3/4 判据
的影响。开关方式：将 ppa.NEAREST_REL 置为极大值使精化轮返回空集合（工具中该常量只用于
精化轮的 min_rel），不改动任何仓库文件。

注意：本工具的输出是“诊断对照”，不是新判决；已归档的 one-shot 判决保持不变。
"""

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pra", f"{BASE}/pilot/tools/partial-refinement-audit.py")
pra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pra)
ppa = pra.ppa

A4 = 440.0
MATRIX = [  # (note, rate, repeat, session)
    (25, 44100, 0, "s01-n25-44100-rep0"), (25, 44100, 1, "s02-n25-44100-rep1"),
    (25, 48000, 0, "s03-n25-48000-rep0"), (25, 48000, 1, "s04-n25-48000-rep1"),
    (27, 44100, 0, "s05-n27-44100-rep0"), (27, 44100, 1, "s06-n27-44100-rep1"),
    (27, 48000, 0, "s07-n27-48000-rep0"), (27, 48000, 1, "s08-n27-48000-rep1"),
    (53, 44100, 0, "s09-n53-44100-rep0"), (53, 44100, 1, "s10-n53-44100-rep1"),
    (53, 48000, 0, "s11-n53-48000-rep0"), (53, 48000, 1, "s12-n53-48000-rep1"),
    (59, 44100, 0, "s13-n59-44100-rep0"), (59, 44100, 1, "s14-n59-44100-rep1"),
    (59, 48000, 0, "s15-n59-48000-rep0"), (59, 48000, 1, "s16-n59-48000-rep1"),
]
VELOCITIES = (47, 79, 107)
BEATING_PARTIALS_BELOW_72 = 6


def evaluate(reference_batch, dev_render, disable_refined, out_path):
    ppa.NOTES = {n: A4 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}
    ppa.SNR_ADMISSION_DB = 25.0
    ppa.SNR_MIN_NOTE = 72
    if disable_refined:
        ppa.NEAREST_REL = 1e9  # 精化轮 min_rel 极大 -> 返回空 -> 不采用

    results = []
    for note, rate, repeat, session in MATRIX:
        for velocity in VELOCITIES:
            unit = f"n{note}-v{velocity}-{rate}-rep{repeat}"
            ref_path = Path(reference_batch) / "sessions" / session / "units" / unit / "export.wav"
            dev_path = Path(dev_render) / str(rate) / f"n{note}-v{velocity}.wav"
            entry = {"note": note, "velocity": velocity, "rate": rate, "repeat": repeat, "unit": unit}
            try:
                rw = pra.analyze_variant(ref_path, note, not disable_refined)["W1"]
                dw = pra.analyze_variant(dev_path, note, not disable_refined)["W1"]
            except Exception as error:  # noqa: BLE001
                entry["error"] = str(error)[:80]
                results.append(entry)
                continue
            rp = dict(zip(rw["numbers"], rw["observed"]))
            dp = dict(zip(dw["numbers"], dw["observed"]))
            common = sorted(set(rp) & set(dp))
            comparable = [n for n in common if n > BEATING_PARTIALS_BELOW_72]
            entry.update({
                "ref_partials": len(rp), "dev_partials": len(dp),
                "common_partials": len(common), "comparable_partials": len(comparable),
                "B_rel_pct": (dw["B"] - rw["B"]) / rw["B"] * 100.0,
                "f1_cents": 1200.0 * math.log2(dw["f1"] / rw["f1"]),
                "ref_B": rw["B"], "dev_B": dw["B"],
            })
            if len(comparable) >= 1:
                m = comparable[0]
                errs = []
                details = []
                for n in comparable:
                    if n == m:
                        continue
                    e = 1200.0 * math.log2((dp[n] / dp[m]) / (rp[n] / rp[m]))
                    errs.append(e)
                    details.append({"partial": n, "error_cents": e})
                entry["base_partial"] = m
                entry["nonbase_count"] = len(errs)
                entry["norm_rms"] = float(np.sqrt(np.mean(np.square(errs)))) if errs else None
                entry["norm_max"] = float(np.max(np.abs(errs))) if errs else None
                entry["details"] = details
            results.append(entry)

    ok = [r for r in results if r.get("norm_rms") is not None and r.get("nonbase_count", 0) >= 2]
    passing = [r for r in ok if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0]
    report = {
        "schema": "devpiano-task39-2-interp-validation-refinement-ablation",
        "reference_batch": str(reference_batch), "dev_render": str(dev_render),
        "disable_refined": disable_refined,
        "criterion": "amendment-3 comparable set (n>=7); amendment-4 base m = min common comparable; RMS<=1 and max<=3 cents, >=2 non-base partials",
        "units_total": len(results), "units_evaluable": len(ok),
        "units_passing": len(passing),
        "failing_units": [r["unit"] for r in ok if r["norm_rms"] > 1.0 or r["norm_max"] > 3.0],
        "results": results,
    }
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"disable_refined={disable_refined}: evaluable {len(ok)} passing {len(passing)} "
          f"failing={report['failing_units']}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-batch", required=True)
    parser.add_argument("--dev-render", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--guard-db", default="20",
                        help="strength guard in dB for the refinement round; 'off' = legacy nearest")
    options = parser.parse_args()
    ppa.REFINEMENT_GUARD_DB = (None if str(options.guard_db).lower() in ("off", "none")
                               else float(options.guard_db))
    out_dir = Path(options.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    on = evaluate(options.reference_batch, options.dev_render, False,
                  out_dir / "ablation-refined-on.json")
    off = evaluate(options.reference_batch, options.dev_render, True,
                   out_dir / "ablation-refined-off.json")
    a = {r["unit"]: r for r in on["results"] if r.get("norm_rms") is not None}
    b = {r["unit"]: r for r in off["results"] if r.get("norm_rms") is not None}
    print("== per-unit 对照（仅显示有变化或原本失败的单元） ==")
    for unit in sorted(a):
        ra, rb = a[unit], b[unit]
        pass_a = ra["norm_rms"] <= 1.0 and ra["norm_max"] <= 3.0
        pass_b = rb["norm_rms"] <= 1.0 and rb["norm_max"] <= 3.0
        if pass_a != pass_b or not pass_a:
            print(f"  {unit}: on rms={ra['norm_rms']:.3f} max={ra['norm_max']:.3f} "
                  f"{'PASS' if pass_a else 'FAIL'} -> off rms={rb['norm_rms']:.3f} "
                  f"max={rb['norm_max']:.3f} {'PASS' if pass_b else 'FAIL'}")


if __name__ == "__main__":
    main()
