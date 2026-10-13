#!/usr/bin/env python3
"""生成 Task 39-2 高音区先导采集（register pilot）的 9 个受控 MIDI 激励。

与 pilot 版 `make-stimulus.py` 逐位同构（55 字节 format-0 SMF、PPQ 480、
tempo 500000、onset 0.1 s、release 4.2 s、end 5.2 s、channel 1、无踏板 CC）。
默认音符 72/84/96（C5/C6/C7），速度 41/70/98。

自检：`build_mid(69, 70)` 的字节必须与认证参考 A4-v70.mid 逐位一致
（SHA-256 9e4827ed…），以证明本生成器与 pilot 认证结构等价。
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PPQ = 480
TEMPO_US = 500000
ONSET_TICKS = 96          # 0.1 s @ 120 BPM
NOTE_OFF_TICKS = 4032     # 4.2 s @ 120 BPM（绝对 tick）
END_TICKS = 4992          # 5.2 s @ 120 BPM（绝对 tick）
CHANNEL = 0               # MIDI channel 1（0-based）
NOTE_OFF_VELOCITY = 0

REGISTER_NOTES = (72, 84, 96)
VELOCITIES = (41, 70, 98)

REFERENCE_SHA256 = "9e4827ed6ca1f69cf9d7ab4bd438fbe2b9fd897fe6d3264ea1604c5a04ba1462"


def vlq(value: int) -> bytes:
    """MIDI 可变长度量编码（7 bit/byte，MSB continuation）。"""
    if not 0 <= value <= 0x0FFFFFFF:
        raise ValueError("VLQ out of range: %d" % value)
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def build_mid(note: int, velocity: int) -> bytes:
    """按认证结构构造 55 字节 format-0 SMF。"""
    events = b"".join([
        b"\x00\xff\x51\x03" + TEMPO_US.to_bytes(3, "big"),
        b"\x00\xb0\x40\x00",                                  # CC64 sustain = 0
        b"\x00\xb0\x42\x00",                                  # CC66 sostenuto = 0
        b"\x00\xb0\x43\x00",                                  # CC67 soft = 0
        vlq(ONSET_TICKS) + bytes([0x90 | CHANNEL, note, velocity]),
        vlq(NOTE_OFF_TICKS - ONSET_TICKS) + bytes([0x80 | CHANNEL, note, NOTE_OFF_VELOCITY]),
        vlq(END_TICKS - NOTE_OFF_TICKS) + b"\xff\x2f\x00",    # end of track
    ])
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + PPQ.to_bytes(2, "big")
    return header + b"MTrk" + len(events).to_bytes(4, "big") + events


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, help="输出目录（MIDI 与 receipt.json）")
    parser.add_argument("--reference", required=True, help="认证参考 A4-v70.mid 路径（逐位对照）")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    reference = Path(args.reference)
    if not reference.is_file():
        print("reference missing: %s" % reference, file=sys.stderr)
        return 2
    reference_bytes = reference.read_bytes()
    if sha256_bytes(reference_bytes) != REFERENCE_SHA256:
        print("reference sha256 mismatch: %s" % reference, file=sys.stderr)
        return 2

    # 自检：生成器必须能逐位复刻认证参考（pilot 版与参考的一致性由此继承）
    trial = build_mid(69, 70)
    if trial != reference_bytes:
        print("self-check failed: (69,70) output is not bit-identical to reference", file=sys.stderr)
        print("  generated: %s" % trial.hex(), file=sys.stderr)
        print("  reference: %s" % reference_bytes.hex(), file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for note in REGISTER_NOTES:
        for velocity in VELOCITIES:
            name = "n%d-v%d.mid" % (note, velocity)
            data = build_mid(note, velocity)
            path = out_dir / name
            path.write_bytes(data)
            files.append({"path": name, "note": note, "velocity": velocity,
                          "bytes": len(data), "sha256": sha256_bytes(data)})

    receipt = {
        "schema": "devpiano-task39-2-register-pilot-stimulus",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "pilot/tools/make-stimulus-register.py",
        "notes": list(REGISTER_NOTES),
        "velocities": list(VELOCITIES),
        "parameters": {
            "format": 0, "ppq": PPQ, "tempo_us": TEMPO_US, "channel": 1,
            "onset_s": ONSET_TICKS / PPQ * (TEMPO_US / 1e6),
            "release_s": NOTE_OFF_TICKS / PPQ * (TEMPO_US / 1e6),
            "end_s": END_TICKS / PPQ * (TEMPO_US / 1e6),
            "cc64": 0, "cc66": 0, "cc67": 0, "note_off_velocity": NOTE_OFF_VELOCITY,
        },
        "reference": {
            "path": str(reference),
            "sha256": REFERENCE_SHA256,
            "replication": {"note": 69, "velocity": 70,
                            "bit_identical": True, "sha256": sha256_bytes(trial)},
        },
        "files": files,
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("generated %d stimulus files in %s" % (len(files), out_dir))
    for item in files:
        print("  %-12s %s" % (item["path"], item["sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
