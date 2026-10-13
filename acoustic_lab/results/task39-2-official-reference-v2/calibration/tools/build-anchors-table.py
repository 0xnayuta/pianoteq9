#!/usr/bin/env python3
"""Task 39-2 校准锚点表生成器（只读输入；输出 JSON 候选表，不改任何 devpiano 代码）。

规则（与 anchors-v1/v2 相同，未放宽）：
- anchor：通过全部预登记判据（max<=3 / RMS<=1 / spread<=1 / partials>=5）的族，
  取该键全部通过族 effective_B 的中位数；
- interp：相邻锚点之间在 log(B) 空间线性插值（21-84）；
- model-upper：85-108 从 C6 锚点向保留的模型上界锚点 {96: 4.0e-2, 108: 8.5e-2} 做 log 插值；
- current_B 复刻 devpiano `Piano88KeyTable.h` 的 `computePianoNoteParams` 第 4 段
  （float32 常量、logPieceWiseInterp；此处以 float64 复刻，两版表间口径一致）。

输入：
- --previous anchors-v2.json：继承既有实测锚点（21/24/36/43/45/47/48/60/69/72/84）；
- --analysis anchors2 批次的 partial-analysis-summary.json：新增 28/33/40 锚点。

输出：--out anchors-v3.json（含 measured_anchors / not_admitted / table_88）。
"""

import argparse
import json
import math
import statistics
from pathlib import Path

MODEL_UPPER = {96: 4.0e-2, 108: 8.5e-2}  # 保留的模型上界锚点（无 C6 以上实测证据）
BASS_CURRENT = ([21.0, 33.0, 43.0], [3.1e-4, 2.4e-4, 1.85e-4])
TENOR_CURRENT = ([44.0, 57.0, 69.0, 84.0, 96.0, 108.0],
                 [2.65e-4, 3.2e-4, 8.5e-4, 5.0e-3, 4.0e-2, 8.5e-2])


def log_interp(x, pts, vals):
    if x <= pts[0]:
        return vals[0]
    if x >= pts[-1]:
        return vals[-1]
    for i in range(1, len(pts)):
        if x <= pts[i]:
            t = (x - pts[i - 1]) / (pts[i] - pts[i - 1])
            log_a, log_b = math.log(vals[i - 1]), math.log(vals[i])
            return math.exp(log_a + t * (log_b - log_a))
    return vals[-1]


def current_b(midi):
    if midi <= 43:
        return log_interp(midi, *BASS_CURRENT)
    return log_interp(midi, *TENOR_CURRENT)


def candidate_b(midi, anchors):
    keys = sorted(anchors)
    if midi in anchors:
        return anchors[midi]
    if midi <= keys[0]:
        return anchors[keys[0]]
    if midi > keys[-1]:
        upper_pts = [keys[-1]] + sorted(MODEL_UPPER)
        upper_vals = [anchors[keys[-1]]] + [MODEL_UPPER[k] for k in sorted(MODEL_UPPER)]
        return log_interp(midi, upper_pts, upper_vals)
    for lo, hi in zip(keys, keys[1:]):
        if lo < midi < hi:
            return log_interp(midi, [lo, hi], [anchors[lo], anchors[hi]])
    raise AssertionError(f"unreachable interpolation state for midi {midi}")


def kind_of(midi, anchors):
    if midi in anchors:
        return "anchor"
    if midi <= 20:
        return "clamp"
    if midi > max(anchors):
        return "model-upper"
    return "interp"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", required=True, help="anchors-v2.json（继承既有锚点）")
    parser.add_argument("--analysis", required=True, help="anchors2 partial-analysis-summary.json")
    parser.add_argument("--out", required=True, help="输出 anchors-v3.json")
    options = parser.parse_args()

    previous = json.loads(Path(options.previous).read_text(encoding="utf-8"))
    analysis = json.loads(Path(options.analysis).read_text(encoding="utf-8"))

    anchors = {int(k): v["B_median"] for k, v in previous["measured_anchors"].items()}

    new_notes = [28, 33, 40]
    measured_new = {}
    for note in new_notes:
        values, families = [], []
        for key, family in analysis["families"].items():
            if not key.startswith(f"n{note}-v"):
                continue
            if not (family["pass_max"] and family["pass_rms"]
                    and family["pass_spread"] and family["pass_partials"]):
                continue
            values.extend(family["effective_B"])
            families.append(key)
        if not values:
            raise SystemExit(f"note {note}: no admitted families")
        median = statistics.median(values)
        measured_new[note] = {
            "B_median": median,
            "B_min": min(values),
            "B_max": max(values),
            "relative_spread": (max(values) - min(values)) / median,
            "families": len(values),
            "family_keys": families,
        }
        anchors[note] = median

    table = []
    for midi in range(21, 109):
        cand = candidate_b(midi, anchors)
        cur = current_b(midi)
        table.append({
            "midi": midi,
            "current_B": cur,
            "candidate_B": cand,
            "kind": kind_of(midi, anchors),
            "ratio_candidate_over_current": cand / cur,
        })

    out = {
        "schema": "devpiano-task39-2-calibration-anchors-v3",
        "supersedes": "anchors-v2.json",
        "source_batch": [
            previous.get("source_batch"),
            "phase39/task39-2/anchors2 (n28/33/40 admitted; n91/95 measured, not admitted)",
        ],
        "selection_rule": previous["selection_rule"],
        "interval_rule": previous["interval_rule"],
        "measured_anchors": {**previous["measured_anchors"],
                             **{str(k): v for k, v in measured_new.items()}},
        "not_admitted": {
            "n91": {"reason": "W2 window cannot identify >=5 partials; only v98 W1 converges (n=1..5)",
                     "w1_only_diagnostic": {"B": 5.8292e-03, "f1_Hz": 1567.863,
                                            "note": "v98 both rates agree within 0.03%; single-velocity, single-window; not an anchor"}},
            "n95": {"reason": "no staged match converges in either window from any seed (n>=4 below noise floor)",
                     "w1_only_diagnostic": {"note": "stationary-line identification has no >=5-partial solution"}},
        },
        "table_88": table,
    }
    Path(options.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    prev_table = {item["midi"]: item for item in previous["table_88"]}
    changed = [m for m in range(21, 109)
               if abs(table[m - 21]["candidate_B"] - prev_table[m]["candidate_B"])
               / prev_table[m]["candidate_B"] > 1e-9]
    print(f"anchors: {sorted(anchors)}")
    print(f"new anchors: " + ", ".join(f"n{k}={v['B_median']:.6e}" for k, v in measured_new.items()))
    print(f"table_88 candidate values changed vs v2: {len(changed)} keys ({changed[0]}..{changed[-1]})")


if __name__ == "__main__":
    main()
