#!/usr/bin/env python3
"""从已认证的 A5 原点证书和实际 MIDI/WAV 生成逐单元 reference-origin timing 报告。

只绑定证书公式：note_on_sample = midi_origin_sample + llround(NoteOn秒 * rate)。
不推断首非零、不做相关对齐、不修改证书或 MIDI。输出报告可由
pilot-partial-analysis.load_timing_report 独立复核。
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path


def _ppa():
    spec = importlib.util.spec_from_file_location(
        "ppa", Path(__file__).with_name("pilot-partial-analysis.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_or_absolute(target, base):
    try:
        return os.path.relpath(str(Path(target).resolve()), str(Path(base).resolve()))
    except ValueError:
        return str(Path(target).resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate", required=True, help="A5 origin-certificate-v1.json")
    parser.add_argument("--midi", required=True, help="actual MIDI stimulus for this unit")
    parser.add_argument("--wav", required=True, help="actual reference WAV for this unit")
    parser.add_argument("--unit", required=True, help="registered unit id")
    parser.add_argument("--out", required=True, help="new timing report path; must not exist")
    parser.add_argument("--note", type=int, default=None,
                        help="expected MIDI note (optional; unique NoteOn otherwise)")
    parser.add_argument("--velocity", type=int, default=None,
                        help="expected MIDI velocity (optional)")
    args = parser.parse_args()

    ppa = _ppa()
    certificate_path = Path(args.certificate)
    midi_path = Path(args.midi)
    wav_path = Path(args.wav)
    out_path = Path(args.out)
    if out_path.exists():
        parser.error("output exists; preserve previous timing report")
    for label, path in (("certificate", certificate_path), ("MIDI", midi_path), ("WAV", wav_path)):
        if not path.is_file():
            parser.error(f"{label} missing: {path}")

    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    if certificate.get("schema") != ppa.REFERENCE_ORIGIN_CERTIFICATE_SCHEMA:
        parser.error("unsupported certificate schema")
    if certificate.get("status") != "authenticated":
        parser.error("certificate is not authenticated")
    origin = certificate.get("midi_origin_sample")
    if not isinstance(origin, int) or isinstance(origin, bool):
        parser.error("certificate has no integer midi_origin_sample")

    timeline = ppa.parse_smf_note_timeline(midi_path, args.note, args.velocity)
    rate, frames, _, _ = ppa.read_wav_stereo(wav_path)
    with wave.open(str(wav_path), "rb") as handle:
        channels = handle.getnchannels()
        bits = handle.getsampwidth() * 8
    if str(rate) not in (certificate.get("rates") or {}):
        parser.error(f"certificate does not cover sample rate {rate}")

    note_on_sample = origin + ppa.llround(timeline["note_on_seconds"] * rate)
    note_off_sample = origin + ppa.llround(timeline["note_off_seconds"] * rate)
    if not 0 <= note_on_sample < note_off_sample <= frames:
        parser.error("certificate formula yields an invalid NoteOn/NoteOff timeline")
    windows = {}
    for name, window in ppa.WINDOWS.items():
        start, stop = ppa.note_on_relative_bounds(window, note_on_sample, rate)
        windows[name] = {"start_sample": start, "stop_sample": stop}

    report = {
        "schema": ppa.REFERENCE_TIMING_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED,
        "unit": args.unit,
        "passed": True,
        "failures": [],
        "reference_origin_certified": True,
        "certificate": {
            "path": _relative_or_absolute(certificate_path, out_path.parent),
            "sha256": _sha256(certificate_path),
            "midi_origin_sample": origin,
        },
        "midi": {
            "path": _relative_or_absolute(midi_path, out_path.parent),
            "sha256": timeline["midi_sha256"],
            "ppq": timeline["ppq"],
            "tempo_us": timeline["tempo_us"],
            "note": timeline["note"],
            "velocity": timeline["velocity"],
            "note_on_tick": timeline["note_on_tick"],
            "note_off_tick": timeline["note_off_tick"],
            "note_on_seconds": timeline["note_on_seconds"],
            "note_off_seconds": timeline["note_off_seconds"],
        },
        "wav": {
            "path": str(wav_path.resolve()),
            "sha256": _sha256(wav_path),
            "rate": rate,
            "frames": frames,
            "channels": channels,
            "bits": bits,
        },
        "wav_sha256": _sha256(wav_path),
        "note_on_sample": note_on_sample,
        "note_off_sample": note_off_sample,
        "windows": windows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        ppa.load_timing_report(out_path, wav_path)
    except Exception as error:
        out_path.unlink()
        print(f"self-check failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote {out_path}")
    print(f"unit={args.unit} note={timeline['note']} velocity={timeline['velocity']} "
          f"rate={rate} note_on_sample={note_on_sample} note_off_sample={note_off_sample}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
