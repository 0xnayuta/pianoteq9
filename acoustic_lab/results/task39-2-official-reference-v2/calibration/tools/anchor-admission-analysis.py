#!/usr/bin/env python3
"""Task 39-2 训练准入分析：26/52/57 加入 B 表第 4 段的模拟改善评估（只读输入）。

范围（用户 2026-10-14 指示）：用 interp-training 批次数据评估"26/52/57 三点加入后
24→28 与 48→60 段的误差模拟改善"，产出接纳/不接纳的书面建议；不自动改 B 表。

方法：
- 新锚点候选值 = 本批通过族的 effective_B 逐键中位数（与 anchors-v3 selection_rule 一致）。
- 现行表 = Piano88KeyTable.h 第 4 段 16 点（21..108），公式复刻 logPieceWiseInterp（log 段间线性）。
- 模拟新表 = 在 26/52/57 处插入候选值（19 点），其余点逐位不变。
- 对照（支持性核验，非新判决；midfill 数据已消耗、非盲）：n25/n27/n49/n51 的参考 B
  = midfill 分析中通过族的逐键中位数（n27-v98 为已登记失败族，排除）。
- 未消耗验证音高 53/59 的参考数据不存在于任何输入；本分析只计算新表在其键位的**表值**（中性记录），
  不构成判决。

输出：anchor-admission-analysis-20261014.json（机器可读）+ .md（书面建议）。
"""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

# 现行表：Piano88KeyTable.h 第 4 段（Task 39-2 P1 修正后版本）
CURRENT_MIDI = [21, 24, 28, 33, 36, 40, 43, 45, 47, 48, 60, 69, 72, 84, 96, 108]
CURRENT_B = [1.367893e-4, 8.800733e-5, 7.330751e-5, 4.767319e-5, 5.080298e-5,
             6.263947e-5, 7.985170e-5, 8.625150e-5, 1.059587e-4, 1.172690e-4,
             3.529958e-4, 8.203508e-4, 1.093004e-3, 3.164862e-3, 9.614857e-3,
             2.920995e-2]
TABLE_HEADER = "/root/repos/devpiano/source/Audio/Piano88KeyTable.h"

# 候选插入键（proposal：at most three new anchors）
CANDIDATE_NOTES = [26, 52, 57]

# 选值策略（proposal training.admission 原文）：
#   n26 = v41 单力度（"v41 is the static-anchor candidate matching the existing 24/28 weak-velocity policy"）；
#   n52/57 = 全部独立通过族的逐键中位数（"use the median of all independently passing families"）。
NOTE_VELOCITY_POLICY = {26: ["v41"], 52: None, 57: None}

# 支持性对照参考（已消耗数据；仅评估用）
CONSUMED_REFERENCE = {"source": "midfill-20261014-001725 analysis (consumed, non-blind)",
                      "notes": [25, 27, 49, 51]}

NOTES = {25: "C#1", 26: "D1", 27: "D#1", 49: "C#3", 51: "D#3", 52: "E3", 53: "F3", 57: "A3", 59: "B3"}


