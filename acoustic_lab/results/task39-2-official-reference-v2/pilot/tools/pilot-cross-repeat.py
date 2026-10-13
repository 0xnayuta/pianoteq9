#!/usr/bin/env python3
"""Task 39-2 pilot 批次的跨 repeat 比较（与 pilot-v2 批次 batch-cross-repeat-analysis.json 同口径）。

- 身份判定：整文件 SHA-256 相等即 identical；
- 差异量化：24-bit 带符号样点逐点比较（帧内 L/R 独立计数），
  报告差异样点数/占比、最大与平均 |Δ| LSB、最大 |Δ| dBFS（相对 2^23 满幅）、首个差异帧号。

用法：pilot-cross-repeat.py --batch <批次根> --out <输出 JSON>
只读输入（units/*/export.wav）；只写 --out 指定文件。
"""

import argparse
import hashlib
import json
import math
import re
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def read_i24(path: Path) -> tuple[int, np.ndarray]:
    """返回 (frames, samples)；样点为带符号 24-bit 整数（交错 L/R）。"""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 3:
            raise SystemExit(f"{path}: expected 24-bit PCM, got {wav.getsampwidth() * 8}-bit")
        channels = wav.getnchannels()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    triplets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    values = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
    values = np.where(values & 0x800000, values - 0x1000000, values)
    return frames, values


def compare(a: Path, b: Path) -> dict:
    sha_a, sha_b = sha256(a), sha256(b)
    if sha_a == sha_b:
        return {"verdict": "identical", "sha_a": sha_a, "sha_b": sha_b}
    frames_a, sa = read_i24(a)
    frames_b, sb = read_i24(b)
    if frames_a != frames_b or sa.shape != sb.shape:
        return {"verdict": "length_mismatch", "sha_a": sha_a, "sha_b": sha_b,
                "frames_a": frames_a, "frames_b": frames_b}
    delta = sa - sb
    mask = delta != 0
    diff_samples = int(mask.sum())
    magnitude = np.abs(delta)
    max_delta = int(magnitude.max()) if diff_samples else 0
    mean_delta = float(magnitude[mask].mean()) if diff_samples else 0.0
    first_index = int(np.argmax(mask)) if diff_samples else None
    return {
        "verdict": "differs",
        "sha_a": sha_a,
        "sha_b": sha_b,
        "diff_samples": diff_samples,
        "total_samples": int(sa.size),
        "diff_ratio": round(diff_samples / sa.size, 6),
        "max_delta_lsb": max_delta,
        "max_delta_dbfs": round(20.0 * math.log10(max_delta / 8388608.0), 1) if max_delta else None,
        "mean_delta_lsb": round(mean_delta, 2),
        "first_diff_frame": None if first_index is None else first_index // 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True, help="批次根（WSL 路径）")
    parser.add_argument("--out", required=True, help="输出 JSON（WSL 路径）")
    args = parser.parse_args()

    root = Path(args.batch)
    units: dict[str, dict[str, dict[str, Path]]] = {}
    for acc in sorted(root.glob("sessions/*/units/*/acceptance.json")):
        doc = json.load(open(acc, encoding="utf-8"))
        match = re.match(r"(n\d+)-v(\d+)-(\d+)-rep(\d)$", doc["unit"])
        family = f"{match.group(1)}-{match.group(3)}"
        units.setdefault(family, {}).setdefault(match.group(2), {})[match.group(4)] = acc.parent / "export.wav"

    pairs = []
    for family in sorted(units, key=lambda s: (int(re.match(r"n(\d+)", s).group(1)), int(s.rsplit("-", 1)[1]))):
        for velocity in sorted(units[family], key=int):
            reps = units[family][velocity]
            if set(reps) != {"0", "1"}:
                continue
            row = {"family": family, "velocity": f"v{velocity}"}
            row.update(compare(reps["0"], reps["1"]))
            pairs.append(row)

    differing = [p for p in pairs if p["verdict"] == "differs"]
    identical = [p for p in pairs if p["verdict"] == "identical"]
    summary: dict = {"pairs_total": len(pairs), "identical": len(identical), "differs": len(differing)}
    if differing:
        summary["differs_max_delta_lsb_worst"] = max(p["max_delta_lsb"] for p in differing)
        summary["differs_max_delta_dbfs_worst"] = min(
            p["max_delta_dbfs"] for p in differing if p["max_delta_dbfs"] is not None)
        ratios = sorted(p["diff_ratio"] for p in differing)
        summary["differs_ratio_range"] = f"{ratios[0] * 100:.3f}%-{ratios[-1] * 100:.3f}% of samples"
    doc = {
        "schema": "devpiano-task39-2-register-pilot-cross-repeat-analysis",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": "signed 24-bit sample comparison; full-file sha256 for identity",
        "batch": str(root),
        "pairs": pairs,
        "summary": summary,
    }
    Path(args.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"cross-repeat: {summary['identical']}/{len(pairs)} identical")
    for p in differing:
        print(f"  {p['family']} {p['velocity']}: diff_ratio={p['diff_ratio']} "
              f"max={p['max_delta_lsb']} LSB ({p['max_delta_dbfs']} dBFS) first_frame={p['first_diff_frame']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
