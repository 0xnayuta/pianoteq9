#!/usr/bin/env python3
"""从真实 SMF、PCM 和运行事件独立核验 A4；不估计 B、不产生正式声学判决。"""
import argparse
import hashlib
import json
import math
import struct
import wave
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_stimulus(path, contract):
    """只解析本次声明的固定 SMF，不补事件、不使用生成器实现。"""
    raw = Path(path).read_bytes()
    if len(raw) < 22:
        raise ValueError("Truncated MIDI")
    tag, length, fmt, tracks, ppq = struct.unpack(">4sIHHH", raw[:14])
    expected = contract["midi"]
    if (tag, length, fmt, tracks, ppq) != (b"MThd", 6, expected["format"], expected["tracks"], expected["ppq"]):
        raise ValueError("MIDI header outside contract")
    track_tag, track_length = struct.unpack(">4sI", raw[14:22])
    if track_tag != b"MTrk" or len(raw) != 22 + track_length:
        raise ValueError("MIDI track length differs")
    position, tick, events = 22, 0, []

    def byte():
        nonlocal position
        if position >= len(raw):
            raise ValueError("Truncated MIDI event")
        value = raw[position]
        position += 1
        return value

    while position < len(raw):
        delta = 0
        for _ in range(4):
            value = byte()
            delta = (delta << 7) | (value & 127)
            if value < 128:
                break
        else:
            raise ValueError("Invalid MIDI VLQ")
        tick += delta
        status = byte()
        row = {"tick": tick}
        if status == 255:
            meta, size = byte(), byte()
            payload = bytes(byte() for _ in range(size))
            if meta == 81 and size == 3:
                row.update(kind="tempo", microseconds_per_quarter=int.from_bytes(payload, "big"))
            elif meta == 47 and size == 0:
                row["kind"] = "end_of_track"
            else:
                raise ValueError("Unregistered meta event")
        elif status in (128, 144, 176):
            first, second = byte(), byte()
            if first > 127 or second > 127:
                raise ValueError("Invalid MIDI data byte")
            row["channel"] = (status & 15) + 1
            if status == 176:
                row.update(kind=f"cc{first}", value=second)
            else:
                row.update(kind="note_on" if status == 144 else "note_off", note=first, velocity=second)
        else:
            raise ValueError("Unregistered MIDI event or running status")
        events.append(row)
    planned = expected["events"]
    if [(row["kind"], row["tick"]) for row in events] != [(row["kind"], row["tick"]) for row in planned]:
        raise ValueError("MIDI event timeline differs")
    if events[0]["microseconds_per_quarter"] != expected["tempo_us_per_quarter"]:
        raise ValueError("MIDI tempo differs")
    if any(row.get("channel", 1) != expected["channel"] for row in events):
        raise ValueError("MIDI channel differs")
    if any(row.get("value", 0) != 0 for row in events):
        raise ValueError("Pedal reset differs")
    on, off = events[4:6]
    if not 1 <= on["velocity"] <= 127 or off["note"] != on["note"] or off["velocity"] != 0:
        raise ValueError("Invalid NoteOn/NoteOff identity or velocity")
    return {"sha256": digest(path), "note": on["note"], "velocity": on["velocity"], "events": events}


def read_pcm(path):
    with wave.open(str(path), "rb") as source:
        channels, width, rate, frames = source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()
        data = source.readframes(frames)
        if source.getcomptype() != "NONE" or width not in (2, 3):
            raise ValueError("Expected integer PCM")
    if len(data) != frames * channels * width:
        raise ValueError("Truncated PCM")
    if width == 2:
        samples = np.frombuffer(data, dtype="<i2").astype(np.int32)
    else:
        octets = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        unsigned = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        samples = (unsigned ^ 0x800000) - 0x800000
    return {"rate": rate, "channels": channels, "bits": width * 8, "frames": frames}, samples.reshape(frames, channels)


def verify(midi, wav, receipt_path, contract):
    stimulus = read_stimulus(midi, contract)
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8-sig"))
    metadata, pcm = read_pcm(wav)
    failures = []

    def require(condition, reason):
        if not condition:
            failures.append(reason)

    rate = metadata["rate"]
    require(rate in contract["dev_render"]["sample_rates_hz"], "sample_rate")
    require(metadata["channels"] == 2 and metadata["bits"] == 24, "stereo24")
    scale = contract["midi"]["tempo_us_per_quarter"] / (contract["midi"]["ppq"] * 1000000)
    event_samples = [math.floor(row["tick"] * scale * rate + 0.5) for row in stimulus["events"]]
    on, off, end = event_samples[4:7]
    require(metadata["frames"] == end, "frame_count")
    require(receipt.get("role") == "contract_render", "diagnostic_control_not_admissible")
    require(receipt.get("sample_rate") == rate and receipt.get("frames") == end, "receipt_pcm_metadata")
    require(receipt.get("channels") == 2 and receipt.get("bits_per_sample") == 24, "receipt_pcm_format")
    require(receipt.get("note_on_sample") == on and receipt.get("note_off_sample") == off and receipt.get("end_sample") == end, "receipt_event_times")
    block = receipt.get("block_size")
    require(block in (512, 257), "block_size")
    ledger = receipt.get("events", [])
    planned = stimulus["events"][1:6]
    require(len(ledger) == len(planned), "runtime_event_count")
    for position, (row, planned_event, sample) in enumerate(zip(ledger, planned, event_samples[1:6])):
        for key in ("kind", "tick", "channel", "note", "velocity", "value"):
            if key in planned_event:
                require(row.get(key) == planned_event[key], f"event_{position}_{key}")
        require(row.get("sample") == sample, f"event_{position}_sample")
        if block in (512, 257):
            require(row.get("block_start") == sample // block * block and row.get("block_offset") == sample % block, f"event_{position}_block_offset")
    nonzero = np.flatnonzero(np.any(pcm != 0, axis=1))
    first = int(nonzero[0]) if len(nonzero) else None
    last = int(nonzero[-1]) if len(nonzero) else None
    require(first is not None and on <= first < off, "audible_held_note")
    require(not bool(np.any(pcm[:on])), "pre_note_on_silence")
    require(first == receipt.get("first_nonzero_sample") and last == receipt.get("last_nonzero_sample"), "receipt_actual_sound_boundaries")
    require(receipt.get("key_down_before_note_off") is True and receipt.get("key_down_after_note_off") is False, "actual_note_off_state_transition")
    require(int(np.max(np.abs(pcm))) < 8388607, "unclipped_pcm")
    windows = {}
    for name in ("W1", "W2"):
        left, right = contract["analysis_windows"][name]
        start = on + math.floor(left * rate + 0.5)
        stop = on + math.floor(right * rate + 0.5)
        require(on <= start < stop <= off, name + "_held_window")
        windows[name] = {"start_sample": start, "stop_sample": stop}
    return {"role": "input_and_dev_render_contract_only", "passed": not failures, "failures": failures, "midi": stimulus, "wav": metadata, "wav_sha256": digest(wav), "receipt_sha256": digest(receipt_path), "first_nonzero_sample": first, "last_nonzero_sample": last, "note_on_sample": on, "note_off_sample": off, "windows": windows, "reference_origin_certified": False, "static_B_qualified": False, "formal_evaluation": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--midi", required=True)
    parser.add_argument("--wav", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if Path(args.out).exists():
        parser.error("Output exists; preserve previous verification")
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    result = verify(args.midi, args.wav, args.receipt, contract)
    result["contract_sha256"] = digest(args.contract)
    with Path(args.out).open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("role", "passed", "failures")}))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