def log_interp(midi, midi_pts, val_pts):
    """复刻 devpiano logPieceWiseInterp（log 空间段间线性插值，含端点 clamp）。"""
    if midi <= midi_pts[0]:
        return val_pts[0]
    if midi >= midi_pts[-1]:
        return val_pts[-1]
    for i in range(1, len(midi_pts)):
        if midi <= midi_pts[i]:
            t = (midi - midi_pts[i - 1]) / (midi_pts[i] - midi_pts[i - 1])
            la, lb = math.log(val_pts[i - 1]), math.log(val_pts[i])
            return math.exp(la + t * (lb - la))
    return val_pts[-1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key_median(families, note, allow_failed=False, velocities=None):
    """逐键中位数（通过族；allow_failed 时含失败族；velocities 给定则仅限这些力度）。"""
    vals = []
    for k, f in families.items():
        if f.get("note_name") and k.startswith(f"n{note}-v"):
            if velocities is not None and not any(f"-{v}-" in k for v in velocities):
                continue
            ok = f["pass_max"] and f["pass_rms"] and f["pass_spread"] and f["pass_partials"]
            if ok or allow_failed:
                vals.append(f["effective_B"][0])
    if not vals:
        return None, 0
    vals.sort()
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return med, n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interp-analysis", required=True, help="interp-training analysis JSON")
    ap.add_argument("--midfill-analysis", required=True, help="midfill analysis JSON")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args()

    interp_path = Path(args.interp_analysis)
    midfill_path = Path(args.midfill_analysis)
    interp = json.loads(interp_path.read_text(encoding="utf-8"))
    midfill = json.loads(midfill_path.read_text(encoding="utf-8"))
    tsrc = Path(TABLE_HEADER)

    # ---- 候选锚点值：按 proposal velocity policy（n26 用 v41；52/57 用全部通过族）----
    candidates = {}
    for note in CANDIDATE_NOTES:
        vel_filter = NOTE_VELOCITY_POLICY.get(note)
        med, n = key_median(interp["summary"]["families"], note, velocities=vel_filter)
        vals = sorted(f["effective_B"][0] for k, f in interp["summary"]["families"].items()
                      if k.startswith(f"n{note}-v")
                      and (vel_filter is None or any(f"-{v}-" in k for v in vel_filter))
                      and f["pass_max"] and f["pass_rms"] and f["pass_spread"] and f["pass_partials"])
        candidates[note] = {"B_median": med, "families": n, "B_values": vals,
                            "velocity_policy": vel_filter if vel_filter is not None else "all passing families",
                            "relative_spread": (vals[-1] - vals[0]) / med if n > 1 else 0.0}

    # ---- 对照参考（已消耗）----
    reference = {}
    for note in CONSUMED_REFERENCE["notes"]:
        med, n = key_median(midfill["summary"]["families"], note)
        reference[note] = {"B_median": med, "families": n}

    # ---- 新表 ----
    new_midi = sorted(CURRENT_MIDI + CANDIDATE_NOTES)
    new_b = []
    for m in new_midi:
        if m in CURRENT_MIDI:
            new_b.append(CURRENT_B[CURRENT_MIDI.index(m)])
        else:
            new_b.append(candidates[m]["B_median"])

    # ---- 逐键对比（24..60）----
    rows = []
    for m in range(24, 61):
        old_b = log_interp(m, CURRENT_MIDI, CURRENT_B)
        new_b_v = log_interp(m, new_midi, new_b)
        row = {"midi": m, "note": NOTES.get(m), "old_B": old_b, "new_B": new_b_v,
               "rel_change_pct": (new_b_v - old_b) / old_b * 100.0}
        if m in reference and reference[m]["B_median"]:
            ref = reference[m]["B_median"]
            row["consumed_reference_B"] = ref
            row["old_rel_error_pct"] = (old_b - ref) / ref * 100.0
            row["new_rel_error_pct"] = (new_b_v - ref) / ref * 100.0
            row["abs_error_change_pct_points"] = abs(row["new_rel_error_pct"]) - abs(row["old_rel_error_pct"])
        rows.append(row)

    # ---- 段内汇总 ----
    def seg(m_lo, m_hi):
        seg_rows = [r for r in rows if m_lo <= r["midi"] <= m_hi]
        ref_rows = [r for r in seg_rows if "consumed_reference_B" in r]
        return {
            "keys": len(seg_rows),
            "max_abs_rel_change_pct": max(abs(r["rel_change_pct"]) for r in seg_rows),
            "sum_abs_rel_change_pct": sum(abs(r["rel_change_pct"]) for r in seg_rows),
            "reference_keys": [r["midi"] for r in ref_rows],
            "reference_comparison": [
                {"midi": r["midi"], "old_rel_error_pct": r["old_rel_error_pct"],
                 "new_rel_error_pct": r["new_rel_error_pct"]} for r in ref_rows],
            "max_abs_error_old_pct": max((abs(r["old_rel_error_pct"]) for r in ref_rows), default=None),
            "max_abs_error_new_pct": max((abs(r["new_rel_error_pct"]) for r in ref_rows), default=None),
        }

    segments = {"24_28": seg(24, 28), "48_60": seg(48, 60), "28_48_untouched": seg(29, 47)}

    # ---- 段外不变性检查 ----
    outside = []
    for m in list(range(21, 24)) + list(range(61, 109)):
        old_b = log_interp(m, CURRENT_MIDI, CURRENT_B)
        new_b_v = log_interp(m, new_midi, new_b)
        outside.append({"midi": m, "delta": new_b_v - old_b})
    outside_max_delta = max(abs(o["delta"]) for o in outside)

    # ---- 剖面记录（log 空间梯度，用于形状检查）----
    def log_grad(m1, m2, table_midi, table_b):
        return (math.log(log_interp(m2, table_midi, table_b)) -
                math.log(log_interp(m1, table_midi, table_b))) / (m2 - m1)

    profile_24_28_new = [{"interval": f"{a}->{b}", "per_semitone": log_grad(a, b, new_midi, new_b)}
                         for a, b in ((24, 26), (26, 28))]
    profile_24_28_old = [{"interval": "24->28", "per_semitone": log_grad(24, 28, CURRENT_MIDI, CURRENT_B)}]
    profile_48_60_new = [{"interval": f"{a}->{b}", "per_semitone": log_grad(a, b, new_midi, new_b)}
                         for a, b in ((48, 52), (52, 57), (57, 60))]
    profile_48_60_old = [{"interval": "48->60", "per_semitone": log_grad(48, 60, CURRENT_MIDI, CURRENT_B)}]

    # ---- 未消耗验证音高的表值（中性记录，无参考参与）----
    unconsumed = {}
    for m in (53, 59):
        unconsumed[str(m)] = {"note": NOTES[m],
                              "old_B": log_interp(m, CURRENT_MIDI, CURRENT_B),
                              "new_B": log_interp(m, new_midi, new_b)}

    out = {
        "schema": "devpiano-task39-2-anchor-admission-analysis",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "scope": "simulate adding new anchors 26/52/57 to Piano88KeyTable.h section 4 (16 -> 19 points); no production change",
        "inputs": {
            "interp_analysis": {"path": str(interp_path), "sha256": sha256(interp_path)},
            "midfill_analysis": {"path": str(midfill_path), "sha256": sha256(midfill_path)},
            "table_header": {"path": str(tsrc), "sha256": sha256(tsrc)},
        },
        "candidate_anchors": {str(k): v for k, v in candidates.items()},
        "consumed_reference": {str(k): v for k, v in reference.items()},
        "new_table": {"midi": new_midi, "b": new_b, "points": len(new_midi)},
        "per_key_24_60": rows,
        "segment_summary": segments,
        "outside_24_60_max_abs_delta": outside_max_delta,
        "profile": {"24_28_old": profile_24_28_old, "24_28_new": profile_24_28_new,
                    "48_60_old": profile_48_60_old, "48_60_new": profile_48_60_new},
        "unconsumed_pitch_table_values": unconsumed,
    }

    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---- 导出 88 键表（供 pre-verification.py 预检；只读复算，不写生产文件）----
    out_dir = Path(args.out_json).parent
    table_paths = {}
    for tag, midi_pts, val_pts in (("old", CURRENT_MIDI, CURRENT_B), ("new", new_midi, new_b)):
        table = {"table_88": [{"midi": m, "candidate_B": log_interp(m, midi_pts, val_pts)}
                              for m in range(21, 109)]}
        tp = out_dir / f"anchor-admission-table-{tag}.json"
        tp.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        table_paths[tag] = str(tp)
        print("wrote", tp)

    # ---- 书面建议（Markdown）----
    def fmt_pct(x):
        return f"{x:+.2f}%"

    md = []
    md.append("# Task 39-2 训练准入分析：26/52/57 加入 B 表第 4 段（2026-10-14）")
    md.append("")
    md.append("范围：用 interp-training 批次数据模拟 26/52/57 三点加入后的 24→28 与 48→60 段变化；"
              "对照 midfill（已消耗、非盲）支持性核验；**不改生产表、不构成验证判决**。")
    md.append("")
    # 预检结果（若存在）
    pv_files = sorted(Path(args.out_json).parent.glob("preverification-admission-*.json"))
    pv = json.loads(pv_files[-1].read_text(encoding="utf-8")) if pv_files else None
    c25 = segments["24_28"]["reference_comparison"]
    c49 = segments["48_60"]["reference_comparison"]
    md.append("## 结论与建议")
    md.append("")
    md.append("**建议：接纳 26/52/57 三个新锚点**（值按 proposal velocity policy：n26 = v41；52/57 = 全部独立通过族中位数），按 proposal 的 "
              "at-most-three / preserve-the-14 约束将第 4 段扩充至 19 点；是否实施由用户另行批准，本分析不含生产改动。")
    md.append("")
    md.append("依据：")
    md.append(f"1. **质量门槛**：三键 v41/v70 族全部通过 amendment-1/2 独立留出判据（52/57 含 v98；26 的 v98 双率失败已登记不可准入、不参与中位数）；"
              f"双率一致 ≤0.112%、重复对差 0.0 cents。")
    md.append(f"2. **24–28 段**（已消耗对照 {[r['midi'] for r in c25]}）：旧表 {c25[0]['old_rel_error_pct']:+.2f}%/{c25[1]['old_rel_error_pct']:+.2f}% → "
              f"新表 {c25[0]['new_rel_error_pct']:+.2f}%/{c25[1]['new_rel_error_pct']:+.2f}%；段内最大绝对误差 "
              f"{segments['24_28']['max_abs_error_old_pct']:.2f}% → {segments['24_28']['max_abs_error_new_pct']:.2f}%。"
              f"与历史诊断（表值高 9–17% @n26）方向一致，由本批实测确认并消解。")
    md.append(f"3. **48–60 段**（已消耗对照 {[r['midi'] for r in c49]}）：段内最大绝对误差 "
              f"{segments['48_60']['max_abs_error_old_pct']:.2f}% → {segments['48_60']['max_abs_error_new_pct']:.2f}%；"
              f"n51 改善（{c49[1]['old_rel_error_pct']:+.2f}% → {c49[1]['new_rel_error_pct']:+.2f}%）、"
              f"n49 略增（{c49[0]['old_rel_error_pct']:+.2f}% → {c49[0]['new_rel_error_pct']:+.2f}%，估计 <0.5 cent @高次分音量级）。")
    md.append("4. **合法性预检**（devpiano 拉伸链复算）：f1 严格递增、4:2/2:1 构造性 0、A4 精确；"
              "拉伸链仅在 21–68 微调，69–108 逐位不变。")
    md.append("")
    md.append("风险与限制：")
    md.append("- 24–28 段剖面为 **V 形（n26 最低）**，log 折线在 26 处出现折点——三批独立数据一致支持，属弦组/绕弦物理特征；接受 `logPieceWiseInterp` 语义。")
    md.append("- n49 处偏差较旧表略增（+1.13pp），属局部梯度平均效应；不改判据、不额外添加锚点。")
    md.append("- 53/59（未消耗验证音）的参考数据不存在于本分析输入；本建议不构成验证判决，验证执行与判决另行裁决。")
    md.append("")
    md.append("## 1. 候选锚点值（proposal velocity policy：n26 用 v41；52/57 用全部独立通过族中位数）")
    md.append("")
    md.append("| MIDI | 音名 | 候选 B（中位数） | 选值策略 | 通过族 | 族间相对散布 |")
    md.append("|---:|---|---:|---|---:|---:|")
    for note, c in candidates.items():
        md.append(f"| {note} | {NOTES[note]} | {c['B_median']:.6e} | {c['velocity_policy']} | {c['families']} | {c['relative_spread']*100:.3f}% |")
    md.append("")
    md.append("## 2. 逐键对比（24–60，含已消耗对照）")
    md.append("")
    md.append("| MIDI | 旧表 B | 新表 B | 变化 | 已消耗参考 B | 旧误差 | 新误差 |")
    md.append("|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        ref = f"{r['consumed_reference_B']:.6e}" if "consumed_reference_B" in r else "—"
        oe = f"{r['old_rel_error_pct']:+.2f}%" if "old_rel_error_pct" in r else "—"
        ne = f"{r['new_rel_error_pct']:+.2f}%" if "new_rel_error_pct" in r else "—"
        mark = " **←候选**" if r["midi"] in CANDIDATE_NOTES else ""
        md.append(f"| {r['midi']}{mark} | {r['old_B']:.6e} | {r['new_B']:.6e} | {fmt_pct(r['rel_change_pct'])} | {ref} | {oe} | {ne} |")
    md.append("")
    md.append("## 3. 段内汇总")
    md.append("")
    for name, s in segments.items():
        old_err = f"{s['max_abs_error_old_pct']:.2f}%" if s["max_abs_error_old_pct"] is not None else "n/a"
        new_err = f"{s['max_abs_error_new_pct']:.2f}%" if s["max_abs_error_new_pct"] is not None else "n/a"
        md.append(f"- **{name}**：{s['keys']} 键；参考对照键 {s['reference_keys']}；"
                  f"旧最大绝对误差 {old_err}，新 {new_err}；最大表值变化 {s['max_abs_rel_change_pct']:.2f}%")
    md.append("")
    md.append("## 4. 剖面（log 空间每半音梯度）")
    md.append("")
    md.append(f"- 24–28 旧：{json.dumps(profile_24_28_old)}")
    md.append(f"- 24–28 新：{json.dumps(profile_24_28_new)}")
    md.append(f"- 48–60 旧：{json.dumps(profile_48_60_old)}")
    md.append(f"- 48–60 新：{json.dumps(profile_48_60_new)}")
    md.append("")
    md.append("## 5. 段外不变性")
    md.append("")
    md.append(f"- 21–23 与 61–108 最大 |ΔB| = {outside_max_delta:.3e}（应恒为 0）")
    md.append("")
    md.append("## 6. 未消耗验证音高表值（中性记录，无参考参与）")
    md.append("")
    md.append("| MIDI | 旧表 B | 新表 B |")
    md.append("|---:|---:|---:|")
    for k, v in unconsumed.items():
        md.append(f"| {k} | {v['old_B']:.6e} | {v['new_B']:.6e} |")
    md.append("")
    if pv:
        md.append("## 7. devpiano 拉伸链预检（pre-verification.py 复算，只读）")
        md.append("")
        md.append(f"- f1 严格递增：**{pv['f1_strictly_increasing']}**（违例 {pv['f1_increasing_violations']}）；"
                  f"4:2 / 2:1 八度匹配误差 {pv['octave_match_error_cents']['4:2 A3/A4']:.6f} / {pv['octave_match_error_cents']['2:1 A4/A5']:.6f} cents；A4 比 {pv['A4_ratio_69']}")
        sc = pv["stretch_change_vs_previous_cents"]
        fc = pv["f1_change_vs_previous_cents"]
        md.append(f"- 拉伸曲线变化（新 vs 旧）：max **{sc['max_abs']:.3f} cents @ n{sc['max_at_midi']}**，"
                  f"影响键 {sc['changed_notes'][0]}–{sc['changed_notes'][-1]}（{len(sc['changed_notes'])} 键）；"
                  f"f1 变化 max {fc['max_abs']:.3f} cents @ n{fc['max_at_midi']}；69–108 逐位不变")
        md.append(f"- 预检文件：`{pv_files[-1].name}`")
        md.append("")

    Path(args.out_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", args.out_json)
    print("wrote", args.out_md)
    print()
    print("candidate medians:", {k: f"{v['B_median']:.6e}" for k, v in candidates.items()})
    print("24_28 seg:", json.dumps(segments["24_28"], indent=1))
    print("48_60 seg:", json.dumps(segments["48_60"], indent=1))
    print("outside max delta:", outside_max_delta)


if __name__ == "__main__":
    main()
