#!/usr/bin/env python3
"""Task 39-2 校准候选表预验算（只读；复刻 devpiano 调谐链，不改任何 devpiano 代码）。

复刻对象（`PianoTuning.h` / `Piano88KeyTable.h`，float64 口径）：
- normalizedPianoPartialRatio(B, m) = m * sqrt((1 + B m^2) / (1 + B))
- octaveStretchCents(n) = 1200 log2(lowerRatio / (2 * upperRatio))，lowerPartial = n < 69 ? 4 : 2
- makeStretchRatios()：57-69 / 70-81 线性段 + 56→21 / 82→108 累积段（链式）
- f1(midi) = 等律 440 Hz * stretchRatios[midi]

检查项：邻键 f1 严格递增（21→108）、4:2 / 2:1 八度匹配误差、A4 线 400/440/480 Hz、
锚点键 f1 拉伸范围、候选表相对前版的拉伸曲线变化。

用法：pre-verification.py --table chains/table.json --compare-against 前版.json --out report.json
"""

import argparse
import json
import math
from pathlib import Path

A4_HZ = 440.0


def equal_temperament_freq(midi):
    return A4_HZ * 2.0 ** ((midi - 69) / 12.0)


def partial_ratio(b, m):
    b = max(0.0, b)
    m = max(1, int(m))
    return m * math.sqrt((1.0 + b * m * m) / (1.0 + b))


def octave_stretch_cents(lower_note, table):
    lower_partial = 4 if lower_note < 69 else 2
    upper_partial = lower_partial // 2
    lower_ratio = partial_ratio(table[lower_note], lower_partial)
    upper_ratio = partial_ratio(table[lower_note + 12], upper_partial)
    return 1200.0 * math.log2(lower_ratio / (2.0 * upper_ratio))


def stretch_ratios(table):
    cents = {}
    lower_anchor = -octave_stretch_cents(57, table)
    upper_anchor = octave_stretch_cents(69, table)
    for note in range(57, 70):
        cents[note] = lower_anchor * (69 - note) / 12.0
    for note in range(70, 82):
        cents[note] = upper_anchor * (note - 69) / 12.0
    for note in range(56, 20, -1):
        cents[note] = cents[note + 12] - octave_stretch_cents(note, table)
    for note in range(82, 109):
        cents[note] = cents[note - 12] + octave_stretch_cents(note - 12, table)
    for note in range(0, 21):
        cents[note] = cents[21]
    for note in range(109, 128):
        cents[note] = cents[108]
    return {n: math.exp2(c / 1200.0) for n, c in cents.items()}


def f1_hz(midi, ratios):
    return equal_temperament_freq(midi) * ratios[midi]


def load_table(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    table = {}
    for item in data["table_88"]:
        table[item["midi"]] = item["candidate_B"]
    for note in range(0, 21):
        table[note] = table[21]
    for note in range(109, 128):
        table[note] = table[108]
    return table


def analyse(table):
    ratios = stretch_ratios(table)
    report = {}

    # 1) 邻键 f1 严格递增（21→108）
    f1 = {n: f1_hz(n, ratios) for n in range(21, 109)}
    violations = [n for n in range(21, 108) if f1[n + 1] <= f1[n]]
    report["f1_strictly_increasing"] = not violations
    report["f1_increasing_violations"] = violations

    # 2) 4:2（A3/A4）与 2:1（A4/A5）八度匹配误差（分音比定义，构造性应 ≈0）
    def match_error(down_note, up_note, down_partial, up_partial, table):
        f_down = f1[down_note] * partial_ratio(table[down_note], down_partial)
        f_up = f1[up_note] * partial_ratio(table[up_note], up_partial)
        return 1200.0 * math.log2(f_down / f_up)

    errors = {
        "4:2 A3/A4": match_error(57, 69, 4, 2, table),
        "2:1 A4/A5": match_error(69, 81, 2, 1, table),
    }
    report["octave_match_error_cents"] = {k: round(v, 6) for k, v in errors.items()}

    # 3) A4 线（stretch 在 69 为 0，等律下精确 440；范围检查 400/440/480 近似线性）
    report["A4_ratio_69"] = ratios[69]
    line = {}
    for base in (400.0, 440.0, 480.0):
        scale = base / A4_HZ
        line[f"{base:g}"] = {
            "A4_Hz": A4_HZ * scale * ratios[69],
            "A5_Hz": A4_HZ * scale * equal_temperament_freq(81) / A4_HZ * ratios[81],
        }
    report["A4_line"] = line

    # 4) 锚点键 f1 拉伸（cents，相对等律）
    stretch_cents = {n: 1200.0 * math.log2(ratios[n]) for n in (21, 24, 28, 33, 36, 40, 43, 48, 60, 69, 72, 84, 96, 108)}
    report["anchor_stretch_cents"] = {str(k): round(v, 3) for k, v in stretch_cents.items()}
    return report, ratios, f1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True)
    parser.add_argument("--compare-against", default=None)
    parser.add_argument("--out", required=True)
    options = parser.parse_args()

    table = load_table(options.table)
    report, ratios, f1 = analyse(table)

    if options.compare_against:
        prev_table = load_table(options.compare_against)
        prev_report, prev_ratios, prev_f1 = analyse(prev_table)
        deltas = {n: 1200.0 * math.log2(ratios[n] / prev_ratios[n]) for n in range(21, 109)}
        report["stretch_change_vs_previous_cents"] = {
            "max_abs": max(abs(v) for v in deltas.values()),
            "max_at_midi": max(deltas, key=lambda n: abs(deltas[n])),
            "changed_notes": [n for n in range(21, 109) if abs(deltas[n]) > 1e-9],
        }
        f1_deltas = {n: 1200.0 * math.log2(f1[n] / prev_f1[n]) for n in range(21, 109)}
        changed_f1 = {n: v for n, v in f1_deltas.items() if abs(v) > 1e-9}
        report["f1_change_vs_previous_cents"] = {
            "changed_notes": sorted(changed_f1),
            "max_abs": max((abs(v) for v in changed_f1.values()), default=0.0),
            "max_at_midi": max(changed_f1, key=lambda n: abs(changed_f1[n])) if changed_f1 else None,
        }

    Path(options.out).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "A4_line"}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
