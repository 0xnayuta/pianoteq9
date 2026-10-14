#!/usr/bin/env python3
"""nearest 精化轮影响审计（只读）。

背景：pilot-partial-analysis.analyze_unit 在 strongest 匹配（stage A/B）之后还有一个
nearest 精化轮（STAGE_B_TOL 容差内取最靠近预测的峰，NEAREST_REL=1e-7 极低门槛）。
validation-interp 判决发现 n27-v107-48000 的 n11/n12 被 -65 dB 泄漏/噪声伪峰拉离真峰
约 7.6 / 5.5 cents。本工具对任意批次逐单元对比“开/关精化轮”的结果，量化该机制的
实际影响面（不改工具、不改判据、不重算任何判决）。

用法：
  python3 partial-refinement-audit.py --batch BATCH --preset PRESET --out DIR
"""

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

BASE = "/root/repos/pianoteq9/acoustic_lab/results/task39-2-official-reference-v2"
spec = importlib.util.spec_from_file_location("ppa", f"{BASE}/pilot/tools/pilot-partial-analysis.py")
ppa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppa)


def analyze_variant(path, note, refined_enabled):
    """复现 analyze_unit 主路径，按开关决定是否执行并采用 nearest 精化轮。"""
    rate, frames, left, right = ppa.read_wav_stereo(path)
    theory = ppa.NOTES[note]
    min_snr = ppa.SNR_ADMISSION_DB if (ppa.SNR_ADMISSION_DB is not None
                                       and note >= ppa.SNR_MIN_NOTE) else None
    seeds = ppa.EXTENDED_SEEDS if note >= ppa.SNR_MIN_NOTE else ppa.DEFAULT_SEEDS
    output = {}
    for name, window in ppa.WINDOWS.items():
        frequency, power = ppa.power_spectrum(left, right, rate, window)
        peaks, rel, snr = ppa.spectral_peaks(frequency, power, ppa.LOW_FREQ, ppa.MAX_FREQ)
        first, stiffness, numbers, observed = ppa.staged_match_multi(
            peaks, rel, snr, theory, seeds=seeds, min_snr=min_snr)
        adopted = "ab"
        if refined_enabled:
            rn, ro = ppa.match_partials(peaks, rel, snr, first, stiffness,
                                        ppa.STAGE_B_TOL, ppa.NEAREST_REL,
                                        mode="nearest", min_snr=min_snr,
                                        guard_db=getattr(ppa, "REFINEMENT_GUARD_DB", None))
            if len(rn) >= 5:
                solution = ppa.fit(ro, rn, first, stiffness)
                rf, rs = float(solution.x[0]), float(solution.x[1])
                current = float(np.max(np.abs(1200 * np.log2(
                    observed / ppa.partial_prediction([first, stiffness], numbers)))))
                refined = float(np.max(np.abs(1200 * np.log2(
                    ro / ppa.partial_prediction([rf, rs], rn)))))
                if refined <= current:
                    first, stiffness, numbers, observed = rf, rs, rn, ro
                    adopted = "refined"
        output[name] = {"f1": first, "B": stiffness,
                        "numbers": [int(v) for v in numbers],
                        "observed": [float(v) for v in observed],
                        "adopted": adopted}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--notes", default=None,
                        help="comma list override (default: preset notes)")
    parser.add_argument("--scan", action="store_true",
                        help="scan every sessions/*/units/*/export.wav and parse n/rate/rep from names")
    options = parser.parse_args()

    batch = Path(options.batch)
    out_dir = Path(options.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    preset = ppa.PRESETS[options.preset]
    notes = ({int(v) for v in options.notes.split(",")} if options.notes
             else set(preset["notes"].keys()))
    velocities = preset.get("velocities", ppa.VELOCITIES)
    ppa.NOTES = {n: 440.0 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}

    jobs = []
    if options.scan:
        for unit_dir in sorted(batch.glob("sessions/*/units/*")):
            wav = unit_dir / "export.wav"
            if not wav.is_file():
                continue
            name = unit_dir.name
            try:
                note = int(name.split("-")[0][1:])
                velocity = int(name.split("-")[1][1:])
                rate = int(name.split("-")[2])
                rep = int(name.split("-")[3].replace("rep", ""))
            except (IndexError, ValueError):
                continue
            if note in notes:
                jobs.append((unit_dir.parent.parent.name, note, rate, rep, velocity, wav))
    else:
        for session, note, rate, rep in preset["sessions"]:
            if note not in notes:
                continue
            for velocity in velocities:
                unit = f"n{note}-v{velocity}-{rate}-rep{rep}"
                jobs.append((session, note, rate, rep, velocity,
                             batch / "sessions" / session / "units" / unit / "export.wav"))

    rows = []
    for session, note, rate, rep, velocity, path in jobs:
        unit = f"n{note}-v{velocity}-{rate}-rep{rep}"
        if not path.is_file():
            rows.append({"unit": unit, "error": "missing"})
            continue
        try:
            with_refined = analyze_variant(path, note, True)
        except Exception as error:  # noqa: BLE001 - 记录不收敛单元而不中断扫描
            rows.append({"unit": unit, "error": f"refined: {error}"})
            continue
        try:
            without = analyze_variant(path, note, False)
        except Exception as error:  # noqa: BLE001
            rows.append({"unit": unit, "error": f"ab: {error}",
                         "adopted": with_refined["W1"]["adopted"]})
            continue
        row = {"unit": unit, "note": note, "velocity": velocity, "rate": rate,
               "rep": rep, "adopted": with_refined["W1"]["adopted"]}
        a = dict(zip(without["W1"]["numbers"], without["W1"]["observed"]))
        b = dict(zip(with_refined["W1"]["numbers"], with_refined["W1"]["observed"]))
        common = sorted(set(a) & set(b))
        worst = 0.0
        worst_n = None
        for n in common:
            if a[n] > 0 and b[n] > 0:
                delta = abs(1200 * math.log2(b[n] / a[n]))
                if delta > worst:
                    worst, worst_n = delta, n
        row["numbers_changed"] = (sorted(a) != sorted(b))
        row["added_partials"] = sorted(set(b) - set(a))
        row["removed_partials"] = sorted(set(a) - set(b))
        row["common_partials"] = len(common)
        row["max_partial_delta_cents"] = worst
        row["max_delta_partial"] = worst_n
        row["f1_delta_cents"] = 1200 * math.log2(with_refined["W1"]["f1"] / without["W1"]["f1"])
        row["B_rel_pct"] = (with_refined["W1"]["B"] - without["W1"]["B"]) / without["W1"]["B"] * 100.0
        rows.append(row)

    report = {"schema": "devpiano-task39-2-refinement-audit",
              "batch": str(batch), "preset": options.preset, "rows": rows}
    (out_dir / "refinement-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    affected = [r for r in rows if r.get("adopted") == "refined" and
                r.get("max_partial_delta_cents", 0.0) >= 0.5]
    changed_numbers = [r for r in rows if r.get("numbers_changed")]
    print(f"units: {len(rows)}  refined adopted: {sum(1 for r in rows if r.get('adopted')=='refined')}"
          f"  numbers changed: {len(changed_numbers)}  affected (>=0.5 cent): {len(affected)}")
    for row in sorted(affected, key=lambda r: -r["max_partial_delta_cents"]):
        print(f"  {row['unit']}: n{row['max_delta_partial']} delta={row['max_partial_delta_cents']:.3f} c"
              f"  f1_delta={row['f1_delta_cents']:+.3f} c  B_rel={row['B_rel_pct']:+.3f}%"
              f"  numbers_changed={row['numbers_changed']}")
    for row in changed_numbers:
        print(f"  [numbers changed] {row['unit']} adopted={row.get('adopted')}")


if __name__ == "__main__":
    main()
