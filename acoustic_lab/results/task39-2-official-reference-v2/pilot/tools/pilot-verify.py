#!/usr/bin/env python3
"""Task 39-2 v2 Pilot 单元核验工具。

子命令：
  compare  比对两份 getParameters 快照（215 项），输出漂移报告（drift != 0 即不一致）
  unit     核验一个导出单元的完整证据集，输出 acceptance.json（接受/拒收 + 原因）

单元核验双层断言（constraints v2）：
  1. pre-export 快照 == post-export 快照（同一会话内不得漂移）
  2. pre-export 快照 == 认证导出基线（FXP 加载后的 215 项认证状态）

WAV 断言：24-bit、目标采样率、双声道、时长在协议窗口内。
只读输入证据；只写 --out 指定的 JSON（unit 子命令默认写 <unit-dir>/acceptance.json）。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_PARAM_COUNT = 215


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def load_parameters(path: Path):
    """接受三种参数快照载体：裸 list、带 result 的 dict、rpc-call 证据（含 response_raw）。"""
    data = read_json(path)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "response_raw" in data:
        raw = data["response_raw"]
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        items = parsed["result"]
    elif isinstance(data, dict) and "result" in data:
        items = data["result"]
    else:
        raise ValueError("unrecognized parameter snapshot shape: %s" % path)
    if not items or not isinstance(items[0], dict) or "id" not in items[0]:
        raise ValueError("snapshot does not look like getParameters output: %s" % path)
    return items


def compare_parameters(a_items, b_items):
    a_map = {item["id"]: item for item in a_items}
    b_map = {item["id"]: item for item in b_items}
    missing_in_b = sorted(set(a_map) - set(b_map))
    extra_in_b = sorted(set(b_map) - set(a_map))
    differing = []
    for item_id in a_map:
        if item_id not in b_map:
            continue
        left, right = a_map[item_id], b_map[item_id]
        if left.get("text") != right.get("text") or left.get("normalized_value") != right.get("normalized_value"):
            differing.append({
                "id": item_id,
                "a_text": left.get("text"),
                "b_text": right.get("text"),
                "a_normalized": left.get("normalized_value"),
                "b_normalized": right.get("normalized_value"),
            })
    differing.sort(key=lambda entry: entry["id"])
    drift_count = len(differing) + len(missing_in_b) + len(extra_in_b)
    return {
        "count_a": len(a_map),
        "count_b": len(b_map),
        "drift_count": drift_count,
        "identical": drift_count == 0 and len(a_map) == len(b_map),
        "missing_in_b": missing_in_b,
        "extra_in_b": extra_in_b,
        "differing": differing,
    }


def cmd_compare(args) -> int:
    a_items = load_parameters(Path(args.a))
    b_items = load_parameters(Path(args.b))
    report = {
        "schema": "devpiano-task39-2-pilot-parameter-compare",
        "label": args.label,
        "a": args.a,
        "b": args.b,
        "checked_utc": now_utc(),
    }
    report.update(compare_parameters(a_items, b_items))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("compare %s vs %s: drift_count=%d identical=%s" % (args.a, args.b, report["drift_count"], report["identical"]))
    for entry in report["differing"]:
        print("  %-32s %r -> %r" % (entry["id"], entry["a_text"], entry["b_text"]))
    for item_id in report["missing_in_b"]:
        print("  missing in b: %s" % item_id)
    for item_id in report["extra_in_b"]:
        print("  extra in b: %s" % item_id)
    return 0 if report["identical"] else 1


def cmd_unit(args) -> int:
    unit_dir = Path(args.unit_dir)
    reasons = []

    pre_items = load_parameters(unit_dir / args.pre_name)
    post_items = load_parameters(unit_dir / args.post_name)
    drift = compare_parameters(pre_items, post_items)
    if drift["count_a"] != EXPECTED_PARAM_COUNT or drift["count_b"] != EXPECTED_PARAM_COUNT:
        reasons.append("parameter_count_mismatch pre=%d post=%d expected=%d"
                       % (drift["count_a"], drift["count_b"], EXPECTED_PARAM_COUNT))
    if drift["drift_count"] != 0:
        reasons.append("pre_post_drift=%d" % drift["drift_count"])

    baseline_items = load_parameters(Path(args.baseline))
    baseline_drift = compare_parameters(baseline_items, pre_items)
    if baseline_drift["drift_count"] != 0:
        reasons.append("pre_vs_baseline_drift=%d" % baseline_drift["drift_count"])

    wav_receipt = read_json(unit_dir / args.wav_name)
    wav = {
        "sha256": wav_receipt.get("sha256"),
        "bytes": wav_receipt.get("bytes"),
        "channels": wav_receipt.get("channels"),
        "bit_depth": wav_receipt.get("bit_depth"),
        "sample_rate": wav_receipt.get("sample_rate"),
        "frames": wav_receipt.get("frames"),
        "duration_seconds": wav_receipt.get("duration_seconds"),
    }
    if not wav["sha256"] or not SHA256_RE.match(str(wav["sha256"])):
        reasons.append("wav_sha256_invalid")
    if not wav["bytes"] or wav["bytes"] <= 0:
        reasons.append("wav_bytes_invalid")
    if wav["bit_depth"] != args.bits:
        reasons.append("wav_bit_depth=%s expected=%d" % (wav["bit_depth"], args.bits))
    if wav["sample_rate"] != args.rate:
        reasons.append("wav_sample_rate=%s expected=%d" % (wav["sample_rate"], args.rate))
    if wav["channels"] != 2:
        reasons.append("wav_channels=%s expected=2" % (wav["channels"],))
    duration = wav["duration_seconds"]
    if duration is None or not (args.min_seconds <= duration <= args.max_seconds):
        reasons.append("wav_duration=%s outside [%s, %s]" % (duration, args.min_seconds, args.max_seconds))

    acceptance = {
        "schema": "devpiano-task39-2-pilot-unit-acceptance",
        "unit": unit_dir.name,
        "checked_utc": now_utc(),
        "expected": {"rate": args.rate, "bits": args.bits,
                     "duration_seconds": [args.min_seconds, args.max_seconds]},
        "pre_post_drift": drift,
        "pre_vs_baseline_drift": baseline_drift,
        "wav": wav,
        "accepted": not reasons,
        "reasons": reasons,
    }
    out = Path(args.out) if args.out else unit_dir / "acceptance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(acceptance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("unit %s: accepted=%s" % (unit_dir.name, acceptance["accepted"]))
    for reason in reasons:
        print("  REJECT: %s" % reason)
    for entry in drift["differing"]:
        print("  drift %-30s %r -> %r" % (entry["id"], entry["a_text"], entry["b_text"]))
    for entry in baseline_drift["differing"]:
        print("  baseline %-27s %r -> %r" % (entry["id"], entry["a_text"], entry["b_text"]))
    return 0 if acceptance["accepted"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_compare = sub.add_parser("compare", help="比对两份 getParameters 快照")
    p_compare.add_argument("--a", required=True)
    p_compare.add_argument("--b", required=True)
    p_compare.add_argument("--out", required=True)
    p_compare.add_argument("--label", default="")
    p_compare.set_defaults(func=cmd_compare)

    p_unit = sub.add_parser("unit", help="核验一个导出单元")
    p_unit.add_argument("--unit-dir", required=True)
    p_unit.add_argument("--rate", type=int, choices=(44100, 48000), required=True)
    p_unit.add_argument("--bits", type=int, default=24)
    p_unit.add_argument("--min-seconds", type=float, default=5.2)
    p_unit.add_argument("--max-seconds", type=float, default=5.6)
    p_unit.add_argument("--baseline", required=True, help="认证导出状态参数快照 JSON")
    p_unit.add_argument("--pre-name", default="pre-parameters.json")
    p_unit.add_argument("--post-name", default="post-parameters.json")
    p_unit.add_argument("--wav-name", default="wav-receipt.json")
    p_unit.add_argument("--out", default="")
    p_unit.set_defaults(func=cmd_unit)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("verify failed: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
