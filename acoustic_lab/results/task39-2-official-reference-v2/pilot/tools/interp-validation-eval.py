#!/usr/bin/env python3
"""interp 验证集对照评估（amendment-3 可比较分音集 + amendment-4 干净基准；只读）。

口径（冻结于 validation-interp 预登记）：
- 可比较分音集 = 两侧 W1 共同识别分音 ∩ n >= 7（<72 的键排除 beatingPartials 覆盖段）；
- 基准 m = 可比较集的最小共同分音号；m 不计入 RMS/max 样本数；
- 归一化误差 err(n) = 1200 * log2( (dev(n)/dev(m)) / (ref(n)/ref(m)) )；
- 判据：RMS(err) <= 1 cent 且 max|err| <= 3 cents，且非基准可比较分音 >= 2；
- 全口径与 B 相对偏差并列记录（诊断，不放松判据）。
"""

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ppa", f"{BASE}/pilot/tools/pilot-partial-analysis.py")
ppa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppa)

gate_spec = importlib.util.spec_from_file_location("validation_gate", Path(__file__).with_name("validation-eval.py"))
gate = importlib.util.module_from_spec(gate_spec)
gate_spec.loader.exec_module(gate)

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


def peaks(path, note):
    # 消费数据诊断域：显式 file_absolute 绝对秒窗；历史绝对分析绝不改写为 NoteOn 相对坐标。
    r = ppa.analyze_unit(ppa.Path(path), note, timing={"coordinate": ppa.COORDINATE_FILE_ABSOLUTE})
    w = r["windows"]["W1"]
    quality = gate.reference_quality(r)
    if not quality["admitted"]:
        raise ValueError(f"reference-quality rejection: {quality['reasons']}; windows={r['window_failures']}")
    observed = {int(n): float(f) for n, f in zip(w["partial_numbers"], w["observed_peak_Hz"])}
    return observed, r["effective_B"], r["f1_Hz"], int(w["identified_partials"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-batch", required=True,
                    help="validation-interp batch root (sessions/<sess>/units/<unit>/export.wav)")
    ap.add_argument("--dev-render", required=True, help="devpiano render root (<rate>/n<note>-v<vel>.wav)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--candidate-table", default=None, help="frozen candidate table (recorded reference only)")
    args = ap.parse_args()
    if Path(args.out).exists():
        ap.error("Output exists; preserve historical evidence")

    ppa.NOTES = {n: A4 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}
    ppa.SNR_ADMISSION_DB = 25.0
    ppa.SNR_MIN_NOTE = 72

    ref_root = Path(args.reference_batch)
    dev_root = Path(args.dev_render)
    results = []
    for note, rate, repeat, sess in MATRIX:
        for vel in VELOCITIES:
            unit = f"n{note}-v{vel}-{rate}-rep{repeat}"
            ref_path = ref_root / "sessions" / sess / "units" / unit / "export.wav"
            dev_path = dev_root / str(rate) / f"n{note}-v{vel}.wav"
            entry = {"note": note, "velocity": vel, "rate": rate, "repeat": repeat, "unit": unit}
            try:
                rp, rB, rf1, rparts = peaks(ref_path, note)
                dp, dB, df1, dparts = peaks(dev_path, note)
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)[:80]
                results.append(entry)
                continue
            common = sorted(set(rp) & set(dp))
            comparable = [n for n in common if n > BEATING_PARTIALS_BELOW_72]
            entry.update({
                "ref_partials": rparts, "dev_partials": dparts,
                "common_partials": len(common), "comparable_partials": len(comparable),
                "B_rel_pct": (dB - rB) / rB * 100.0,
                "ref_B": rB, "dev_B": dB, "f1_cents": 1200.0 * math.log2(df1 / rf1),
            })
            if len(comparable) >= 1:
                m = comparable[0]
                errs = []
                detail = []
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
        "schema": "devpiano-task39-2-interp-validation-eval",
        "assessment_role": "consumed_data_diagnostic_only",
        "historical_verdict_changed": False,
        "partial_observer_sha256": ppa.sha256(ppa.OBSERVER_PATH),
        "reference_batch": str(ref_root),
        "dev_render": str(dev_root),
        "candidate_table": args.candidate_table,
        "criterion": "amendment-3 comparable set (n>=7); amendment-4 base m = min common comparable; RMS<=1 cent and max<=3 cents, >=2 non-base partials",
        "units_total": len(results),
        "units_evaluable": len(ok),
        "units_weak": [r["unit"] for r in weak],
        "units_error": [r["unit"] for r in errs_n],
        "units_passing": len(passing),
        "results": results,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"units {len(results)} evaluable {len(ok)} weak {len(weak)} error {len(errs_n)} passing {len(passing)}")
    for note in (25, 27, 53, 59):
        rows = [r for r in ok if r["note"] == note]
        if not rows:
            continue
        b = [r["B_rel_pct"] for r in rows]
        nr = [r["norm_rms"] for r in rows]
        nm = [r["norm_max"] for r in rows]
        p = sum(1 for r in rows if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0)
        print(f"  n{note}: B_rel {np.mean(b):+6.2f}%  norm_rms mean {np.mean(nr):5.3f} max {max(nr):5.3f}  "
              f"norm_max mean {np.mean(nm):5.3f} worst {max(nm):5.3f}  pass {p}/{len(rows)}")
    if ok:
        nr = [r["norm_rms"] for r in ok]
        nm = [r["norm_max"] for r in ok]
        print(f"overall: median rms {np.median(nr):.3f} worst rms {max(nr):.3f} | median max {np.median(nm):.3f} worst max {max(nm):.3f}")


if __name__ == "__main__":
    main()
