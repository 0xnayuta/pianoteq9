#!/usr/bin/env python3
"""sealed validation（validation-20261013-185755）的 nearest 精化轮消融对照（只读、诊断）。

判据口径复现自 `validation-evaluation-report.md`：
- theory 基准 A4=442；
- 归一化分音比 f(n)/f(1)，n 取两侧共同识别分音（n≥2）；
- 判据 RMS ≤1 cent 且 max ≤3 cents（报告汇总为 12/28 可归一化单元通过）。

开/关精化轮通过 ppa.NEAREST_REL 切换（1e9 → 精化轮返回空）。不修改任何文件；
输出为诊断对照，已归档的一次性判决保持不变。
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

A4 = 442.0
NOTES = (26, 39, 50, 63, 77, 86, 98, 104)
VELOCITIES = (55, 85, 113)
RATES = (44100, 48000)


def evaluate(batch, dev_root, disable_refined, out_path):
    ppa.NOTES = {n: A4 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}
    ppa.SNR_ADMISSION_DB = 25.0
    ppa.SNR_MIN_NOTE = 72
    if disable_refined:
        ppa.NEAREST_REL = 1e9

    results = []
    for index, note in enumerate(NOTES, start=1):
        for rate in RATES:
            session_number = 2 * (index - 1) + (1 if rate == 44100 else 2)
            session = f"s{session_number:02d}-n{note}-{rate}"
            for velocity in VELOCITIES:
                unit = f"n{note}-v{velocity}-{rate}-rep0"
                ref_path = batch / "sessions" / session / "units" / unit / "export.wav"
                dev_path = dev_root / str(rate) / f"n{note}-v{velocity}.wav"
                entry = {"note": note, "velocity": velocity, "rate": rate, "unit": unit}
                if not ref_path.is_file() or not dev_path.is_file():
                    entry["error"] = "missing file"
                    results.append(entry)
                    continue
                try:
                    rw = pra.analyze_variant(ref_path, note, not disable_refined)["W1"]
                    dw = pra.analyze_variant(dev_path, note, not disable_refined)["W1"]
                except Exception as error:  # noqa: BLE001
                    entry["error"] = str(error)[:60]
                    results.append(entry)
                    continue
                rp = dict(zip(rw["numbers"], rw["observed"]))
                dp = dict(zip(dw["numbers"], dw["observed"]))
                common = sorted(set(rp) & set(dp))
                entry.update({"common_partials": len(common), "ref_partials": len(rp),
                              "dev_partials": len(dp),
                              "ref_B": rw["B"], "dev_B": dw["B"],
                              "B_rel_pct": (dw["B"] - rw["B"]) / rw["B"] * 100.0,
                              "f1_cents": 1200.0 * math.log2(dw["f1"] / rw["f1"])})
                errs = []
                if len(common) >= 3 and 1 in rp and 1 in dp:
                    for n in common:
                        if n == 1:
                            continue
                        errs.append(1200.0 * math.log2((dp[n] / dp[1]) / (rp[n] / rp[1])))
                entry["norm_rms"] = float(np.sqrt(np.mean(np.square(errs)))) if errs else None
                entry["norm_max"] = float(np.max(np.abs(errs))) if errs else None
                results.append(entry)

    analyzable = [r for r in results if r.get("norm_rms") is not None]
    passing = [r for r in analyzable if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0]
    report = {
        "schema": "devpiano-sealed-validation-refinement-ablation",
        "batch": str(batch), "dev_render": str(dev_root), "disable_refined": disable_refined,
        "criterion": "normalized partial ratio f(n)/f(1), n>=2 over common partials; RMS<=1 and max<=3 cents",
        "units_total": len(results), "units_analyzable": len(analyzable),
        "units_passing": len(passing),
        "failing_units": [r["unit"] for r in analyzable
                          if r["norm_rms"] > 1.0 or r["norm_max"] > 3.0],
        "results": results,
    }
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"disable_refined={disable_refined}: analyzable {len(analyzable)} passing {len(passing)}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--dev-render", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--guard-db", default="20",
                        help="strength guard in dB for the refinement round; 'off' = legacy nearest")
    options = parser.parse_args()
    ppa.REFINEMENT_GUARD_DB = (None if str(options.guard_db).lower() in ("off", "none")
                               else float(options.guard_db))
    out_dir = Path(options.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    batch = Path(options.batch)
    dev_root = Path(options.dev_render)
    on = evaluate(batch, dev_root, False, out_dir / "sealed-ablation-refined-on.json")
    off = evaluate(batch, dev_root, True, out_dir / "sealed-ablation-refined-off.json")
    a = {r["unit"]: r for r in on["results"] if r.get("norm_rms") is not None}
    b = {r["unit"]: r for r in off["results"] if r.get("norm_rms") is not None}
    print("== 判定状态变化的单元 ==")
    flips = 0
    for unit in sorted(a):
        if unit not in b:
            continue
        pass_a = a[unit]["norm_rms"] <= 1.0 and a[unit]["norm_max"] <= 3.0
        pass_b = b[unit]["norm_rms"] <= 1.0 and b[unit]["norm_max"] <= 3.0
        if pass_a != pass_b:
            flips += 1
            print(f"  {unit}: on rms={a[unit]['norm_rms']:.3f} max={a[unit]['norm_max']:.3f} "
                  f"{'PASS' if pass_a else 'FAIL'} -> off rms={b[unit]['norm_rms']:.3f} "
                  f"max={b[unit]['norm_max']:.3f} {'PASS' if pass_b else 'FAIL'}")
    print(f"status flips: {flips}")


if __name__ == "__main__":
    main()
