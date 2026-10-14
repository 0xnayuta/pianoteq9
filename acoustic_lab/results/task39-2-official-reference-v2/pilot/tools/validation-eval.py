#!/usr/bin/env python3
"""后继验证批次通用对照评估（amendment-3/4 判据 + amendment-5 守卫；只读）。

矩阵、条件与工具绑定全部从预登记 JSON 读取（防止评估与登记漂移）；工具散列在评估时
重新计算并写入产物，供审计比对。

判据（amendment-3/4，与 validation-interp 相同）：
- 可比较分音集 = 两侧 W1 共同识别分音；<72 键用 n>=min_comparable_below_72，
- 72–95 键用 n>=5，>=96 键不排除分音（amendment-3 的固定拍频段边界）；
- 基准 m = 可比较集最小共同分音，不计入样本；
- err(n) = 1200 * log2( (dev(n)/dev(m)) / (ref(n)/ref(m)) )；
- 判据：RMS(err) <= 1 cent 且 max|err| <= 3 cents，且非基准样本 >= 2。

用法：
  python3 validation-eval.py --preregistration <prereg.json> \
    --reference-batch <batch root> --dev-render <render root> --out <result.json> \
    [--refinement-guard-db 20|off]
"""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

BASE = "/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2"
ANALYSIS_TOOL = f"{BASE}/pilot/tools/pilot-partial-analysis.py"

spec = importlib.util.spec_from_file_location("ppa", ANALYSIS_TOOL)
ppa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppa)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def peaks(path, note):
    r = ppa.analyze_unit(ppa.Path(path), note)
    w = r["windows"]["W1"]
    observed = {int(n): float(f) for n, f in zip(w["partial_numbers"], w["observed_peak_Hz"])}
    return observed, r["effective_B"], r["f1_Hz"], int(w["identified_partials"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--reference-batch", required=True)
    parser.add_argument("--dev-render", required=True, help="devpiano render root (<rate>/n<note>-v<vel>.wav)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--candidate-table", default=None)
    parser.add_argument("--refinement-guard-db", default=None,
                        help="override preregistered guard; 'off' = legacy nearest")
    options = parser.parse_args()

    prereg = json.loads(Path(options.preregistration).read_text())
    evaluation = prereg["evaluation"]
    a4 = evaluation["a4_hz"]
    matrix = evaluation["matrix"]
    velocities = evaluation["velocities"]
    min_comparable = evaluation["min_comparable_below_72"]
    guard = evaluation.get("refinement_guard_db", 20.0)
    if options.refinement_guard_db is not None:
        guard = (None if str(options.refinement_guard_db).lower() in ("off", "none")
                 else float(options.refinement_guard_db))
    ppa.REFINEMENT_GUARD_DB = guard

    ppa.NOTES = {n: a4 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}
    ppa.SNR_ADMISSION_DB = 25.0
    ppa.SNR_MIN_NOTE = 72

    ref_root = Path(options.reference_batch)
    dev_root = Path(options.dev_render)
    results = []
    for row in matrix:
        note, rate, repeat, session = row["note"], row["rate"], row["repeat"], row["session"]
        for vel in velocities:
            unit = f"n{note}-v{vel}-{rate}-rep{repeat}"
            ref_path = ref_root / "sessions" / session / "units" / unit / "export.wav"
            dev_path = dev_root / str(rate) / f"n{note}-v{vel}.wav"
            entry = {"note": note, "velocity": vel, "rate": rate, "repeat": repeat, "unit": unit}
            try:
                rp, rB, rf1, rparts = peaks(ref_path, note)
                dp, dB, df1, dparts = peaks(dev_path, note)
            except Exception as error:  # noqa: BLE001
                entry["error"] = str(error)[:80]
                results.append(entry)
                continue
            common = sorted(set(rp) & set(dp))
            first_comparable = min_comparable if note < 72 else (5 if note < 96 else 1)
            comparable = [n for n in common if n >= first_comparable]
            entry.update({
                "ref_partials": rparts, "dev_partials": dparts,
                "common_partials": len(common), "comparable_partials": len(comparable),
                "B_rel_pct": (dB - rB) / rB * 100.0,
                "ref_B": rB, "dev_B": dB, "f1_cents": 1200.0 * math.log2(df1 / rf1),
            })
            if len(comparable) >= 1:
                m = comparable[0]
                errs, detail = [], []
                for n in comparable:
                    if n == m:
                        continue
                    e = 1200.0 * math.log2((dp[n] / dp[m]) / (rp[n] / rp[m]))
                    errs.append(e)
                    detail.append({"partial": n, "error_cents": e})
                entry["base_partial"] = m
                entry["nonbase_count"] = len(errs)
                entry["norm_rms"] = float(np.sqrt(np.mean(np.square(errs)))) if errs else None
                entry["norm_max"] = float(np.max(np.abs(errs))) if errs else None
                entry["details"] = detail
            results.append(entry)

    ok = [r for r in results if r.get("norm_rms") is not None and r.get("nonbase_count", 0) >= 2]
    weak = [r for r in results if r.get("norm_rms") is not None and r.get("nonbase_count", 0) < 2]
    errs_n = [r for r in results if "error" in r]
    passing = [r for r in ok if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0]
    out = {
        "schema": "devpiano-task39-2-validation-eval",
        "preregistration": str(options.preregistration),
        "preregistration_sha256": sha256(options.preregistration),
        "analysis_tool": ANALYSIS_TOOL,
        "analysis_tool_sha256": sha256(ANALYSIS_TOOL),
        "refinement_guard_db": guard,
        "reference_batch": str(ref_root),
        "dev_render": str(dev_root),
        "candidate_table": options.candidate_table,
        "criterion": ("amendment-3 comparable set (n>=%d below MIDI72, n>=5 at MIDI72-95, n>=1 from MIDI96); "
                      "amendment-4 base m = min common comparable; "
                      "RMS<=1 cent and max<=3 cents, >=2 non-base partials; amendment-5 strength guard"
                      % min_comparable),
        "units_total": len(results),
        "units_evaluable": len(ok),
        "units_weak": [r["unit"] for r in weak],
        "units_error": [r["unit"] for r in errs_n],
        "units_passing": len(passing),
        "failing_units": [r["unit"] for r in ok if r["norm_rms"] > 1.0 or r["norm_max"] > 3.0],
        "results": results,
    }
    Path(options.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"guard={guard}: units {len(results)} evaluable {len(ok)} weak {len(weak)} error {len(errs_n)} "
          f"passing {len(passing)}")
    notes = sorted({r["note"] for r in results})
    for note in notes:
        rows = [r for r in ok if r["note"] == note]
        if not rows:
            continue
        nr = [r["norm_rms"] for r in rows]
        nm = [r["norm_max"] for r in rows]
        b = [r["B_rel_pct"] for r in rows]
        p = sum(1 for r in rows if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0)
        print(f"  n{note}: B_rel {np.mean(b):+6.2f}%  rms mean {np.mean(nr):5.3f} max {max(nr):5.3f}  "
              f"max mean {np.mean(nm):5.3f} worst {max(nm):5.3f}  pass {p}/{len(rows)}")
    if ok:
        nr = [r["norm_rms"] for r in ok]
        nm = [r["norm_max"] for r in ok]
        print(f"overall: median rms {np.median(nr):.3f} worst rms {max(nr):.3f} | "
              f"median max {np.median(nm):.3f} worst max {max(nm):.3f}")


if __name__ == "__main__":
    main()
