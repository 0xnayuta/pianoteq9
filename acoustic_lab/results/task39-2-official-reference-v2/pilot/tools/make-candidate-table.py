#!/usr/bin/env python3
"""从 devpiano 生产表 Piano88KeyTable.h 复算 88 键候选表（只读；log 段间线性插值）。

用途：为验证批次冻结候选表——数值与 `Piano88KeyTable.h` 的 `computePianoNoteParams`
第 4 段（`logPieceWiseInterp`，21–108 全范围）一致；输出格式与既有候选表相同（table_88）。
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

SOURCE = "/root/repos/devpiano/source/Audio/Piano88KeyTable.h"


def parse_table(path):
    text = Path(path).read_text()
    m_midi = re.search(r"bMidi\[19\]\s*=\s*\{([^}]*)\}", text, re.S)
    m_vals = re.search(r"bVals\[19\]\s*=\s*\{([^}]*)\}", text, re.S)
    if not m_midi or not m_vals:
        raise SystemExit("bMidi/bVals not found in source")
    midi = [float(v.strip().rstrip("fF")) for v in m_midi.group(1).split(",") if v.strip()]
    vals = [float(v.strip().rstrip("fF")) for v in m_vals.group(1).split(",") if v.strip()]
    if len(midi) != 19 or len(vals) != 19:
        raise SystemExit(f"expected 19 anchors, got {len(midi)}/{len(vals)}")
    return midi, vals


def log_interp(midi_value, midi_points, value_points):
    if midi_value <= midi_points[0]:
        return value_points[0]
    if midi_value >= midi_points[-1]:
        return value_points[-1]
    for i in range(1, len(midi_points)):
        if midi_value <= midi_points[i]:
            t = (midi_value - midi_points[i - 1]) / (midi_points[i] - midi_points[i - 1])
            la, lb = math.log(value_points[i - 1]), math.log(value_points[i])
            return math.exp(la + t * (lb - la))
    return value_points[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--out", required=True)
    options = parser.parse_args()
    midi_points, value_points = parse_table(options.source)
    table = [{"midi": m, "candidate_B": log_interp(m, midi_points, value_points)}
             for m in range(21, 109)]
    payload = {
        "schema": "devpiano-task39-2-candidate-table",
        "source": options.source,
        "source_sha256": hashlib.sha256(Path(options.source).read_bytes()).hexdigest(),
        "anchors": {"bMidi": midi_points, "bVals": value_points},
        "table_88": table,
    }
    Path(options.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {options.out}: {len(table)} keys; source sha256 {payload['source_sha256']}")


if __name__ == "__main__":
    main()
